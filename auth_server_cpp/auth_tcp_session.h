#ifndef AUTH_TCP_SESSION_H
#define AUTH_TCP_SESSION_H

#include <boost/asio.hpp>
#include <nlohmann/json.hpp>
#include <grpcpp/grpcpp.h> // For gRPC
#include "grpc_generated/auth_service.grpc.pb.h" // Generated gRPC code
#include <iostream>
#include <string>
#include <memory> // For std::enable_shared_from_this, std::shared_ptr, std::unique_ptr

using boost::asio::ip::tcp;
using nlohmann::json;

// Forward declaration of AuthService for the Stub
namespace auth {
    class AuthService;
}

class AuthTcpSession : public std::enable_shared_from_this<AuthTcpSession> {
public:
    AuthTcpSession(tcp::socket socket, std::shared_ptr<grpc::Channel> grpc_channel);
    void start();

private:
    void do_read();
    void handle_read(const boost::system::error_code& error, std::size_t length);
    void process_json_request(const std::string& json_str);
    void do_write(const std::string& msg);
    void handle_write(const boost::system::error_code& error, std::size_t length); // Added handle_write
    void close_session(const std::string& reason = "");


    tcp::socket socket_;
    boost::asio::streambuf read_buffer_;
    std::unique_ptr<auth::AuthService::Stub> grpc_stub_; // gRPC client stub
};

#endif // AUTH_TCP_SESSION_H
