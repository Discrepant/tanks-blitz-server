#ifndef COMMAND_CONSUMER_H
#define COMMAND_CONSUMER_H

#include <string>
#include <thread>
#include <atomic>
#include <vector> // Included for completeness, though not directly used in this header
#include <nlohmann/json.hpp>

// RabbitMQ C client
#include <rabbitmq-c/amqp.h>
#include <rabbitmq-c/tcp_socket.h> // For amqp_tcp_socket_new
#include <rabbitmq-c/framing.h>    // For amqp_cstring_bytes, amqp_empty_bytes, amqp_empty_table

// Forward declarations from our project
class SessionManager;
class TankPool;
// Note: Tank.h is not directly needed here if handle_command_logic only uses SessionManager/TankPool interfaces
// that then interact with Tanks. If it calls Tank methods directly, Tank.h would be needed.
// Based on the prompt, handle_command_logic will call tank->shoot() and tank->move(), so Tank.h is needed.
#include "tank.h"


class PlayerCommandConsumer {
public:
    PlayerCommandConsumer(SessionManager* sm,
                          TankPool* tp,
                          const std::string& host,
                          int port,
                          const std::string& user,
                          const std::string& password,
                          const std::string& vhost = "/");
    ~PlayerCommandConsumer();

    void start();
    void stop();
    bool is_running() const { return running_.load(); }

    // Deleted copy constructor and assignment operator
    PlayerCommandConsumer(const PlayerCommandConsumer&) = delete;
    PlayerCommandConsumer& operator=(const PlayerCommandConsumer&) = delete;

private:
    bool connect_to_rabbitmq();
    void disconnect_from_rabbitmq();
    void consume_loop();
    void process_amqp_message(amqp_envelope_t& envelope);
public: // Made public for testing
    bool handle_command_logic(const nlohmann::json& message_data);
private:
    SessionManager* session_manager_; // Raw pointer, lifetime managed externally
    TankPool* tank_pool_;             // Raw pointer, lifetime managed externally

    // RabbitMQ Connection parameters
    std::string rmq_host_;
    int rmq_port_;
    std::string rmq_user_;
    std::string rmq_pass_;
    std::string rmq_vhost_;

    amqp_connection_state_t rmq_conn_state_ = nullptr; // Initialize to nullptr
    // amqp_socket_t* rmq_socket_ = nullptr; // amqp_connection_state_t manages the socket internally after open

    std::atomic<bool> running_{false};
    std::thread consumer_thread_;

    static const std::string PLAYER_COMMANDS_QUEUE_NAME;
    static const int CHANNEL_ID = 1; // AMQP channel to use
};

#endif // COMMAND_CONSUMER_H
