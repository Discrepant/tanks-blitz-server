#ifndef COMMAND_CONSUMER_H
#define COMMAND_CONSUMER_H

#include <string>
#include <thread>
#include <atomic>
#include <nlohmann/json.hpp>

// RabbitMQ C client
#include <amqp.h>
#include <amqp_tcp_socket.h>
// For amqp_cstring_bytes, amqp_empty_bytes, amqp_empty_table if not included by above
#include <amqp_framing.h>

#include "session_manager.h" // Assuming SessionManager is defined
#include "tank_pool.h"       // Assuming TankPool is defined

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

    void start(); // Renamed from start_consuming
    void stop();  // Renamed from stop_consuming

    // Deleted copy constructor and assignment operator
    PlayerCommandConsumer(const PlayerCommandConsumer&) = delete;
    PlayerCommandConsumer& operator=(const PlayerCommandConsumer&) = delete;

private:
    bool connect();
    void disconnect();
    void consume_loop();
    void process_message_body(const amqp_bytes_t& body);

    SessionManager* session_manager_; // Raw pointer, lifetime managed externally
    TankPool* tank_pool_;             // Raw pointer, lifetime managed externally

    // RabbitMQ Connection parameters
    std::string rabbitmq_host_;
    int rabbitmq_port_;
    std::string rabbitmq_user_;
    std::string rabbitmq_password_;
    std::string rabbitmq_vhost_;

    amqp_connection_state_t conn_state_;
    // amqp_socket_t* socket_ = nullptr; // amqp_connection_state_t includes socket state internally after amqp_socket_open

    std::atomic<bool> running_{false};
    std::thread consumer_thread_;

    static const std::string PLAYER_COMMANDS_QUEUE_NAME;
};

#endif // COMMAND_CONSUMER_H
