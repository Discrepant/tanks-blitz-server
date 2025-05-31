#include "auth_tcp_server.h"
#include <iostream>

AuthTcpServer::AuthTcpServer(boost::asio::io_context& io_context,
                             short port,
                             const std::string& grpc_server_address)
    : acceptor_(io_context, tcp::endpoint(tcp::v4(), port)) {

    std::cout << "AuthTcpServer: Initializing gRPC channel to: " << grpc_server_address << std::endl;
    grpc_channel_ = grpc::CreateChannel(grpc_server_address, grpc::InsecureChannelCredentials());

    // Optionally, check channel state immediately or before first use.
    // For example, try to connect or wait for ready.
    if (!grpc_channel_) {
        std::cerr << "AuthTcpServer FATAL: Failed to create gRPC channel." << std::endl;
        // Handle error appropriately, maybe throw an exception
        throw std::runtime_error("Failed to create gRPC channel to " + grpc_server_address);
    } else {
        // You can try to check connectivity here if needed, e.g.,
        // auto state = grpc_channel_->GetState(true); // true for try_to_connect
        // std::cout << "AuthTcpServer: gRPC channel state: " << state << std::endl;
        // if (state == GRPC_CHANNEL_FATAL_FAILURE) { ... }
         std::cout << "AuthTcpServer: gRPC channel created. TCP server listening on port " << port << std::endl;
    }

    do_accept();
}

void AuthTcpServer::do_accept() {
    auto new_socket = std::make_shared<tcp::socket>(acceptor_.get_executor().context());
    acceptor_.async_accept(*new_socket,
        [this, new_socket](const boost::system::error_code& error) {
            // Create a new session object here, inside the lambda, to pass the accepted socket.
            // The session object itself will be managed by a shared_ptr.
            auto new_session = std::make_shared<AuthTcpSession>(std::move(*new_socket), grpc_channel_);
            handle_accept(new_session, error);
        });
}

void AuthTcpServer::handle_accept(std::shared_ptr<AuthTcpSession> new_session,
                                  const boost::system::error_code& error) {
    if (!error) {
        std::cout << "AuthTcpServer: Accepted new connection from: "
                  << new_session->socket().remote_endpoint().address().to_string() << ":"
                  << new_session->socket().remote_endpoint().port() << std::endl;
        new_session->start();
    } else {
        std::cerr << "AuthTcpServer: Accept error: " << error.message() << std::endl;
    }

    // Continue listening for the next connection unless the error is critical
    if (error != boost::asio::error::operation_aborted) {
         do_accept();
    }
}
