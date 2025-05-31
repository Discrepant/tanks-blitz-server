#ifndef TCP_HANDLER_H
#define TCP_HANDLER_H

#include <boost/asio.hpp>
#include <vector>
#include <memory> // For std::shared_ptr
#include "tcp_session.h"
// #include "stubs.h" // Stubs no longer used directly by GameTCPServer
#include "session_manager.h" // For SessionManager pointer
#include "tank_pool.h"       // For TankPool pointer
#include <amqp.h>            // For amqp_connection_state_t
#include <grpcpp/grpcpp.h>   // For grpc::Channel

using boost::asio::ip::tcp;

class GameTCPServer {
public:
    GameTCPServer(boost::asio::io_context& io_context, short port,
                  SessionManager* sm,
                  TankPool* tp,
                  amqp_connection_state_t rabbitmq_conn_state,
                  std::shared_ptr<grpc::Channel> grpc_auth_channel); // Added gRPC channel

private:
    void do_accept();
    void handle_accept(std::shared_ptr<GameTCPSession> new_session,
                       const boost::system::error_code& error);

    tcp::acceptor acceptor_;
    SessionManager* session_manager_; // Changed from stub to actual pointer
    TankPool* tank_pool_;             // Changed from stub to actual pointer
    amqp_connection_state_t rabbitmq_conn_state_;
    std::shared_ptr<grpc::Channel> grpc_auth_channel_; // Added gRPC channel member
};

#endif // TCP_HANDLER_H
