#ifndef GAME_TCP_SESSION_H
#define GAME_TCP_SESSION_H

#include <boost/asio.hpp>
#include <string>
#include <vector>
#include <deque>
#include <iostream> // Included for consistency, though logging might be more in .cpp
#include <memory>   // For std::enable_shared_from_this, std::shared_ptr, std::unique_ptr
#include <nlohmann/json.hpp>

// AMQP (RabbitMQ)
#include <amqp.h>
// #include <amqp_tcp_socket.h> // Not directly used in session, connection state passed
#include <amqp_framing.h>    // For amqp_cstring_bytes etc. if used directly

// gRPC (Auth Service Client)
#include <grpcpp/grpcpp.h>
// Path to generated gRPC code for auth_service.proto
// This assumes a specific project structure where auth_server_cpp is a sibling to game_server_cpp,
// and protos target generates files accessible via this relative path.
// This will be resolved by CMake include directories.
#include "../../auth_server_cpp/grpc_generated/auth_service.grpc.pb.h"

// Forward declarations from our own project
class SessionManager;
class TankPool;
// class Tank; // Included via tank_pool.h or session_manager.h if they include it, or directly if needed.
// For PlayerInSessionData, Tank is needed.
#include "tank.h"


using boost::asio::ip::tcp;
using nlohmann::json;

// Forward declaration for AuthService for the Stub type
namespace auth {
    class AuthService;
}


class GameTCPSession : public std::enable_shared_from_this<GameTCPSession> {
public:
    GameTCPSession(tcp::socket socket,
                   SessionManager* sm,
                   TankPool* tp,
                   amqp_connection_state_t rabbitmq_conn_state, // For publishing game events via RabbitMQ
                   std::shared_ptr<grpc::Channel> grpc_auth_channel); // For authentication

    void start(); // Starts the session, typically by initiating a read operation

private:
    // Network operations
    void do_read();
    void handle_read(const boost::system::error_code& error, std::size_t length);
    void do_write(); // Manages sending messages from write_msgs_queue_
    void send_message(const std::string& msg); // Queues a message for sending
    void handle_write(const boost::system::error_code& error, std::size_t length);
    void close_session(const std::string& reason = "");

public: // Made public for testing
    void process_command(const std::string& line);
private:
    // Command Handlers
    void handle_login(const std::vector<std::string>& args);
    void handle_register(const std::vector<std::string>& args);
    void handle_move(const std::vector<std::string>& args);
    void handle_shoot(const std::vector<std::string>& args);
    void handle_say(const std::vector<std::string>& args);
    void handle_help(const std::vector<std::string>& args);
    void handle_players(const std::vector<std::string>& args);
    void handle_quit(const std::vector<std::string>& args);
    // Potentially other handlers: get_game_state, get_leaderboard, etc.

    // RabbitMQ Publishing
    void publish_to_rabbitmq_internal(const std::string& queue_name, const nlohmann::json& message_json);
    static const std::string RMQ_PLAYER_COMMANDS_QUEUE;
    static const std::string RMQ_CHAT_MESSAGES_QUEUE;


    // Member variables
    tcp::socket socket_;
    boost::asio::streambuf read_buffer_; // Buffer for incoming data
    std::deque<std::string> write_msgs_queue_; // Queue of outgoing messages

    // External services and managers (raw pointers, lifetime managed by main/server)
    SessionManager* session_manager_;
    TankPool* tank_pool_;
    amqp_connection_state_t rmq_conn_state_; // RabbitMQ connection state (not owned)
    std::unique_ptr<auth::AuthService::Stub> auth_grpc_stub_; // gRPC client stub for authentication

    // Player state
    std::string username_;           // Authenticated username
    std::string current_session_id_; // ID of the game session the player is in
    std::string assigned_tank_id_;   // ID of the tank assigned to this player
    bool authenticated_ = false;
};

#endif // GAME_TCP_SESSION_H
