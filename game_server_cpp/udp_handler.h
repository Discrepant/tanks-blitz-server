#ifndef UDP_HANDLER_H
#define UDP_HANDLER_H

#include <boost/asio.hpp>
#include <nlohmann/json.hpp>
#include <iostream>
#include <string>
#include <vector>
#include <array>
#include <memory> // For std::shared_ptr

// RabbitMQ C AMQP client
#include <amqp.h>
#include <amqp_tcp_socket.h>

// #include "stubs.h" // No longer using stubs directly here
#include "session_manager.h" // Use actual SessionManager
#include "tank_pool.h"       // Use actual TankPool

using boost::asio::ip::udp;
using nlohmann::json;

class GameUDPHandler {
public:
    GameUDPHandler(boost::asio::io_context& io_context, short port,
                   SessionManager* session_manager, TankPool* tank_pool); // Changed to pointers
    ~GameUDPHandler();

    void send_message(const std::string& message, const udp::endpoint& target_endpoint);

private:
    void start_receive();
    void handle_receive(const boost::system::error_code& error, std::size_t bytes_transferred);
    void handle_send(const boost::system::error_code& error, std::size_t bytes_transferred);
    void process_message(const std::string& message_str, const udp::endpoint& sender_endpoint);

    // RabbitMQ specific methods
    bool setup_rabbitmq_connection();
    void publish_to_rabbitmq(const std::string& queue_name, const nlohmann::json& message_json);
    void close_rabbitmq_connection();

    // Message action handlers
    void handle_join_game(const nlohmann::json& msg, const udp::endpoint& sender_endpoint);
    void handle_move(const nlohmann::json& msg, const udp::endpoint& sender_endpoint);
    void handle_shoot(const nlohmann::json& msg, const udp::endpoint& sender_endpoint);
    void handle_leave_game(const nlohmann::json& msg, const udp::endpoint& sender_endpoint);

    udp::socket socket_;
    udp::endpoint sender_endpoint_;
    std::array<char, 1024> recv_buffer_;

    SessionManager* session_manager_; // Changed to pointer
    TankPool* tank_pool_;             // Changed to pointer

    // RabbitMQ connection state
    amqp_connection_state_t rabbitmq_conn_;
    bool rabbitmq_connected_ = false;

public: // Added public accessor for RMQ connection state
    amqp_connection_state_t get_rabbitmq_connection_state() const { return rabbitmq_conn_; }
    bool is_rabbitmq_connected() const { return rabbitmq_connected_; }
};

#endif // UDP_HANDLER_H
