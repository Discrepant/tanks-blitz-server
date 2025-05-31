#ifndef GAME_TCP_HANDLER_H // Renamed from TCP_HANDLER_H to avoid potential conflicts if an old one existed
#define GAME_TCP_HANDLER_H

#include <boost/asio.hpp>
#include <vector>   // Though not directly used in this header, often useful for server logic
#include <memory>   // For std::shared_ptr

// Forward declarations
class GameTCPSession; // Defined in tcp_session.h
class SessionManager;
class TankPool;
namespace grpc { class Channel; } // Forward declare grpc::Channel
struct amqp_connection_state; // Forward declare AMQP connection state struct (pointer type is amqp_connection_state_t)


using boost::asio::ip::tcp;

class GameTCPServer {
public:
    GameTCPServer(boost::asio::io_context& io_context,
                  short port,
                  SessionManager* sm,
                  TankPool* tp,
                  amqp_connection_state_t rabbitmq_conn_state, // Pass AMQP connection state for sessions
                  std::shared_ptr<grpc::Channel> grpc_auth_channel); // Pass gRPC channel for auth

    // Deleted copy constructor and assignment operator
    GameTCPServer(const GameTCPServer&) = delete;
    GameTCPServer& operator=(const GameTCPServer&) = delete;

private:
    void do_accept();
    void handle_accept(std::shared_ptr<GameTCPSession> new_session,
                       const boost::system::error_code& error);

    tcp::acceptor acceptor_;

    // Pointers to shared resources, lifetime managed externally (e.g., by main)
    SessionManager* session_manager_;
    TankPool* tank_pool_;
    amqp_connection_state_t rmq_conn_state_; // For passing to new GameTCPSessions
    std::shared_ptr<grpc::Channel> grpc_auth_channel_; // For passing to new GameTCPSessions
};

#endif // GAME_TCP_HANDLER_H
