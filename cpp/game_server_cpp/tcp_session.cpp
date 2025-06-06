#include "tcp_session.h"
#include "session_manager.h" // Для методов SessionManager
#include "tank_pool.h"       // Для методов TankPool
#include "tank.h"            // Для методов Tank
#include <boost/algorithm/string.hpp> // Для разделения строк (например, boost::split)
#include <chrono>             // Для крайних сроков gRPC

// Определение статических const членов, если есть (например, имена очередей)
const std::string GameTCPSession::RMQ_PLAYER_COMMANDS_QUEUE = "player_commands";
const std::string GameTCPSession::RMQ_CHAT_MESSAGES_QUEUE = "game_chat_messages";


GameTCPSession::GameTCPSession(tcp::socket socket,
                               SessionManager* sm,
                               TankPool* tp,
                               amqp_connection_state_t rabbitmq_conn_state,
                               std::shared_ptr<grpc::Channel> grpc_auth_channel)
    : socket_(std::move(socket)),
      session_manager_(sm),
      tank_pool_(tp),
      rmq_conn_state_(rabbitmq_conn_state),
      authenticated_(false) {

    if (!session_manager_ || !tank_pool_) {
        std::cerr << "GameTCPSession FATAL: SessionManager or TankPool is null." << std::endl;
        // Эта сессия, скорее всего, неработоспособна, можно выбросить исключение или установить состояние ошибки.
    }
    if (grpc_auth_channel) {
        auth_grpc_stub_ = auth::AuthService::NewStub(grpc_auth_channel);
        // std::cout << "GameTCPSession: Auth gRPC Stub initialized." << std::endl;
    } else {
        std::cerr << "GameTCPSession FATAL: grpc_auth_channel is null. Authentication will fail." << std::endl;
    }
    // std::cout << "GameTCPSession created for " << socket_.remote_endpoint().address().to_string() << std::endl;
}

void GameTCPSession::start() {
    // std::cout << "GameTCPSession started for " << socket_.remote_endpoint().address().to_string() << std::endl;
    send_message("СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО Добро пожаловать в TankGame! Пожалуйста, ВОЙДИТЕ или ЗАРЕГИСТРИРУЙТЕСЬ.\n");
    do_read();
}

void GameTCPSession::close_session(const std::string& reason) {
    if (socket_.is_open()) {
        std::cout << "GameTCPSession: Closing session for player '" << username_
                  << "' (" << socket_.remote_endpoint().address().to_string()
                  << "). Reason: " << reason << std::endl;

        if (authenticated_ && !username_.empty() && session_manager_) {
            // SessionManager::remove_player_from_any_session обрабатывает освобождение танка.
            session_manager_->remove_player_from_any_session(username_);
        }

        boost::system::error_code ec;
        socket_.shutdown(tcp::socket::shutdown_both, ec); // Корректное завершение
        socket_.close(ec); // Закрыть сокет
    }
    // Очистка конфиденциальных данных
    authenticated_ = false;
    username_.clear();
    current_session_id_.clear();
    assigned_tank_id_.clear();
}

void GameTCPSession::do_read() {
    if (!socket_.is_open()) return; // Не читать, если сокет закрыт

    auto self(shared_from_this()); // Поддерживать жизнь сессии во время асинхронной операции
    boost::asio::async_read_until(socket_, read_buffer_, '\n',
        [this, self](const boost::system::error_code& error, std::size_t length) {
            handle_read(error, length);
        });
}

void GameTCPSession::handle_read(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        std::istream is(&read_buffer_);
        std::string line;
        std::getline(is, line);

        if (!line.empty() && line.back() == '\r') { // Обработка \r\n от telnet
            line.pop_back();
        }

        if (!line.empty()) {
            // std::cout << "TCP Recv from " << (username_.empty() ? socket_.remote_endpoint().address().to_string() : username_) << ": " << line << std::endl;
            process_command(line);
        }

        if (socket_.is_open()) { // Если process_command не закрыл сессию
            do_read(); // Продолжаем чтение для следующей команды
        }
    } else if (error == boost::asio::error::eof) {
        close_session("Клиент отключился (EOF).");
    } else if (error == boost::asio::error::connection_reset) {
        close_session("Соединение сброшено клиентом.");
    } else if (error == boost::asio::error::operation_aborted) {
        std::cout << "GameTCPSession: Операция чтения прервана для " << username_ << "." << std::endl;
    } else {
        std::cerr << "GameTCPSession: Ошибка чтения для " << username_ << ": " << error.message() << std::endl;
        close_session("Ошибка чтения.");
    }
}

void GameTCPSession::send_message(const std::string& msg) {
    if (!socket_.is_open()){
         std::cerr << "GameTCPSession: Попытка отправить сообщение на закрытый сокет для " << username_ << std::endl;
        return;
    }

    bool write_in_progress = !write_msgs_queue_.empty();
    write_msgs_queue_.push_back(msg);
    if (!write_in_progress) {
        do_write();
    }
}

void GameTCPSession::do_write() {
    if (!socket_.is_open() || write_msgs_queue_.empty()) {
        return;
    }
    auto self(shared_from_this());
    boost::asio::async_write(socket_,
        boost::asio::buffer(write_msgs_queue_.front().data(), write_msgs_queue_.front().length()),
        [this, self](const boost::system::error_code& error, std::size_t length) {
            handle_write(error, length);
        });
}

void GameTCPSession::handle_write(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        // std::cout << "TCP Sent " << length << " bytes to " << username_ << std::endl;
        { // Область видимости для блокировки при доступе к очереди из нескольких потоков (хотя обработчики ASIO сериализованы)
            if (!write_msgs_queue_.empty()) {
                 write_msgs_queue_.pop_front();
            }
        }
        if (!write_msgs_queue_.empty()) {
            do_write(); // Записать следующее сообщение в очереди
        }
    } else {
        std::cerr << "GameTCPSession: Ошибка записи для " << username_ << ": " << error.message() << std::endl;
        close_session("Ошибка записи.");
    }
}


void GameTCPSession::process_command(const std::string& line) {
    std::vector<std::string> parts;
    boost::split(parts, line, boost::is_any_of(" "), boost::token_compress_on);

    if (parts.empty() || parts[0].empty()) return;

    std::string command_verb = parts[0];
    boost::to_upper(command_verb);
    std::vector<std::string> args_list;
    if (parts.size() > 1) {
        args_list.assign(parts.begin() + 1, parts.end());
    }

    if (!authenticated_ && command_verb != "LOGIN" && command_verb != "REGISTER" && command_verb != "HELP" && command_verb != "QUIT") {
        send_message("ОШИБКА_СЕРВЕРА НЕ_АВТОРИЗОВАН Пожалуйста, сначала ВОЙДИТЕ или ЗАРЕГИСТРИРУЙТЕСЬ, чтобы использовать команду: " + command_verb + "\n");
        return;
    }

    if (command_verb == "LOGIN") handle_login(args_list);
    else if (command_verb == "REGISTER") handle_register(args_list);
    else if (command_verb == "MOVE") handle_move(args_list);
    else if (command_verb == "SHOOT") handle_shoot(args_list);
    else if (command_verb == "SAY") handle_say(args_list);
    else if (command_verb == "HELP") handle_help(args_list);
    else if (command_verb == "PLAYERS") handle_players(args_list);
    else if (command_verb == "QUIT") handle_quit(args_list);
    else send_message("ОШИБКА_СЕРВЕРА НЕИЗВЕСТНАЯ_КОМАНДА " + command_verb + "\n");
}

// --- Обработчики команд ---
void GameTCPSession::handle_login(const std::vector<std::string>& args) {
    std::string remote_ep_str = "unknown_endpoint"; // Значение по умолчанию
    try {
        if (socket_.is_open()) {
            boost::system::error_code ec_re;
            tcp::endpoint re = socket_.remote_endpoint(ec_re); // Это может выбросить исключение или установить ec_re
            if (!ec_re) {
                remote_ep_str = re.address().to_string() + ":" + std::to_string(re.port());
            } else {
                std::cerr << "GameTCPSession: Error code set by remote_endpoint in handle_login: " 
                          << ec_re.message() << " for player attempt: " << (args.empty() ? "N/A" : args[0]) << std::endl;
                // Оставляем remote_ep_str как "unknown_endpoint"
            }
        } else {
            std::cerr << "GameTCPSession: Socket is not open at the beginning of handle_login for player attempt: " 
                      << (args.empty() ? "N/A" : args[0]) << std::endl;
            // Оставляем remote_ep_str как "unknown_endpoint"
        }
    } catch (const boost::system::system_error& e) {
        std::cerr << "GameTCPSession: boost::system::system_error caught while getting remote_endpoint in handle_login: "
                  << e.what() << " for player attempt: " << (args.empty() ? "N/A" : args[0]) << std::endl;
        // Оставляем remote_ep_str как "unknown_endpoint"
    } catch (const std::exception& e) {
        std::cerr << "GameTCPSession: std::exception caught while getting remote_endpoint in handle_login: "
                  << e.what() << " for player attempt: " << (args.empty() ? "N/A" : args[0]) << std::endl;
        // Оставляем remote_ep_str как "unknown_endpoint"
    }

    if (args.size() < 2) {
        send_message("ОШИБКА_СЕРВЕРА ВХОД_НЕУДАЧА Неверные аргументы. Использование: LOGIN <имя_пользователя> <пароль>\n");
        return;
    }
    std::string provided_username = args[0];
    std::string password = args[1];

    if (!auth_grpc_stub_) {
        send_message("ОШИБКА_СЕРВЕРА ВХОД_НЕУДАЧА Сервис аутентификации недоступен.\n");
        return;
    }
    if (authenticated_) {
        send_message("ОШИБКА_СЕРВЕРА ВХОД_НЕУДАЧА Уже вошли как " + username_ + ".\n");
        return;
    }

    auth::AuthRequest grpc_request;
    grpc_request.set_username(provided_username);
    grpc_request.set_password(password);
    auth::AuthResponse grpc_response;
    grpc::ClientContext context;
    context.set_deadline(std::chrono::system_clock::now() + std::chrono::milliseconds(1000)); // Таймаут 1с

    grpc::Status status = auth_grpc_stub_->AuthenticateUser(&context, grpc_request, &grpc_response);

    if (status.ok() && grpc_response.authenticated()) {
        username_ = provided_username;
        authenticated_ = true;

        if (!tank_pool_ || !session_manager_) {
            send_message("ОШИБКА_СЕРВЕРА ВХОД_УСПЕШЕН_НО_ИГРА_НЕДОСТУПНА Ошибка сервера.\n");
            authenticated_ = false; username_.clear(); // Откат
            return;
        }
        auto tank = tank_pool_->acquire_tank();
        if (tank) {
            assigned_tank_id_ = tank->get_id();
            // Используем find_or_create_session_for_player для лучшего управления сессиями
            auto game_session = session_manager_->find_or_create_session_for_player(
                username_,
                remote_ep_str,
                tank,
                false /*is_udp_player=false*/
            );

            if (game_session) {
                current_session_id_ = game_session->get_id();
                send_message("ОТВЕТ_СЕРВЕРА ВХОД_УСПЕШЕН " + grpc_response.message() + " Токен: " + grpc_response.token() + "\n");
                send_message("СЕРВЕР: Игрок " + username_ + " присоединился к игровой сессии " + current_session_id_ + " с танком " + assigned_tank_id_ + ".\n");
                send_message("СЕРВЕР: Состояние танка: " + tank->get_state().dump() + "\n");
            } else {
                send_message("ОШИБКА_СЕРВЕРА ВХОД_НЕУДАЧА Не удалось присоединиться/создать игровую сессию.\n");
                tank_pool_->release_tank(assigned_tank_id_); // Освобождаем полученный танк
                assigned_tank_id_.clear();
                authenticated_ = false; username_.clear(); // Откат
            }
        } else { // Нет доступных танков
            send_message("ОШИБКА_СЕРВЕРА ВХОД_НЕУДАЧА Нет свободных танков.\n");
            authenticated_ = false; username_.clear(); // Откат
        }
    } else { // Ошибка gRPC или аутентификация не удалась от сервиса
        std::string error_msg = status.ok() ? grpc_response.message() : ("Ошибка сервиса аутентификации (" + std::to_string(status.error_code()) + "): " + status.error_message());
        send_message("ОШИБКА_СЕРВЕРА ВХОД_НЕУДАЧА " + error_msg + "\n");
    }
}

void GameTCPSession::handle_register(const std::vector<std::string>& args) {
    send_message("ОШИБКА_СЕРВЕРА РЕГИСТРАЦИЯ_НЕУДАЧА Регистрация через игровой сервер пока не поддерживается.\n");
}

void GameTCPSession::handle_move(const std::vector<std::string>& args) {
    if (!authenticated_) { send_message("ОШИБКА_СЕРВЕРА НЕ_АВТОРИЗОВАН\n"); return; }
    if (args.size() < 2) {
        send_message("ОШИБКА_СЕРВЕРА ДВИЖЕНИЕ_НЕУДАЧА Неверные аргументы. Использование: MOVE <X> <Y>\n"); return;
    }
    if (current_session_id_.empty() || assigned_tank_id_.empty() || !session_manager_) {
        send_message("ОШИБКА_СЕРВЕРА ДВИЖЕНИЕ_НЕУДАЧА Не в игре или ошибка сервера.\n"); return;
    }
    try {
        // Предполагаем, что X и Y - это первые два аргумента для move
        json new_position_json = {{"x", std::stoi(args[0])}, {"y", std::stoi(args[1])}};
        json command_json = {
            {"player_id", username_}, {"command", "move"},
            {"details", {{"source", "tcp_handler"}, {"tank_id", assigned_tank_id_}, {"new_position", new_position_json}}}
        };
        publish_to_rabbitmq_internal(RMQ_PLAYER_COMMANDS_QUEUE, command_json);
        send_message("СЕРВЕР_ПОДТВЕРЖДЕНИЕ КОМАНДА_ДВИЖЕНИЯ_ОТПРАВЛЕНА\n");
    } catch (const std::exception& e) {
        send_message("ОШИБКА_СЕРВЕРА ДВИЖЕНИЕ_НЕУДАЧА Неверные координаты: " + std::string(e.what()) + "\n");
    }
}

void GameTCPSession::handle_shoot(const std::vector<std::string>& args) {
    if (!authenticated_) { send_message("ОШИБКА_СЕРВЕРА НЕ_АВТОРИЗОВАН\n"); return; }
    if (current_session_id_.empty() || assigned_tank_id_.empty() || !session_manager_) {
        send_message("ОШИБКА_СЕРВЕРА ВЫСТРЕЛ_НЕУДАЧА Не в игре или ошибка сервера.\n"); return;
    }
    json command_json = {
        {"player_id", username_}, {"command", "shoot"},
        {"details", {{"source", "tcp_handler"}, {"tank_id", assigned_tank_id_}}}
    };
    publish_to_rabbitmq_internal(RMQ_PLAYER_COMMANDS_QUEUE, command_json);
    send_message("СЕРВЕР_ПОДТВЕРЖДЕНИЕ КОМАНДА_ВЫСТРЕЛА_ОТПРАВЛЕНА\n");
}

void GameTCPSession::handle_say(const std::vector<std::string>& args) {
    if (!authenticated_) { send_message("ОШИБКА_СЕРВЕРА НЕ_АВТОРИЗОВАН\n"); return; }
    if (args.empty()) {
        send_message("ОШИБКА_СЕРВЕРА СКАЗАТЬ_НЕУДАЧА Сообщение отсутствует. Использование: SAY <сообщение ...>\n"); return;
    }
    std::string message_text;
    for (size_t i = 0; i < args.size(); ++i) {
        message_text += args[i] + (i == args.size() - 1 ? "" : " ");
    }
    send_message("СЕРВЕР: Вы сказали: " + message_text + "\n"); // Пока эхо-ответ
    json chat_json = {
        {"player_id", username_}, {"command", "say_broadcast"}, // Или специфичная команда чата
        {"details", {{"source", "tcp_handler"}, {"session_id", current_session_id_}, {"text", message_text}}}
    };
    publish_to_rabbitmq_internal(RMQ_CHAT_MESSAGES_QUEUE, chat_json); // Используем другую очередь для чата
}

void GameTCPSession::handle_help(const std::vector<std::string>& args) {
    std::string help_msg = "СЕРВЕР: Доступные команды:\n";
    help_msg += "  LOGIN <имя_пользователя> <пароль>\n";
    help_msg += "  REGISTER <имя_пользователя> <пароль> (Не работает)\n";
    if (authenticated_) {
        help_msg += "  MOVE <x> <y>\n  SHOOT\n  SAY <сообщение ...>\n  PLAYERS\n";
    }
    help_msg += "  HELP\n  QUIT\n";
    send_message(help_msg);
}

void GameTCPSession::handle_players(const std::vector<std::string>& args) {
    if (!authenticated_ || !session_manager_) { send_message("ОШИБКА_СЕРВЕРА НЕ_АВТОРИЗОВАН или ошибка сервера.\n"); return; }
    if (current_session_id_.empty()) {
        send_message("ИНФО_СЕРВЕРА Вы в данный момент не в игровой сессии.\n"); return;
    }
    auto game_session = session_manager_->get_session(current_session_id_);
    if (game_session) {
        const auto& players_map = game_session->get_players();
        if (players_map.empty()) {
            send_message("ИНФО_СЕРВЕРА В вашей сессии '" + current_session_id_ + "' нет игроков.\n");
        } else {
            std::string list_msg = "СЕРВЕР: Игроки в сессии '" + current_session_id_ + "':\n";
            for (const auto& pair : players_map) {
                list_msg += "  - " + pair.first + (pair.first == username_ ? " (Вы)" : "") + "\n";
            }
            send_message(list_msg);
        }
    } else {
        send_message("ОШИБКА_СЕРВЕРА Не удалось получить информацию о сессии для ID: " + current_session_id_ + "\n");
    }
}

void GameTCPSession::handle_quit(const std::vector<std::string>& args) {
    send_message("ОТВЕТ_СЕРВЕРА ДО_СВИДАНИЯ Закрытие соединения.\n");
    // std::cout << "GameTCPSession: Player " << username_ << " initiated QUIT." << std::endl;
    close_session("Команда выхода от игрока.");
}

void GameTCPSession::publish_to_rabbitmq_internal(const std::string& queue_name, const nlohmann::json& message_json) {
    if (!rmq_conn_state_) {
        std::cerr << "GameTCPSession (" << username_ << "): Состояние соединения RabbitMQ null. Невозможно опубликовать." << std::endl;
        return;
    }
    std::string message_body = message_json.dump();
    amqp_bytes_t message_bytes;
    message_bytes.len = message_body.length();
    message_bytes.bytes = (void*)message_body.c_str();
    amqp_basic_properties_t props;
    props._flags = AMQP_BASIC_DELIVERY_MODE_FLAG;
    props.delivery_mode = 2; // Постоянный

    int status = amqp_basic_publish(rmq_conn_state_, 1, amqp_empty_bytes, amqp_cstring_bytes(queue_name.c_str()),
                                    0, 0, &props, message_bytes);
    if (status) {
        std::cerr << "GameTCPSession (" << username_ << "): Не удалось опубликовать в очередь RabbitMQ '" << queue_name
                  << "': " << amqp_error_string2(status) << std::endl;
    }
    // else { std::cout << "GameTCPSession (" << username_ << "): Message published to RabbitMQ queue '" << queue_name << "'" << std::endl;} // Подробно
}
