#include "auth_tcp_server.h"
#include <iostream>
#include <boost/asio/signal_set.hpp> // For signal handling

int main() {
    const short tcp_port = 9000;
    const std::string grpc_server_address = "localhost:50051"; // Python gRPC server address

    try {
        std::cout << "Auth TCP Server (C++) starting..." << std::endl;
        boost::asio::io_context io_context;

        // Setup signal handling for graceful shutdown
        boost::asio::signal_set signals(io_context, SIGINT, SIGTERM);
        signals.async_wait([&io_context](const boost::system::error_code& /*error*/, int /*signal_number*/) {
            std::cout << "Signal received, stopping Auth TCP Server..." << std::endl;
            io_context.stop();
        });

        AuthTcpServer auth_server(io_context, tcp_port, grpc_server_address);

        std::cout << "Auth TCP Server listening on port " << tcp_port
                  << ", connected to gRPC Auth Service at " << grpc_server_address << std::endl;
        std::cout << "Press Ctrl+C to exit." << std::endl;

        io_context.run(); // This will block until io_context.stop() is called

        std::cout << "Auth TCP Server shut down gracefully." << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "Critical Error in Auth TCP Server main: " << e.what() << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "Unknown critical error in Auth TCP Server main." << std::endl;
        return 2;
    }

    return 0;
}
