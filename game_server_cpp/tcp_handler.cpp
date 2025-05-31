#include "tcp_handler.h"
#include <iostream>

GameTCPServer::GameTCPServer(boost::asio::io_context& io_context, short port,
                             SessionManagerStub& sm_stub,
                             TankPoolStub& tp_stub,
                             amqp_connection_state_t rabbitmq_conn_state)
    : acceptor_(io_context, tcp::endpoint(tcp::v4(), port)),
      session_manager_stub_(sm_stub),
      tank_pool_stub_(tp_stub),
      rabbitmq_conn_state_(rabbitmq_conn_state) {
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
                                                                session_manager_stub_,
                                                                tank_pool_stub_,
                                                                rabbitmq_conn_state_);
            handle_accept(new_session, error);
        });
}

void GameTCPServer::handle_accept(std::shared_ptr<GameTCPSession> new_session,
                                  const boost::system::error_code& error) {
    if (!error) {
        std::cout << "Accepted new TCP connection from: "
                  << new_session->socket().remote_endpoint().address().to_string() << ":"
                  << new_session->socket().remote_endpoint().port() << std::endl;
        new_session->start(); // Start the session (sends ack, starts reading)
    } else {
        std::cerr << "TCP Accept error: " << error.message() << std::endl;
        // If accept fails, we might want to stop the server or log and continue.
        // For now, just log. If it's a recoverable error, do_accept will be called again.
        // If it's a fatal error (e.g. out of file descriptors), the server might struggle.
    }

    // Continue listening for the next connection unless the error is critical
    // For some errors (like operation_aborted if acceptor is closed), we might not want to continue.
    if (error != boost::asio::error::operation_aborted) {
         do_accept();
    }
}
