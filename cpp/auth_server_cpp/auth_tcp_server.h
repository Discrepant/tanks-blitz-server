#ifndef AUTH_TCP_SERVER_H
#define AUTH_TCP_SERVER_H

#include <boost/asio.hpp>
#include <grpcpp/grpcpp.h> // Для grpc::Channel
#include <memory>           // Для std::shared_ptr
// #include "auth_tcp_session.h" // Предварительное объявление предпочтительнее, если возможно

using boost::asio::ip::tcp;

// Предварительное объявление
class AuthTcpSession;

class AuthTcpServer {
public:
    AuthTcpServer(boost::asio::io_context& io_context,
                  short port,
                  const std::string& grpc_server_address);

    // Удаленные конструктор копирования и оператор присваивания
    AuthTcpServer(const AuthTcpServer&) = delete;
    AuthTcpServer& operator=(const AuthTcpServer&) = delete;

private:
    void do_accept();
    void handle_accept(std::shared_ptr<AuthTcpSession> new_session,
                       const boost::system::error_code& error);

    tcp::acceptor acceptor_;
    std::shared_ptr<grpc::Channel> grpc_channel_; // Общий указатель на канал gRPC
};

#endif // AUTH_TCP_SERVER_H
