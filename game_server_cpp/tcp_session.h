#ifndef TCP_SESSION_H
#define TCP_SESSION_H

#include <boost/asio.hpp>
#include <nlohmann/json.hpp>
#include <iostream>
#include <string>
#include <vector>
#include <deque>
#include <memory> // For std::enable_shared_from_this

// #include "stubs.h" // No longer using stubs
#include "session_manager.h" // Use actual SessionManager
#include "tank_pool.h"       // Use actual TankPool
#include <amqp.h>  // For amqp_connection_state_t
#include <amqp_framing.h> // For amqp_cstring_bytes, amqp_empty_bytes etc.

using boost::asio::ip::tcp;
using nlohmann::json;

class GameTCPSession : public std::enable_shared_from_this<GameTCPSession> {
public:
    GameTCPSession(tcp::socket socket,
                   SessionManager* sm,         // Changed to pointer
                   TankPool* tp,             // Changed to pointer
                   amqp_connection_state_t rabbitmq_conn_state);

    void start();

private:
    void do_read();
    void handle_read(const boost::system::error_code& error, std::size_t length);
    void process_command(const std::string& line);

    void do_write(const std::string& msg);
    void handle_write(const boost::system::error_code& error, std::size_t length);

    void publish_to_rabbitmq_internal(const std::string& queue_name, const nlohmann::json& message_json);

    void close_session(const std::string& reason = "");

    // Command Handlers
    void handle_login(const std::vector<std::string>& args);
    void handle_register(const std::vector<std::string>& args);
    void handle_move(const std::vector<std::string>& args);
    void handle_shoot(const std::vector<std::string>& args);
    void handle_say(const std::vector<std::string>& args);
    void handle_help(const std::vector<std::string>& args);
    void handle_players(const std::vector<std::string>& args);
    void handle_quit(const std::vector<std::string>& args);
    // Add more command handlers as needed: e.g., get_game_state, get_leaderboard

    tcp::socket socket_;
    SessionManager* session_manager_; // Changed to pointer
    TankPool* tank_pool_;             // Changed to pointer
    amqp_connection_state_t rabbitmq_conn_state_;

    boost::asio::streambuf read_buffer_;
    std::deque<std::string> write_msgs_; // Queue for messages to write

    // Member variables for player and session state
    std::string username_;              // Username after successful login. Used as player_id for now.
    bool authenticated_ = false;
    std::string current_session_id_;    // Game session ID player is part of
    std::string assigned_tank_id_;      // Tank ID assigned to the player
    // std::string player_id_; // Effectively replaced by username_
    // std::string session_id_for_player_; // Replaced by current_session_id_
};

#endif // TCP_SESSION_H
