#ifndef AUTH_TCP_SERVER_H
#define AUTH_TCP_SERVER_H

#include <boost/asio.hpp>
#include <grpcpp/grpcpp.h> // For grpc::Channel
#include <memory> // For std::shared_ptr
#include "auth_tcp_session.h" // Forward declare or include fully

using boost::asio::ip::tcp;

class AuthTcpServer {
public:
    AuthTcpServer(boost::asio::io_context& io_context,
                  short port,
                  const std::string& grpc_server_address);

private:
    void do_accept();
    void handle_accept(std::shared_ptr<AuthTcpSession> new_session,
                       const boost::system::error_code& error);

    tcp::acceptor acceptor_;
    std::shared_ptr<grpc::Channel> grpc_channel_; // Shared pointer to the gRPC channel
};

#endif // AUTH_TCP_SERVER_H
