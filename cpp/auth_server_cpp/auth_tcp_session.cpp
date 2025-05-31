#include "auth_tcp_session.h"
#include <chrono> // For gRPC deadlines

AuthTcpSession::AuthTcpSession(tcp::socket socket, std::shared_ptr<grpc::Channel> grpc_channel)
    : socket_(std::move(socket)) {
    if (!grpc_channel) {
        std::cerr << "AuthTcpSession FATAL: gRPC channel is null. Cannot create AuthService stub." << std::endl;
        // This session will be non-functional. Consider throwing or setting an error state.
        // For now, grpc_stub_ will remain null, and attempts to use it will fail.
    } else {
        grpc_stub_ = auth::AuthService::NewStub(grpc_channel);
        // std::cout << "AuthTcpSession: AuthService gRPC Stub initialized." << std::endl;
    }
    // std::cout << "AuthTcpSession created for " << socket_.remote_endpoint().address().to_string()
    //           << ":" << socket_.remote_endpoint().port() << std::endl;
}

void AuthTcpSession::start() {
    // std::cout << "AuthTcpSession started for " << socket_.remote_endpoint().address().to_string() << std::endl;
    if (!grpc_stub_) { // If stub wasn't initialized, this session is useless.
        std::cerr << "AuthTcpSession Error: gRPC stub not initialized. Closing session for "
                  << socket_.remote_endpoint().address().to_string() << std::endl;
        send_response("{\"status\": \"error\", \"message\": \"Auth service connection error. Please try later.\"}\n");
        // close_session() will be called by handle_write or if send_response fails to open socket.
        return;
    }
    do_read();
}

void AuthTcpSession::close_session(const std::string& reason) {
    if (socket_.is_open()) {
        // std::cout << "AuthTcpSession: Closing session for "
        //           << socket_.remote_endpoint().address().to_string() << ":" << socket_.remote_endpoint().port()
        //           << ". Reason: " << reason << std::endl;
        boost::system::error_code ec;
        socket_.shutdown(tcp::socket::shutdown_both, ec); // Graceful shutdown
        socket_.close(ec); // Close socket
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
            // std::cout << "AuthTCP Recv from " << socket_.remote_endpoint().address().to_string() << ": " << line << std::endl;
            process_json_request(line);
        }

        if (socket_.is_open()) { // If process_json_request didn't close session
            do_read();
        }
    } else if (error == boost::asio::error::eof) {
        close_session("Client disconnected (EOF).");
    } else if (error == boost::asio::error::connection_reset) {
        close_session("Client connection reset.");
    } else if (error == boost::asio::error::operation_aborted) {
        // std::cout << "AuthTCP Read operation aborted." << std::endl; // Normal on server shutdown
    } else {
        std::cerr << "AuthTCP Read error: " << error.message() << std::endl;
        close_session("Read error.");
    }
}

void AuthTcpSession::process_json_request(const std::string& json_str) {
    json response_payload;
    if (!grpc_stub_) { // Check again, in case it wasn't set during construction
        response_payload = {
            {"status", "error"},
            {"message", "Authentication service is currently unavailable. Please try again later."}
        };
        send_response(response_payload.dump() + "\n");
        return;
    }

    try {
        json request_payload = json::parse(json_str);

        if (!request_payload.contains("action") || !request_payload.contains("username") || !request_payload.contains("password")) {
            response_payload = {
                {"status", "error"},
                {"message", "Request missing required fields: action, username, password"}
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
        context.set_deadline(std::chrono::system_clock::now() + std::chrono::milliseconds(1000)); // 1 second timeout
        grpc::Status status;

        // std::cout << "AuthTCP: Sending gRPC request for action '" << action << "' user '" << username << "'" << std::endl;

        if (action == "login") {
            status = grpc_stub_->AuthenticateUser(&context, grpc_request, &grpc_response);
        } else if (action == "register") {
            status = grpc_stub_->RegisterUser(&context, grpc_request, &grpc_response);
        } else {
            response_payload = { {"status", "error"}, {"message", "Unknown action: " + action} };
            send_response(response_payload.dump() + "\n");
            return;
        }

        if (status.ok()) {
            response_payload = {
                {"status", grpc_response.authenticated() ? "success" : "failure"},
                {"message", grpc_response.message()},
                {"token", grpc_response.token()}
            };
            // std::cout << "AuthTCP: gRPC call OK for '" << action << "', user '" << username << "'. Auth: " << grpc_response.authenticated() << std::endl;
        } else {
            std::cerr << "AuthTCP: gRPC call FAILED for '" << action << "', user '" << username
                      << "'. Code: " << status.error_code() << ", Msg: " << status.error_message() << std::endl;
            response_payload = {
                {"status", "error"},
                {"message", "Auth service communication error (" + std::to_string(status.error_code()) + "): " + status.error_message()}
            };
        }

    } catch (const json::parse_error& e) {
        std::cerr << "AuthTCP: JSON parsing error: " << e.what() << " for request: " << json_str << std::endl;
        response_payload = { {"status", "error"}, {"message", "Invalid JSON request: " + std::string(e.what())} };
    } catch (const std::exception& e) {
        std::cerr << "AuthTCP: Exception processing request: " << e.what() << " for request: " << json_str << std::endl;
        response_payload = { {"status", "error"}, {"message", "Server error processing request: " + std::string(e.what())} };
    }

    send_response(response_payload.dump() + "\n");
}

void AuthTcpSession::send_response(const std::string& msg) {
    if (!socket_.is_open()){
        // std::cerr << "AuthTcpSession: Attempted to send response on closed socket." << std::endl;
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
        // std::cout << "AuthTCP Sent " << length << " bytes successfully." << std::endl;
        { // Scope for potential lock if queue was shared (not strictly needed with asio strand/single thread)
            if (!write_msgs_queue_.empty()) {
                 write_msgs_queue_.pop_front();
            }
        }
        if (!write_msgs_queue_.empty()) {
            do_write(); // Write next message in queue
        }
    } else {
        std::cerr << "AuthTCP Write error: " << error.message() << std::endl;
        close_session("Write error.");
    }
}
