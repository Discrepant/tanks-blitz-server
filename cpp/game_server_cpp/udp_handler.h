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
#include <rabbitmq-c/amqp.h>
#include <rabbitmq-c/tcp_socket.h>
#include <rabbitmq-c/framing.h> // For amqp_cstring_bytes etc.

#include "session_manager.h" // Actual SessionManager
#include "tank_pool.h"       // Actual TankPool

using boost::asio::ip::udp;
using nlohmann::json;

class GameUDPHandler {
public:
    GameUDPHandler(boost::asio::io_context& io_context,
                   short port,
                   SessionManager* sm,
                   TankPool* tp,
                   const std::string& rabbitmq_host,
                   int rabbitmq_port,
                   const std::string& rabbitmq_user,
                   const std::string& rabbitmq_pass,
                   const std::string& rabbitmq_vhost = "/");
    ~GameUDPHandler();

    bool is_rmq_connected() const { return rmq_connected_; }
    amqp_connection_state_t get_rmq_connection_state() const { return rmq_conn_state_; }

    // Call to start listening if not done in constructor, or for clarity.
    // If constructor calls internal_start_receive, this might not be needed publicly.
    // void start_listening();

private:
    void internal_start_receive();
    void handle_receive(const boost::system::error_code& error, std::size_t bytes_transferred);
public: // Made public for testing
    void process_message(const std::string& message_str, const udp::endpoint& remote_endpoint);
private:
    void send_json_response(const nlohmann::json& response_json, const udp::endpoint& target_endpoint);
    // Using shared_ptr for message body to keep it alive during async send
    void handle_send(std::shared_ptr<std::string> /*message_body_ptr*/,
                     const boost::system::error_code& error,
                     std::size_t /*bytes_transferred*/);

    // Action Handlers
    void handle_join_game(const json& msg, const udp::endpoint& sender_endpoint);
    void handle_move(const json& msg, const udp::endpoint& sender_endpoint);
    void handle_shoot(const json& msg, const udp::endpoint& sender_endpoint);
    void handle_leave_game(const json& msg, const udp::endpoint& sender_endpoint);

    // RabbitMQ specific methods
    bool setup_rabbitmq_connection();
    void publish_to_rabbitmq(const std::string& queue_name, const nlohmann::json& message_json);
    void close_rabbitmq_connection();

    udp::socket socket_;
    udp::endpoint sender_endpoint_; // Stores the endpoint of the last received message
    std::array<char, 1024> recv_buffer_;

    SessionManager* session_manager_; // Pointer to SessionManager singleton
    TankPool* tank_pool_;             // Pointer to TankPool singleton

    // RabbitMQ connection details and state
    std::string rmq_host_;
    int rmq_port_;
    std::string rmq_user_;
    std::string rmq_pass_;
    std::string rmq_vhost_;
    amqp_connection_state_t rmq_conn_state_;
    bool rmq_connected_ = false;

    static const std::string RMQ_PLAYER_COMMANDS_QUEUE;
};

#endif // UDP_HANDLER_H
