#ifndef AUTH_TCP_SESSION_H
#define AUTH_TCP_SESSION_H

#include <boost/asio.hpp>
#include <nlohmann/json.hpp>
#include <grpcpp/grpcpp.h>
#include "auth_service.grpc.pb.h" // Generated gRPC code (from protos target)
#include <iostream>
#include <string>
#include <memory> // For std::enable_shared_from_this, std::shared_ptr, std::unique_ptr
#include <deque>  // For write_msgs_queue_

using boost::asio::ip::tcp;
using nlohmann::json;

// Forward declaration of AuthService for the Stub (already in auth_service.grpc.pb.h but good practice if only stub was needed)
// namespace auth {
//     class AuthService;
// }

class AuthTcpSession : public std::enable_shared_from_this<AuthTcpSession> {
public:
    AuthTcpSession(tcp::socket socket, std::shared_ptr<grpc::Channel> grpc_channel);
    void start();

private:
    void do_read();
    void handle_read(const boost::system::error_code& error, std::size_t length);
public: // Made public for testing
    void process_json_request(const std::string& json_str);
private:
    void send_response(const std::string& msg); // Queues message and starts write chain if not active
    void do_write(); // Writes the front message from the queue
    void handle_write(const boost::system::error_code& error, std::size_t length);

    void close_session(const std::string& reason = "");


    tcp::socket socket_;
    boost::asio::streambuf read_buffer_;
    std::unique_ptr<auth::AuthService::Stub> grpc_stub_; // gRPC client stub
    std::deque<std::string> write_msgs_queue_; // Queue for outgoing messages
};

#endif // AUTH_TCP_SESSION_H
