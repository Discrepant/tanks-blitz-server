#include "auth_tcp_session.h"
#include <chrono> // Для крайних сроков gRPC

AuthTcpSession::AuthTcpSession(tcp::socket socket, std::shared_ptr<grpc::Channel> grpc_channel)
    : socket_(std::move(socket)) {
    if (!grpc_channel) {
        std::cerr << "AuthTcpSession FATAL: gRPC channel is null. Cannot create AuthService stub." << std::endl;
        // Эта сессия будет нефункциональной. Рассмотрите возможность выброса исключения или установки состояния ошибки.
        // Пока что grpc_stub_ останется нулевым, и попытки его использовать приведут к ошибке.
    } else {
        grpc_stub_ = auth::AuthService::NewStub(grpc_channel);
        // std::cout << "AuthTcpSession: Заглушка gRPC для AuthService инициализирована." << std::endl; // AuthTcpSession: AuthService gRPC Stub initialized.
    }
    // std::cout << "AuthTcpSession создана для " << socket_.remote_endpoint().address().to_string() // AuthTcpSession created for
    //           << ":" << socket_.remote_endpoint().port() << std::endl;
}

void AuthTcpSession::start() {
    // std::cout << "AuthTcpSession запущена для " << socket_.remote_endpoint().address().to_string() << std::endl; // AuthTcpSession started for
    if (!grpc_stub_) { // Если заглушка не была инициализирована, эта сессия бесполезна.
        std::cerr << "AuthTcpSession Error: gRPC stub not initialized. Closing session for "
                  << socket_.remote_endpoint().address().to_string() << std::endl;
        send_response("{\"status\": \"error\", \"message\": \"Ошибка подключения к сервису аутентификации. Пожалуйста, попробуйте позже.\"}\n");
        // close_session() будет вызвана handle_write или если send_response не сможет открыть сокет.
        return;
    }
    do_read();
}

void AuthTcpSession::close_session(const std::string& reason) {
    if (socket_.is_open()) {
        // std::cout << "AuthTcpSession: Закрытие сессии для " // AuthTcpSession: Closing session for
        //           << socket_.remote_endpoint().address().to_string() << ":" << socket_.remote_endpoint().port()
        //           << ". Причина: " << reason << std::endl; // Reason:
        boost::system::error_code ec;
        socket_.shutdown(tcp::socket::shutdown_both, ec); // Корректное завершение работы
        socket_.close(ec); // Закрыть сокет
    }
}

void AuthTcpSession::do_read() {
    if (!socket_.is_open()) return;

    auto self(shared_from_this());
    boost::asio::async_read_until(socket_, read_buffer_, '\n',
        [this, self](const boost::system::error_code& error, std::size_t length) {
            handle_read(error, length);
        });
}

void AuthTcpSession::handle_read(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        std::istream is(&read_buffer_);
        std::string line;
        std::getline(is, line);

        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }

        if (!line.empty()) {
            // std::cout << "AuthTCP: Получено от " << socket_.remote_endpoint().address().to_string() << ": " << line << std::endl; // AuthTCP Recv from
            process_json_request(line);
        }

        if (socket_.is_open()) { // Если process_json_request не закрыл сессию
            do_read();
        }
    } else if (error == boost::asio::error::eof) {
        close_session("Клиент отключился (EOF).");
    } else if (error == boost::asio::error::connection_reset) {
        close_session("Соединение сброшено клиентом.");
    } else if (error == boost::asio::error::operation_aborted) {
        // std::cout << "AuthTCP: Операция чтения прервана." << std::endl; // AuthTCP Read operation aborted. // Нормально при завершении работы сервера
    } else {
        std::cerr << "AuthTCP Read error: " << error.message() << std::endl;
        close_session("Ошибка чтения.");
    }
}

void AuthTcpSession::process_json_request(const std::string& json_str) {
    json response_payload;
    if (!grpc_stub_) { // Проверяем снова, на случай если не было установлено во время создания
        response_payload = {
            {"status", "error"},
            {"message", "Сервис аутентификации в данный момент недоступен. Пожалуйста, попробуйте снова позже."}
        };
        send_response(response_payload.dump() + "\n");
        return;
    }

    try {
        json request_payload = json::parse(json_str);

        if (!request_payload.contains("action") || !request_payload.contains("username") || !request_payload.contains("password")) {
            response_payload = {
                {"status", "error"},
                {"message", "В запросе отсутствуют обязательные поля: action, username, password"}
            };
            send_response(response_payload.dump() + "\n");
            return;
        }

        std::string action = request_payload["action"].get<std::string>();
        std::string username = request_payload["username"].get<std::string>();
        std::string password = request_payload["password"].get<std::string>();

        auth::AuthRequest grpc_request;
        grpc_request.set_username(username);
        grpc_request.set_password(password);

        auth::AuthResponse grpc_response;
        grpc::ClientContext context;
        context.set_deadline(std::chrono::system_clock::now() + std::chrono::milliseconds(1000)); // Таймаут 1 секунда
        grpc::Status status;

        // std::cout << "AuthTCP: Отправка gRPC запроса для действия '" << action << "', пользователь '" << username << "'" << std::endl; // AuthTCP: Sending gRPC request for action '...' user '...'

        if (action == "login") {
            status = grpc_stub_->AuthenticateUser(&context, grpc_request, &grpc_response);
        } else if (action == "register") {
            status = grpc_stub_->RegisterUser(&context, grpc_request, &grpc_response);
        } else {
            response_payload = { {"status", "error"}, {"message", "Неизвестное действие: " + action} };
            send_response(response_payload.dump() + "\n");
            return;
        }

        if (status.ok()) {
            response_payload = {
                {"status", grpc_response.authenticated() ? "success" : "failure"},
                {"message", grpc_response.message()}, // Предполагаем, что сообщение от gRPC уже локализовано или не требует локализации
                {"token", grpc_response.token()}
            };
            // std::cout << "AuthTCP: gRPC вызов OK для '" << action << "', пользователь '" << username << "'. Аутентификация: " << grpc_response.authenticated() << std::endl; // AuthTCP: gRPC call OK for '...', user '...'. Auth: ...
        } else {
            std::cerr << "AuthTCP: gRPC call FAILED for '" << action << "', user '" << username
                      << "'. Code: " << status.error_code() << ", Msg: " << status.error_message() << std::endl;
            response_payload = {
                {"status", "error"},
                {"message", "Ошибка связи с сервисом аутентификации (" + std::to_string(status.error_code()) + "): " + status.error_message()}
            };
        }

    } catch (const json::parse_error& e) {
        std::cerr << "AuthTCP: JSON parsing error: " << e.what() << " for request: " << json_str << std::endl;
        response_payload = { {"status", "error"}, {"message", "Ошибка разбора JSON: " + std::string(e.what())} };
    } catch (const std::exception& e) {
        std::cerr << "AuthTCP: Exception processing request: " << e.what() << " for request: " << json_str << std::endl;
        response_payload = { {"status", "error"}, {"message", "Ошибка сервера при обработке запроса: " + std::string(e.what())} };
    }

    send_response(response_payload.dump() + "\n");
}

void AuthTcpSession::send_response(const std::string& msg) {
    if (!socket_.is_open()){
        // std::cerr << "AuthTcpSession: Попытка отправить ответ на закрытый сокет." << std::endl; // AuthTcpSession: Attempted to send response on closed socket. // Попытка отправить ответ на закрытый сокет.
        return;
    }

    bool write_in_progress = !write_msgs_queue_.empty();
    write_msgs_queue_.push_back(msg);
    if (!write_in_progress) {
        do_write();
    }
}

void AuthTcpSession::do_write() {
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

void AuthTcpSession::handle_write(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        // std::cout << "AuthTCP: Успешно отправлено " << length << " байт." << std::endl; // AuthTCP Sent ... bytes successfully.
        { // Область видимости для потенциальной блокировки, если очередь была бы общей (не строго необходимо с asio strand/однопоточным выполнением)
            if (!write_msgs_queue_.empty()) {
                 write_msgs_queue_.pop_front();
            }
        }
        if (!write_msgs_queue_.empty()) {
            do_write(); // Записать следующее сообщение в очереди
        }
    } else {
        std::cerr << "AuthTCP Write error: " << error.message() << std::endl;
        close_session("Ошибка записи.");
    }
}
