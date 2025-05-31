#include "auth_tcp_session.h"
#include <boost/algorithm/string.hpp> // For string utilities if needed later

AuthTcpSession::AuthTcpSession(tcp::socket socket, std::shared_ptr<grpc::Channel> grpc_channel)
    : socket_(std::move(socket)) {
    grpc_stub_ = auth::AuthService::NewStub(grpc_channel);
    std::cout << "AuthTcpSession created for " << socket_.remote_endpoint().address().to_string()
              << ":" << socket_.remote_endpoint().port() << std::endl;
}

void AuthTcpSession::start() {
    std::cout << "AuthTcpSession started for " << socket_.remote_endpoint().address().to_string() << std::endl;
    do_read();
}

void AuthTcpSession::close_session(const std::string& reason) {
    if (socket_.is_open()) {
        std::cout << "Closing AuthTcpSession for "
                  << socket_.remote_endpoint().address().to_string() << ":" << socket_.remote_endpoint().port()
                  << ". Reason: " << reason << std::endl;
        boost::system::error_code ec;
        socket_.shutdown(tcp::socket::shutdown_both, ec);
        socket_.close(ec);
    }
}

void AuthTcpSession::do_read() {
    auto self(shared_from_this()); // Keep session alive
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
            std::cout << "AuthTCP Recv from " << socket_.remote_endpoint().address().to_string() << ": " << line << std::endl;
            process_json_request(line);
        }
        // Only continue reading if the socket is still open (process_json_request might close it via error)
        if (socket_.is_open()) {
            do_read();
        }
    } else if (error == boost::asio::error::eof) {
        close_session("Client disconnected (EOF).");
    } else if (error == boost::asio::error::connection_reset) {
        close_session("Client connection reset.");
    } else if (error == boost::asio::error::operation_aborted) {
        std::cout << "AuthTCP Read operation aborted." << std::endl;
    } else {
        std::cerr << "AuthTCP Read error: " << error.message() << std::endl;
        close_session("Read error.");
    }
}

void AuthTcpSession::process_json_request(const std::string& json_str) {
    json response_payload;
    try {
        json request_payload = json::parse(json_str);

        if (!request_payload.contains("action") || !request_payload.contains("username") || !request_payload.contains("password")) {
            response_payload = {
                {"status", "error"},
                {"message", "Missing required fields: action, username, password"}
            };
            do_write(response_payload.dump() + "\n");
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
        grpc::Status status;

        std::cout << "AuthTCP: Sending gRPC request for action '" << action << "' user '" << username << "'" << std::endl;

        if (action == "login") {
            status = grpc_stub_->AuthenticateUser(&context, grpc_request, &grpc_response);
        } else if (action == "register") {
            status = grpc_stub_->RegisterUser(&context, grpc_request, &grpc_response);
        } else {
            response_payload = {
                {"status", "error"},
                {"message", "Unknown action: " + action}
            };
            do_write(response_payload.dump() + "\n");
            return;
        }

        if (status.ok()) {
            response_payload = {
                {"status", grpc_response.authenticated() ? "success" : "failure"},
                {"message", grpc_response.message()},
                {"token", grpc_response.token()}
            };
            std::cout << "AuthTCP: gRPC call successful for action '" << action << "', user '" << username
                      << "'. Authenticated: " << grpc_response.authenticated() << std::endl;
        } else {
            std::cerr << "AuthTCP: gRPC call failed for action '" << action << "', user '" << username
                      << "'. Error: " << status.error_code() << ": " << status.error_message() << std::endl;
            response_payload = {
                {"status", "error"},
                {"message", "gRPC error (" + std::to_string(status.error_code()) + "): " + status.error_message()}
            };
        }

    } catch (const json::parse_error& e) {
        std::cerr << "AuthTCP: JSON parsing error: " << e.what() << " for request: " << json_str << std::endl;
        response_payload = {
            {"status", "error"},
            {"message", "Invalid JSON request: " + std::string(e.what())}
        };
    } catch (const std::exception& e) {
        std::cerr << "AuthTCP: Exception processing request: " << e.what() << " for request: " << json_str << std::endl;
        response_payload = {
            {"status", "error"},
            {"message", "Server error processing request: " + std::string(e.what())}
        };
    }

    do_write(response_payload.dump() + "\n");
}

void AuthTcpSession::do_write(const std::string& msg) {
    if (!socket_.is_open()) {
        std::cerr << "AuthTCP Write error: Socket is not open." << std::endl;
        return;
    }
    auto self(shared_from_this());
    boost::asio::async_write(socket_, boost::asio::buffer(msg.data(), msg.length()),
        [this, self](const boost::system::error_code& error, std::size_t length) {
            handle_write(error, length);
        });
}

void AuthTcpSession::handle_write(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        // std::cout << "AuthTCP Sent " << length << " bytes successfully." << std::endl;
    } else {
        std::cerr << "AuthTCP Write error: " << error.message() << std::endl;
        close_session("Write error.");
    }
}
