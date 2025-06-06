#ifndef GAME_TCP_HANDLER_H // Переименовано из TCP_HANDLER_H во избежание потенциальных конфликтов, если старый файл существовал
#define GAME_TCP_HANDLER_H

#include <rabbitmq-c/amqp.h>  // Для amqp_connection_state_t и других типов AMQP
#include <boost/asio.hpp>
#include <vector>   // Хотя напрямую не используется в этом заголовке, часто полезно для серверной логики
#include <memory>   // Для std::shared_ptr

// Предварительные объявления
class GameTCPSession; // Определен в tcp_session.h
class SessionManager;
class TankPool;
namespace grpc { class Channel; } // Предварительное объявление grpc::Channel
// struct amqp_connection_state; // Предварительное объявление структуры состояния соединения AMQP (тип указателя - amqp_connection_state_t)


using boost::asio::ip::tcp;

class GameTCPServer {
public:
    GameTCPServer(boost::asio::io_context& io_context,
                  short port,
                  SessionManager* sm,
                  TankPool* tp,
                  amqp_connection_state_t rabbitmq_conn_state, // Передача состояния соединения AMQP для сессий
                  std::shared_ptr<grpc::Channel> grpc_auth_channel); // Передача канала gRPC для аутентификации

    // Удаленные конструктор копирования и оператор присваивания
    GameTCPServer(const GameTCPServer&) = delete;
    GameTCPServer& operator=(const GameTCPServer&) = delete;

private:
    void do_accept();
    void handle_accept(std::shared_ptr<GameTCPSession> new_session,
                       const boost::system::error_code& error);

    tcp::acceptor acceptor_;

    // Указатели на общие ресурсы, время жизни управляется извне (например, main)
    SessionManager* session_manager_;
    TankPool* tank_pool_;
    amqp_connection_state_t rmq_conn_state_; // Для передачи новым GameTCPSessions
    std::shared_ptr<grpc::Channel> grpc_auth_channel_; // Для передачи новым GameTCPSessions
};

#endif // GAME_TCP_HANDLER_H
