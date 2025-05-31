#include "auth_tcp_server.h"
#include <iostream>
#include <boost/asio/signal_set.hpp> // For signal handling (SIGINT, SIGTERM)
#include <csignal> // For std::signal and signal constants (alternative to asio::signal_set)

// Removed global io_context pointer and C-style signal handler for simplicity with asio::signal_set

int main(int argc, char* argv[]) {
    short tcp_port = 9000; // Default TCP listening port
    std::string grpc_server_address = "localhost:50051"; // Default Python gRPC Auth Service address

    // Basic command-line argument parsing
    // Usage: ./auth_server_app [tcp_listen_port] [grpc_auth_service_address]
    // Example: ./auth_server_app 9000 localhost:50051
    // Example for Docker: ./auth_server_app 9000 auth_server:50051 (where auth_server is Python gRPC service name)

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--port" && i + 1 < argc) {
            try {
                tcp_port = static_cast<short>(std::stoi(argv[++i]));
            } catch (const std::exception& e) {
                std::cerr << "Warning: Invalid value for --port '" << argv[i] << "'. Using default " << tcp_port << ". Error: " << e.what() << std::endl;
            }
        } else if (arg == "--grpc_addr" && i + 1 < argc) {
            grpc_server_address = argv[++i];
        } else if (arg == "--help") {
            std::cout << "Usage: " << argv[0] << " [--port <tcp_listen_port>] [--grpc_addr <grpc_auth_host:port>]" << std::endl;
            std::cout << "Defaults:" << std::endl;
            std::cout << "  --port " << tcp_port << std::endl;
            std::cout << "  --grpc_addr " << grpc_server_address << std::endl;
            return 0;
        }
    }
    // The old positional argument parsing is removed in favor of named arguments.
    // if (argc >= 2) {
    //     try {
    //         tcp_port = static_cast<short>(std::stoi(argv[1]));
    //     } catch (const std::exception& e) {
    //         std::cerr << "Warning: Invalid port number '" << argv[1] << "'. Using default " << tcp_port << ". Error: " << e.what() << std::endl;
    //     }
    // }
    // if (argc >= 3) {
    //     grpc_server_address = argv[2];
    // }


    std::cout << "Auth TCP Server (C++) starting..." << std::endl;
    std::cout << "  Config - TCP Listening on port : " << tcp_port << std::endl;
    std::cout << "  Config - gRPC Auth Service at  : " << grpc_server_address << std::endl;

    try {
        boost::asio::io_context io_context;

        // Setup signal handling for graceful shutdown
        boost::asio::signal_set signals(io_context, SIGINT, SIGTERM);
        signals.async_wait([&io_context](const boost::system::error_code& /*error*/, int signal_num) {
            std::cout << "\nSignal " << signal_num << " received. Auth TCP Server stopping io_context." << std::endl;
            io_context.stop();
        });

        AuthTcpServer auth_server(io_context, tcp_port, grpc_server_address);

        std::cout << "Auth TCP Server initialized and listening. Press Ctrl+C to exit." << std::endl;

        io_context.run();

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
