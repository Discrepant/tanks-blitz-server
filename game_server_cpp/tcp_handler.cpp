#include "tcp_handler.h"
#include <iostream>

GameTCPServer::GameTCPServer(boost::asio::io_context& io_context, short port,
                             SessionManager* sm,
                             TankPool* tp,
                             amqp_connection_state_t rabbitmq_conn_state,
                             std::shared_ptr<grpc::Channel> grpc_auth_channel) // Added gRPC channel
    : acceptor_(io_context, tcp::endpoint(tcp::v4(), port)),
      session_manager_(sm),   // Store actual manager pointer
      tank_pool_(tp),         // Store actual pool pointer
      rabbitmq_conn_state_(rabbitmq_conn_state),
      grpc_auth_channel_(grpc_auth_channel) { // Store gRPC channel
    std::cout << "TCP Server initializing on port " << port << std::endl;
    do_accept();
}

void GameTCPServer::do_accept() {
    // Create a new socket for the next incoming connection.
    // Note: The acceptor's io_context is used to create the socket.
    auto new_socket = std::make_shared<tcp::socket>(acceptor_.get_executor().context());

    acceptor_.async_accept(*new_socket,
        [this, new_socket](const boost::system::error_code& error) {
            // Create a new session object here, inside the lambda, to pass the accepted socket.
            // The session object itself will be managed by a shared_ptr.
            auto new_session = std::make_shared<GameTCPSession>(std::move(*new_socket),
                                                                session_manager_, // Pass pointer
                                                                tank_pool_,       // Pass pointer
                                                                rabbitmq_conn_state_,
                                                                grpc_auth_channel_); // Pass gRPC channel
            handle_accept(new_session, error);
        });
}

void GameTCPServer::handle_accept(std::shared_ptr<GameTCPSession> new_session,
                                  const boost::system::error_code& error) {
    if (!error) {
        std::cout << "GameTCPServer: Accepted new game connection from: "
                  << new_session->socket().remote_endpoint().address().to_string() << ":"
                  << new_session->socket().remote_endpoint().port() << std::endl;
        new_session->start();
    } else {
        std::cerr << "GameTCPServer: Accept error: " << error.message() << std::endl;
    }

    if (error != boost::asio::error::operation_aborted) {
         do_accept();
    }
}
