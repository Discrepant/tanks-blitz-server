#include "tcp_handler.h"
#include "tcp_session.h" // Полное определение GameTCPSession
#include <iostream>

GameTCPServer::GameTCPServer(boost::asio::io_context& io_context,
                             short port,
                             SessionManager* sm,
                             TankPool* tp,
                             amqp_connection_state_t rabbitmq_conn_state,
                             std::shared_ptr<grpc::Channel> grpc_auth_channel)
    : acceptor_(io_context, tcp::endpoint(tcp::v4(), port)),
      session_manager_(sm),
      tank_pool_(tp),
      rmq_conn_state_(rabbitmq_conn_state),
      grpc_auth_channel_(grpc_auth_channel) {

    if (!session_manager_ || !tank_pool_) {
         std::cerr << "GameTCPServer FATAL: SessionManager or TankPool is null. Server cannot function correctly." << std::endl;
         // Рассмотрите возможность выброса исключения для остановки запуска сервера, если отсутствуют критические зависимости
    }
    if (!grpc_auth_channel_) {
        std::cerr << "GameTCPServer WARNING: gRPC Auth Channel is null. Authentication in TCP sessions will fail." << std::endl;
    }
    if (!rmq_conn_state_) { // Примечание: amqp_connection_state_t - это тип указателя
        std::cerr << "GameTCPServer WARNING: RabbitMQ connection state is null. RabbitMQ features in TCP sessions will fail." << std::endl;
    }

    std::cout << "GameTCPServer: Initializing on port " << port << std::endl;
    do_accept();
}

void GameTCPServer::do_accept() {
    // Создаем новый сокет для следующего входящего соединения.
    auto new_socket = std::make_shared<tcp::socket>(acceptor_.get_executor());

    acceptor_.async_accept(*new_socket,
        [this, new_socket](const boost::system::error_code& error) {
            // Создаем новый объект сессии, передавая все необходимые зависимости.
            auto new_session = std::make_shared<GameTCPSession>(std::move(*new_socket),
                                                                this->session_manager_,
                                                                this->tank_pool_,
                                                                this->rmq_conn_state_,
                                                                this->grpc_auth_channel_);
            handle_accept(new_session, error);
        });
}

void GameTCPServer::handle_accept(std::shared_ptr<GameTCPSession> new_session,
                                  const boost::system::error_code& error) {
    if (!error) {
        // std::cout << "GameTCPServer: Accepted new game connection from: "
        //           << new_session->socket().remote_endpoint().address().to_string() << ":"
        //           << new_session->socket().remote_endpoint().port() << std::endl; // Принято новое игровое соединение от...
        new_session->start(); // Запускаем сессию (отправляет подтверждение, начинает чтение)
    } else {
        std::cerr << "GameTCPServer: Accept error: " << error.message() << std::endl;
        // Если accept завершается неудачно, возможно, мы захотим остановить сервер или залогировать и продолжить.
        // Пока просто логируем. Если это исправимая ошибка, do_accept будет вызван снова.
    }

    // Продолжаем слушать следующее соединение, если ошибка не критическая (например, operation_aborted)
    if (error != boost::asio::error::operation_aborted) {
         do_accept();
    }
}
