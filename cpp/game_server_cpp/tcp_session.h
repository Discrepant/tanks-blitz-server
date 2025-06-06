#ifndef GAME_TCP_SESSION_H
#define GAME_TCP_SESSION_H

#include <boost/asio.hpp>
#include <string>
#include <vector>
#include <deque>
#include <iostream> // Включено для согласованности, хотя логирование может быть больше в .cpp
#include <memory>   // Для std::enable_shared_from_this, std::shared_ptr, std::unique_ptr
#include <nlohmann/json.hpp>

// AMQP (RabbitMQ)
#include <rabbitmq-c/amqp.h>
// #include <amqp_tcp_socket.h> // Напрямую не используется в сессии, передается состояние соединения
#include <rabbitmq-c/framing.h>    // Для amqp_cstring_bytes и т.д., если используется напрямую

// gRPC (Клиент сервиса аутентификации)
#include <grpcpp/grpcpp.h>
// Путь к сгенерированному gRPC коду для auth_service.proto
// Это предполагает определенную структуру проекта, где auth_server_cpp является соседним с game_server_cpp,
// и цель protos генерирует файлы, доступные по этому относительному пути.
// Это будет разрешено через include директории CMake.
#include "auth_service.grpc.pb.h"

// Предварительные объявления из нашего собственного проекта
class SessionManager;
class TankPool;
// class Tank; // Включается через tank_pool.h или session_manager.h, если они его включают, или напрямую при необходимости.
// Для PlayerInSessionData, Tank необходим.
#include "tank.h"


using boost::asio::ip::tcp;
using nlohmann::json;

// Предварительное объявление для AuthService для типа Stub
namespace auth {
    class AuthService;
}


class GameTCPSession : public std::enable_shared_from_this<GameTCPSession> {
public:
    GameTCPSession(tcp::socket socket,
                   SessionManager* sm,
                   TankPool* tp,
                   amqp_connection_state_t rabbitmq_conn_state, // Для публикации игровых событий через RabbitMQ
                   std::shared_ptr<grpc::Channel> grpc_auth_channel); // Для аутентификации

    void start(); // Запускает сессию, обычно инициируя операцию чтения

private:
    // Сетевые операции
    void do_read();
    void handle_read(const boost::system::error_code& error, std::size_t length);
    void do_write(); // Управляет отправкой сообщений из write_msgs_queue_
    void send_message(const std::string& msg); // Помещает сообщение в очередь для отправки
    void handle_write(const boost::system::error_code& error, std::size_t length);
    void close_session(const std::string& reason = "");

public: // Сделано публичным для тестирования
    void process_command(const std::string& line);
private:
    // Обработчики команд
    void handle_login(const std::vector<std::string>& args);
    void handle_register(const std::vector<std::string>& args);
    void handle_move(const std::vector<std::string>& args);
    void handle_shoot(const std::vector<std::string>& args);
    void handle_say(const std::vector<std::string>& args);
    void handle_help(const std::vector<std::string>& args);
    void handle_players(const std::vector<std::string>& args);
    void handle_quit(const std::vector<std::string>& args);
    // Потенциально другие обработчики: get_game_state, get_leaderboard и т.д.

    // Публикация в RabbitMQ
    void publish_to_rabbitmq_internal(const std::string& queue_name, const nlohmann::json& message_json);
    static const std::string RMQ_PLAYER_COMMANDS_QUEUE;
    static const std::string RMQ_CHAT_MESSAGES_QUEUE;


    // Члены-переменные
    tcp::socket socket_;
    boost::asio::streambuf read_buffer_; // Буфер для входящих данных
    std::deque<std::string> write_msgs_queue_; // Очередь исходящих сообщений

    // Внешние сервисы и менеджеры (сырые указатели, время жизни управляется main/server)
    SessionManager* session_manager_;
    TankPool* tank_pool_;
    amqp_connection_state_t rmq_conn_state_; // Состояние соединения RabbitMQ (не владеет)
    std::unique_ptr<auth::AuthService::Stub> auth_grpc_stub_; // Клиентская заглушка gRPC для аутентификации

    // Состояние игрока
    std::string username_;           // Аутентифицированное имя пользователя
    std::string current_session_id_; // ID игровой сессии, в которой находится игрок
    std::string assigned_tank_id_;   // ID танка, назначенного этому игроку
    bool authenticated_ = false;
};

#endif // GAME_TCP_SESSION_H
