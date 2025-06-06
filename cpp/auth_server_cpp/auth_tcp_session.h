#ifndef AUTH_TCP_SESSION_H
#define AUTH_TCP_SESSION_H

#include <boost/asio.hpp>
#include <nlohmann/json.hpp>
#include <grpcpp/grpcpp.h>
#include "auth_service.grpc.pb.h" // Сгенерированный gRPC код (из цели protos)
#include <iostream>
#include <string>
#include <memory> // Для std::enable_shared_from_this, std::shared_ptr, std::unique_ptr
#include <deque>  // Для write_msgs_queue_ (очереди сообщений для записи)

using boost::asio::ip::tcp;
using nlohmann::json;

// Предварительное объявление AuthService для заглушки (Stub) (уже есть в auth_service.grpc.pb.h, но хорошая практика, если нужна только заглушка)
// namespace auth {
//     class AuthService;
// }

class AuthTcpSession : public std::enable_shared_from_this<AuthTcpSession> {
public:
    AuthTcpSession(tcp::socket socket, std::shared_ptr<grpc::Channel> grpc_channel);
    void start();

private:
    void do_read();
    void handle_read(const boost::system::error_code& error, std::size_t length);
public: // Сделано публичным для тестирования
    void process_json_request(const std::string& json_str);
private:
    void send_response(const std::string& msg); // Помещает сообщение в очередь и запускает цепочку записи, если она не активна
    void do_write(); // Записывает первое сообщение из очереди
    void handle_write(const boost::system::error_code& error, std::size_t length);

    void close_session(const std::string& reason = "");


    tcp::socket socket_;
    boost::asio::streambuf read_buffer_;
    std::unique_ptr<auth::AuthService::Stub> grpc_stub_; // Клиентская заглушка gRPC
    std::deque<std::string> write_msgs_queue_; // Очередь для исходящих сообщений
};

#endif // AUTH_TCP_SESSION_H
