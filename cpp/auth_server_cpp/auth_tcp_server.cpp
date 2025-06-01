#include "auth_tcp_server.h"
#include "auth_tcp_session.h" // Full definition of AuthTcpSession
#include <iostream>
#include <stdexcept> // For std::runtime_error

AuthTcpServer::AuthTcpServer(boost::asio::io_context& io_context,
                             short port,
                             const std::string& grpc_server_address)
    : acceptor_(io_context, tcp::endpoint(tcp::v4(), port)) {

    std::cout << "AuthTcpServer: Initializing... Attempting to create gRPC channel to: " << grpc_server_address << std::endl;
    grpc_channel_ = grpc::CreateChannel(grpc_server_address, grpc::InsecureChannelCredentials());

    if (!grpc_channel_) {
        std::cerr << "AuthTcpServer FATAL: Failed to create gRPC channel to '" << grpc_server_address
                  << "'. The server will not be able to process authentication requests." << std::endl;
        // This is a critical failure. The application should likely terminate or enter a degraded state.
        throw std::runtime_error("Failed to create gRPC channel for AuthTcpServer to " + grpc_server_address);
    } else {
        // Optional: Check initial channel state.
        // auto initial_state = grpc_channel_->GetState(false); // Don't try to connect yet
        // std::cout << "AuthTcpServer: gRPC channel initial state: " << static_cast<int>(initial_state) << std::endl;
        // A more robust check would be to try to connect or wait for ready with a timeout,
        // but this can block startup. For now, assume CreateChannel is enough and errors handled per-call.
         std::cout << "AuthTcpServer: gRPC channel created. TCP server listening on port " << port << std::endl;
    }

    do_accept();
}

void AuthTcpServer::do_accept() {
    // Create a new socket for the next incoming connection.
    auto new_socket = std::make_shared<tcp::socket>(acceptor_.get_executor());

    acceptor_.async_accept(*new_socket,
        [this, new_socket](const boost::system::error_code& error) {
            // Create the session, passing the moved socket and the gRPC channel
            auto new_session = std::make_shared<AuthTcpSession>(std::move(*new_socket), grpc_channel_);
            handle_accept(new_session, error);
        });
}

void AuthTcpServer::handle_accept(std::shared_ptr<AuthTcpSession> new_session,
                                  const boost::system::error_code& error) {
    if (!error) {
        // std::cout << "AuthTcpServer: Accepted new auth connection from: "
        //           << new_session->socket().remote_endpoint().address().to_string() << ":"  // socket() is private
        //           << new_session->socket().remote_endpoint().port() << std::endl;
        // AuthTcpSession doesn't expose socket() publicly, so direct logging of remote_endpoint here is harder.
        // Logging can be done within AuthTcpSession::start() or constructor.
        new_session->start();
    } else {
        std::cerr << "AuthTcpServer: Accept error: " << error.message() << std::endl;
        // If accept fails, we might want to stop the server or log and continue.
        // For now, just log. If it's a recoverable error, do_accept will be called again by the logic below.
    }

    // Continue listening for the next connection unless the error is critical (e.g. operation_aborted)
    if (error != boost::asio::error::operation_aborted) {
         do_accept();
    }
}
