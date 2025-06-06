#ifdef _WIN32
#include <winsock2.h>
#endif
#include "command_consumer.h"
#include "session_manager.h" // To interact with sessions
#include "tank_pool.h"       // To interact with tanks (though mostly via session)
#include "tank.h"            // For tank->shoot(), tank->move()
#include <iostream>
#include <chrono>            // For std::chrono::seconds for sleep
#include <stdexcept>         // For std::runtime_error in handle_command_logic

// Define static const members
const std::string PlayerCommandConsumer::PLAYER_COMMANDS_QUEUE_NAME = "player_commands";

// Вспомогательная функция для преобразования amqp_bytes_t в std::string, полезна для тел сообщений
static std::string amqp_bytes_to_std_string(const amqp_bytes_t& bytes) {
    return std::string(static_cast<char*>(bytes.bytes), bytes.len);
}

// Вспомогательная функция для проверки ошибок AMQP (из примеров librabbitmq-c)
static void die_on_amqp_error(amqp_rpc_reply_t x, char const *context) {
    if (x.reply_type != AMQP_RESPONSE_NORMAL) {
        std::cerr << context << ": server error " << static_cast<int>(x.reply.id) << " ("
                  << amqp_method_name(x.reply.id) << ")" << std::endl;
        // Дополнительные детали для закрытия соединения/канала
        if (x.reply.id == AMQP_CONNECTION_CLOSE_METHOD || x.reply.id == AMQP_CHANNEL_CLOSE_METHOD) {
            auto* decoded_reply = static_cast<amqp_connection_close_t*>(x.reply.decoded);
            if (decoded_reply) {
                 std::cerr << " AMQP reply_code: " << decoded_reply->reply_code << std::endl;
                 std::cerr << " AMQP reply_text: " << amqp_bytes_to_std_string(decoded_reply->reply_text) << std::endl;
            }
        }
        // Для этого приложения мы, возможно, не захотим выходить, а скорее логировать и пытаться переподключиться.
        // Поэтому вместо exit(1) мы выбросим исключение или вернем false из connect_to_rabbitmq.
        // Пока что просто подробно логируем.
    }
}
static void die_on_library_error(int x, char const* context) {
    if (x < 0) { // AMQP_STATUS_OK равен 0, ошибки < 0
        std::cerr << context << ": library error: " << amqp_error_string2(x) << std::endl;
    }
}


PlayerCommandConsumer::PlayerCommandConsumer(SessionManager* sm,
                                             TankPool* tp,
                                             const std::string& host,
                                             int port,
                                             const std::string& user,
                                             const std::string& password,
                                             const std::string& vhost)
    : session_manager_(sm),
      tank_pool_(tp),
      rmq_host_(host),
      rmq_port_(port),
      rmq_user_(user),
      rmq_pass_(password),
      rmq_vhost_(vhost),
      rmq_conn_state_(nullptr), // Инициализируем как nullptr
      running_(false) {
    if (!session_manager_) {
        std::cerr << "PlayerCommandConsumer CRITICAL: SessionManager is null." << std::endl;
        throw std::invalid_argument("SessionManager cannot be null for PlayerCommandConsumer");
    }
    if (!tank_pool_) {
        std::cerr << "PlayerCommandConsumer CRITICAL: TankPool is null." << std::endl;
        throw std::invalid_argument("TankPool cannot be null for PlayerCommandConsumer");
    }
    std::cout << "PlayerCommandConsumer created for RabbitMQ at " << rmq_host_ << ":" << rmq_port_ << std::endl;
}

PlayerCommandConsumer::~PlayerCommandConsumer() {
    std::cout << "PlayerCommandConsumer destructor called." << std::endl;
    if (running_.load()) {
        stop(); // Убедимся, что потоку дан сигнал на остановку и он присоединен
    } else if (consumer_thread_.joinable()) {
        // Если не запущен, но поток все еще существует (например, start вызван, затем stop до полного выхода потока из предыдущего цикла)
        consumer_thread_.join();
    }
    // Окончательная очистка соединения, если stop() не справился (например, если поток так и не запустился)
    if (rmq_conn_state_ != nullptr) {
        std::cout << "PlayerCommandConsumer: Cleaning up RabbitMQ connection in destructor." << std::endl;
        disconnect_from_rabbitmq();
    }
}

void PlayerCommandConsumer::start() {
    if (running_.load()) {
        std::cout << "PlayerCommandConsumer already running." << std::endl;
        return;
    }
    running_.store(true);
    consumer_thread_ = std::thread(&PlayerCommandConsumer::consume_loop, this);
    std::cout << "PlayerCommandConsumer started, consumer thread launched." << std::endl;
}

void PlayerCommandConsumer::stop() {
    std::cout << "PlayerCommandConsumer stopping..." << std::endl;
    running_.store(false); // Сигнализируем циклу об остановке

    // Прерывание amqp_consume_message (если он блокируется на неопределенное время)
    // Это сложно. Закрытие соединения из другого потока - один из способов.
    // Если amqp_consume_message имеет таймаут, цикл проверит флаг running_.
    // Пока что мы полагаемся на таймаут в amqp_consume_message или ошибку соединения для прерывания цикла.
    // Более надежный способ прервать блокирующий amqp_consume_message - закрыть соединение
    // из этого метода stop(), что заставит amqp_consume_message вернуть ошибку.

    if (consumer_thread_.joinable()) {
        try {
            consumer_thread_.join();
            std::cout << "PlayerCommandConsumer: Consumer thread joined." << std::endl;
        } catch (const std::system_error& e) {
            std::cerr << "PlayerCommandConsumer: Error joining consumer thread: " << e.what()
                      << " (code: " << e.code() << ")" << std::endl;
        }
    }
    // disconnect_from_rabbitmq() вызывается consume_loop при выходе.
}

bool PlayerCommandConsumer::connect_to_rabbitmq() {
    rmq_conn_state_ = amqp_new_connection();
    if (!rmq_conn_state_) {
        std::cerr << "Consumer RMQ: Не удалось создать новое состояние соединения AMQP." << std::endl;
        return false;
    }

    amqp_socket_t* socket = amqp_tcp_socket_new(rmq_conn_state_);
    if (!socket) {
        std::cerr << "Consumer RMQ: Не удалось создать TCP сокет." << std::endl;
        amqp_destroy_connection(rmq_conn_state_); rmq_conn_state_ = nullptr;
        return false;
    }

    int status = amqp_socket_open(socket, rmq_host_.c_str(), rmq_port_);
    if (status != AMQP_STATUS_OK) {
        std::cerr << "Consumer RMQ: Не удалось открыть TCP сокет для " << rmq_host_ << ":" << rmq_port_
                  << ". Ошибка: " << amqp_error_string2(status) << std::endl;
        amqp_destroy_connection(rmq_conn_state_); rmq_conn_state_ = nullptr;
        return false;
    }

    amqp_rpc_reply_t login_reply = amqp_login(rmq_conn_state_, rmq_vhost_.c_str(), 0, AMQP_DEFAULT_FRAME_SIZE, 0, AMQP_SASL_METHOD_PLAIN, rmq_user_.c_str(), rmq_pass_.c_str());
    if (login_reply.reply_type != AMQP_RESPONSE_NORMAL) {
        std::cerr << "Consumer RMQ: Ошибка входа. Тип ответа AMQP: " << static_cast<int>(login_reply.reply_type);
        if (login_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
            if (login_reply.reply.id == AMQP_CONNECTION_CLOSE_METHOD) {
                auto* decoded_reply = static_cast<amqp_connection_close_t*>(login_reply.reply.decoded);
                if (decoded_reply) {
                    std::cerr << " Ошибка сервера: " << decoded_reply->reply_code
                              << " текст: " << amqp_bytes_to_std_string(decoded_reply->reply_text);
                }
            } else {
                 std::cerr << " Ошибка сервера, ID метода: " << login_reply.reply.id;
            }
        } else if (login_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
             std::cerr << " Ошибка библиотеки: " << amqp_error_string2(login_reply.library_error);
        }
        std::cerr << std::endl;
        amqp_destroy_connection(rmq_conn_state_); rmq_conn_state_ = nullptr;
        return false;
    }

    // Открытие канала
    amqp_channel_open(rmq_conn_state_, CHANNEL_ID);
    amqp_rpc_reply_t channel_open_reply = amqp_get_rpc_reply(rmq_conn_state_);
    if (channel_open_reply.reply_type != AMQP_RESPONSE_NORMAL) {
        std::cerr << "Consumer RMQ: Ошибка открытия канала. Тип ответа AMQP: " << static_cast<int>(channel_open_reply.reply_type);
        if (channel_open_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
            if (channel_open_reply.reply.id == AMQP_CHANNEL_CLOSE_METHOD) { // Обычно AMQP_CHANNEL_CLOSE_METHOD
                auto* decoded_reply = static_cast<amqp_channel_close_t*>(channel_open_reply.reply.decoded);
                if (decoded_reply) {
                    std::cerr << " Ошибка сервера: " << decoded_reply->reply_code
                              << " текст: " << amqp_bytes_to_std_string(decoded_reply->reply_text);
                }
            } else {
                 std::cerr << " Ошибка сервера, ID метода: " << channel_open_reply.reply.id;
            }
        } else if (channel_open_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
             std::cerr << " Ошибка библиотеки: " << amqp_error_string2(channel_open_reply.library_error);
        }
        std::cerr << std::endl;
        amqp_destroy_connection(rmq_conn_state_); rmq_conn_state_ = nullptr;
        return false;
    }

    // Объявление очереди как устойчивой (durable)
    // Примечание: amqp_queue_declare_ok_t все еще полезен для получения имени очереди, количества сообщений и т.д., если потребуется позже.
    // Пока что нас интересует только успех/неудача.
    amqp_queue_declare_ok_t *declare_ok = amqp_queue_declare(rmq_conn_state_, CHANNEL_ID, amqp_cstring_bytes(PLAYER_COMMANDS_QUEUE_NAME.c_str()), 0, 1, 0, 0, amqp_empty_table);
    amqp_rpc_reply_t queue_declare_reply = amqp_get_rpc_reply(rmq_conn_state_);
    if (queue_declare_reply.reply_type != AMQP_RESPONSE_NORMAL || !declare_ok) { // Также проверяем declare_ok для безопасности
        std::cerr << "Consumer RMQ: Ошибка объявления очереди. Тип ответа AMQP: " << static_cast<int>(queue_declare_reply.reply_type);
        if (queue_declare_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
             if (queue_declare_reply.reply.id == AMQP_CHANNEL_CLOSE_METHOD) { // Ошибки очереди часто закрывают канал
                auto* decoded_reply = static_cast<amqp_channel_close_t*>(queue_declare_reply.reply.decoded);
                if (decoded_reply) {
                    std::cerr << " Ошибка сервера: " << decoded_reply->reply_code
                              << " текст: " << amqp_bytes_to_std_string(decoded_reply->reply_text);
                }
            } else {
                 std::cerr << " Ошибка сервера, ID метода: " << queue_declare_reply.reply.id;
            }
        } else if (queue_declare_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
             std::cerr << " Ошибка библиотеки: " << amqp_error_string2(queue_declare_reply.library_error);
        }
        std::cerr << std::endl;
        if (!declare_ok) std::cerr << "Consumer RMQ: declare_ok был NULL." << std::endl;

        amqp_destroy_connection(rmq_conn_state_); rmq_conn_state_ = nullptr;
        return false;
    }


    // Установка QoS: prefetch_count = 1 (обрабатывать по одному сообщению за раз)
    amqp_basic_qos(rmq_conn_state_, CHANNEL_ID, 0, 1, 0);
    amqp_rpc_reply_t qos_reply = amqp_get_rpc_reply(rmq_conn_state_);
    if (qos_reply.reply_type != AMQP_RESPONSE_NORMAL) {
        std::cerr << "Consumer RMQ: Ошибка установки QoS. Тип ответа AMQP: " << static_cast<int>(qos_reply.reply_type);
         if (qos_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
            if (qos_reply.reply.id == AMQP_CHANNEL_CLOSE_METHOD) {
                auto* decoded_reply = static_cast<amqp_channel_close_t*>(qos_reply.reply.decoded);
                if (decoded_reply) {
                    std::cerr << " Ошибка сервера: " << decoded_reply->reply_code
                              << " текст: " << amqp_bytes_to_std_string(decoded_reply->reply_text);
                }
            } else {
                 std::cerr << " Ошибка сервера, ID метода: " << qos_reply.reply.id;
            }
        } else if (qos_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
             std::cerr << " Ошибка библиотеки: " << amqp_error_string2(qos_reply.library_error);
        }
        std::cerr << std::endl;
        amqp_destroy_connection(rmq_conn_state_); rmq_conn_state_ = nullptr;
        return false;
    }

    // Начало потребления сообщений (Basic Consume)
    amqp_basic_consume_ok_t* consume_ok = amqp_basic_consume(rmq_conn_state_, CHANNEL_ID, amqp_cstring_bytes(PLAYER_COMMANDS_QUEUE_NAME.c_str()), amqp_empty_bytes, 0, 0, 0, amqp_empty_table); // no_ack = 0 (false) - подтверждение требуется
    amqp_rpc_reply_t basic_consume_reply = amqp_get_rpc_reply(rmq_conn_state_);
    if (basic_consume_reply.reply_type != AMQP_RESPONSE_NORMAL || !consume_ok) {
        std::cerr << "Consumer RMQ: Ошибка Basic Consume. Тип ответа AMQP: " << static_cast<int>(basic_consume_reply.reply_type);
        if (basic_consume_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
            if (basic_consume_reply.reply.id == AMQP_CHANNEL_CLOSE_METHOD) {
                auto* decoded_reply = static_cast<amqp_channel_close_t*>(basic_consume_reply.reply.decoded);
                if (decoded_reply) {
                    std::cerr << " Ошибка сервера: " << decoded_reply->reply_code
                              << " текст: " << amqp_bytes_to_std_string(decoded_reply->reply_text);
                }
            } else {
                 std::cerr << " Ошибка сервера, ID метода: " << basic_consume_reply.reply.id;
            }
        } else if (basic_consume_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
             std::cerr << " Ошибка библиотеки: " << amqp_error_string2(basic_consume_reply.library_error);
        }
        std::cerr << std::endl;
        if (!consume_ok) std::cerr << "Consumer RMQ: consume_ok был NULL." << std::endl;

        amqp_destroy_connection(rmq_conn_state_); rmq_conn_state_ = nullptr;
        return false;
    }

    std::cout << "Consumer RMQ: Successfully connected and consuming from '" << PLAYER_COMMANDS_QUEUE_NAME << "'." << std::endl;
    return true;
}

void PlayerCommandConsumer::disconnect_from_rabbitmq() {
    if (rmq_conn_state_) {
        std::cout << "Consumer RMQ: Disconnecting..." << std::endl;
        // Хорошей практикой является проверка ответов RPC для этих операций, но для отключения часто используется принцип "наилучших усилий".
        amqp_channel_close(rmq_conn_state_, CHANNEL_ID, AMQP_REPLY_SUCCESS);
        amqp_connection_close(rmq_conn_state_, AMQP_REPLY_SUCCESS);
        int status = amqp_destroy_connection(rmq_conn_state_);
        die_on_library_error(status, "RMQ Destroying connection");
        rmq_conn_state_ = nullptr;
        std::cout << "Consumer RMQ: Disconnected." << std::endl;
    }
}

void PlayerCommandConsumer::consume_loop() {
    std::cout << "Consumer RMQ: Consume loop thread started." << std::endl;
    while (running_.load()) {
        if (!rmq_conn_state_ && !connect_to_rabbitmq()) {
            std::cerr << "Consumer RMQ: Connection failed. Retrying in 5 seconds..." << std::endl;
            if (rmq_conn_state_) disconnect_from_rabbitmq(); // Убедимся в очистке, если соединение частично удалось
            std::this_thread::sleep_for(std::chrono::seconds(5));
            continue;
        }

        bool connection_active = true;
        while (running_.load() && connection_active) {
            amqp_envelope_t envelope;
            amqp_maybe_release_buffers(rmq_conn_state_);

            struct timeval timeout; // Используем таймаут для amqp_consume_message
            timeout.tv_sec = 1;  // Таймаут 1 секунда
            timeout.tv_usec = 0;

            amqp_rpc_reply_t res = amqp_consume_message(rmq_conn_state_, &envelope, &timeout, 0);

            if (res.reply_type == AMQP_RESPONSE_NORMAL) {
                process_amqp_message(envelope);
                amqp_destroy_envelope(&envelope);
            } else if (res.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
                if (res.library_error == AMQP_STATUS_TIMEOUT) {
                    continue; // Нормальный таймаут, проверяем флаг running_ и продолжаем
                } else if (res.library_error == AMQP_STATUS_UNEXPECTED_STATE ||
                           res.library_error == AMQP_STATUS_CONNECTION_CLOSED ||
                           res.library_error == AMQP_STATUS_SOCKET_ERROR) {
                    std::cerr << "Consumer RMQ: Connection issue (" << amqp_error_string2(res.library_error)
                              << "). Attempting to reconnect." << std::endl;
                    connection_active = false; // Прерываем внутренний цикл для переподключения
                } else {
                    std::cerr << "Consumer RMQ: Library exception: " << amqp_error_string2(res.library_error) << std::endl;
                    connection_active = false; // Пока что рассматриваем другие ошибки библиотеки как проблемы с соединением
                }
            } else if (res.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
                 std::cerr << "Consumer RMQ: Server exception. Class_id: " << res.reply.id << ", Method_id: "
                           << (res.reply.decoded ? ((amqp_method_t*)res.reply.decoded)->id : 0) << std::endl;
                 connection_active = false; // Рассматриваем как проблему с соединением
            }
        } // Конец внутреннего цикла connection_active
        disconnect_from_rabbitmq(); // Отключаемся перед попыткой переподключения или выходом
        if (running_.load() && !connection_active) {
             std::cout << "Consumer RMQ: Reconnecting in 5 seconds due to detected issue..." << std::endl;
             std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }
    disconnect_from_rabbitmq(); // Окончательное отключение, если цикл завершается из-за running_ = false
    std::cout << "Consumer RMQ: Consume loop thread finished." << std::endl;
}

void PlayerCommandConsumer::process_amqp_message(amqp_envelope_t& envelope) {
    // std::cout << "Consumer RMQ: Received message, delivery tag " << envelope.delivery_tag << ", size " << envelope.message.body.len << std::endl;
    bool success = false;
    try {
        std::string message_str = amqp_bytes_to_std_string(envelope.message.body);
        nlohmann::json message_data = nlohmann::json::parse(message_str);
        success = handle_command_logic(message_data);
    } catch (const nlohmann::json::parse_error& e) {
        std::cerr << "Consumer RMQ: Ошибка разбора JSON: " << e.what() << ". Тело: "
                  << amqp_bytes_to_std_string(envelope.message.body) << std::endl;
        success = false; // Рассматриваем как ошибку
    } catch (const std::exception& e) {
        std::cerr << "Consumer RMQ: Исключение в handle_command_logic: " << e.what() << ". Тело: "
                  << amqp_bytes_to_std_string(envelope.message.body) << std::endl;
        success = false;
    }

    if (success) {
        die_on_library_error(amqp_basic_ack(rmq_conn_state_, CHANNEL_ID, envelope.delivery_tag, 0 /*multiple*/), "RMQ Basic Ack");
    } else {
        std::cerr << "Consumer RMQ: Отклонение сообщения (Nack) (тег доставки " << envelope.delivery_tag << ") из-за ошибки обработки." << std::endl;
        die_on_library_error(amqp_basic_nack(rmq_conn_state_, CHANNEL_ID, envelope.delivery_tag, 0 /*multiple*/, 0 /*requeue=false*/), "RMQ Basic Nack");
    }
}

bool PlayerCommandConsumer::handle_command_logic(const nlohmann::json& msg_data) {
    // std::cout << "Consumer handling command: " << msg_data.dump(2) << std::endl;
    if (!msg_data.contains("player_id") || !msg_data.contains("command") || !msg_data.contains("details")) {
        throw std::runtime_error("В сообщении отсутствуют обязательные поля: player_id, command или details.");
    }

    std::string player_id = msg_data["player_id"].get<std::string>();
    std::string command = msg_data["command"].get<std::string>();
    const nlohmann::json& details = msg_data["details"];

    if (!session_manager_) throw std::runtime_error("SessionManager не доступен.");

    auto session = session_manager_->get_session_by_player_id(player_id);
    if (!session) {
        std::cout << "Consumer: Нет активной сессии для player_id: " << player_id << ". Команда '" << command << "' проигнорирована." << std::endl;
        return true; // Подтверждаем сообщение, так как для этого игрока нечего делать.
    }

    auto tank = session->get_tank_for_player(player_id);
    if (!tank) {
        std::cout << "Consumer: Нет танка для player_id: " << player_id << " в сессии " << session->get_id()
                  << ". Команда '" << command << "' проигнорирована." << std::endl;
        return true; // Подтверждаем сообщение.
    }

    if (!tank->is_active() && (command == "move" || command == "shoot")) {
        std::cout << "Consumer: Танк " << tank->get_id() << " (игрок " << player_id << ") неактивен. Команда '"
                  << command << "' проигнорирована." << std::endl;
        return true; // Подтверждаем сообщение.
    }

    if (command == "move") {
        if (!details.contains("new_position")) {
            throw std::runtime_error("Команда 'move' не содержит 'new_position' в деталях.");
        }
        tank->move(details["new_position"]);
        // std::cout << "Consumer: Processed 'move' for tank " << tank->get_id() << std::endl;
    } else if (command == "shoot") {
        tank->shoot();
        // std::cout << "Consumer: Processed 'shoot' for tank " << tank->get_id() << std::endl;
    } else {
        std::cerr << "Consumer: Получена неизвестная команда '" << command << "' для игрока " << player_id << "." << std::endl;
        return true; // Подтверждаем неизвестные команды, а не зацикливаем их через Nack, если они некорректны, но не приведут к успеху.
    }
    return true; // Успешно обработано (или намеренно проигнорировано)
}
