#include "auth_tcp_server.h"
#include "auth_tcp_session.h" // Полное определение AuthTcpSession
#include <iostream>
#include <stdexcept> // Для std::runtime_error

AuthTcpServer::AuthTcpServer(boost::asio::io_context& io_context,
                             short port,
                             const std::string& grpc_server_address)
    : acceptor_(io_context, tcp::endpoint(tcp::v4(), port)) {

    std::cout << "AuthTcpServer: Initializing... Attempting to create gRPC channel to: " << grpc_server_address << std::endl;
    grpc_channel_ = grpc::CreateChannel(grpc_server_address, grpc::InsecureChannelCredentials());

    if (!grpc_channel_) {
        std::cerr << "AuthTcpServer FATAL: Failed to create gRPC channel to '" << grpc_server_address
                  << "'. The server will not be able to process authentication requests." << std::endl;
        // Это критическая ошибка. Приложение, скорее всего, должно завершиться или перейти в состояние ограниченной функциональности.
        throw std::runtime_error("Failed to create gRPC channel for AuthTcpServer to " + grpc_server_address);
    } else {
        // Опционально: Проверка начального состояния канала.
        // auto initial_state = grpc_channel_->GetState(false); // Пока не пытаться подключиться
        // std::cout << "AuthTcpServer: gRPC channel initial state: " << static_cast<int>(initial_state) << std::endl;
        // Более надежная проверка - попытаться подключиться или дождаться готовности с таймаутом,
        // но это может заблокировать запуск. Пока предполагаем, что CreateChannel достаточно, и ошибки обрабатываются при каждом вызове.
         std::cout << "AuthTcpServer: gRPC channel created. TCP server listening on port " << port << std::endl;
    }

    do_accept();
}

void AuthTcpServer::do_accept() {
    // Создаем новый сокет для следующего входящего соединения.
    auto new_socket = std::make_shared<tcp::socket>(acceptor_.get_executor());

    acceptor_.async_accept(*new_socket,
        [this, new_socket](const boost::system::error_code& error) {
            // Создаем сессию, передавая перемещенный сокет и канал gRPC
            auto new_session = std::make_shared<AuthTcpSession>(std::move(*new_socket), grpc_channel_);
            handle_accept(new_session, error);
        });
}

void AuthTcpServer::handle_accept(std::shared_ptr<AuthTcpSession> new_session,
                                  const boost::system::error_code& error) {
    if (!error) {
        // std::cout << "AuthTcpServer: Accepted new auth connection from: "
        //           << new_session->socket().remote_endpoint().address().to_string() << ":"  // socket() является приватным
        //           << new_session->socket().remote_endpoint().port() << std::endl;
        // AuthTcpSession не предоставляет публичный доступ к socket(), поэтому прямое логирование remote_endpoint здесь затруднено.
        // Логирование можно выполнить внутри AuthTcpSession::start() или в конструкторе.
        new_session->start();
    } else {
        std::cerr << "AuthTcpServer: Accept error: " << error.message() << std::endl;
        // Если accept завершается неудачно, возможно, мы захотим остановить сервер или залогировать и продолжить.
        // Пока просто логируем. Если это исправимая ошибка, do_accept будет вызван снова логикой ниже.
    }

    // Продолжаем слушать следующее соединение, если ошибка не критическая (например, operation_aborted)
    if (error != boost::asio::error::operation_aborted) {
         do_accept();
    }
}
