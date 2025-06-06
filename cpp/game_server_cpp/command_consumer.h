#ifndef COMMAND_CONSUMER_H
#define COMMAND_CONSUMER_H

#include <string>
#include <thread>
#include <atomic>
#include <vector> // Включен для полноты, хотя напрямую не используется в этом заголовке
#include <nlohmann/json.hpp>

// C-клиент RabbitMQ
#include <rabbitmq-c/amqp.h>
#include <rabbitmq-c/tcp_socket.h> // Для amqp_tcp_socket_new
#include <rabbitmq-c/framing.h>    // Для amqp_cstring_bytes, amqp_empty_bytes, amqp_empty_table

// Предварительные объявления из нашего проекта
class SessionManager;
class TankPool;
// Примечание: Tank.h здесь напрямую не нужен, если handle_command_logic использует только интерфейсы SessionManager/TankPool,
// которые затем взаимодействуют с танками. Если он вызывает методы Tank напрямую, Tank.h был бы необходим.
// Исходя из задания, handle_command_logic будет вызывать tank->shoot() и tank->move(), поэтому Tank.h нужен.
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

    // Удаленные конструктор копирования и оператор присваивания
    PlayerCommandConsumer(const PlayerCommandConsumer&) = delete;
    PlayerCommandConsumer& operator=(const PlayerCommandConsumer&) = delete;

private:
    bool connect_to_rabbitmq();
    void disconnect_from_rabbitmq();
    void consume_loop();
    void process_amqp_message(amqp_envelope_t& envelope);
public: // Сделано публичным для тестирования
    bool handle_command_logic(const nlohmann::json& message_data);
private:
    SessionManager* session_manager_; // Сырой указатель, время жизни управляется извне
    TankPool* tank_pool_;             // Сырой указатель, время жизни управляется извне

    // Параметры подключения RabbitMQ
    std::string rmq_host_;
    int rmq_port_;
    std::string rmq_user_;
    std::string rmq_pass_;
    std::string rmq_vhost_;

    amqp_connection_state_t rmq_conn_state_ = nullptr; // Инициализируем как nullptr
    // amqp_socket_t* rmq_socket_ = nullptr; // amqp_connection_state_t управляет сокетом внутренне после открытия

    std::atomic<bool> running_{false};
    std::thread consumer_thread_;

    static const std::string PLAYER_COMMANDS_QUEUE_NAME;
    static const int CHANNEL_ID = 1; // Используемый канал AMQP
};

#endif // COMMAND_CONSUMER_H
