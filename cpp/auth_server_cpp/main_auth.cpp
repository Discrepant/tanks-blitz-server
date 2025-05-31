#include "auth_tcp_server.h"
#include <iostream>
#include <boost/asio/signal_set.hpp> // For signal handling (SIGINT, SIGTERM)
#include <csignal> // For std::signal and signal constants (alternative to asio::signal_set)

// Global io_context pointer to allow signal handler to stop it.
// This is a common, simple way for console apps. More complex apps might use other patterns.
boost::asio::io_context* g_io_context_ptr = nullptr;

void signal_handler(int signal_number) {
    std::cout << "\nSignal " << signal_number << " received. Shutting down Auth TCP Server..." << std::endl;
    if (g_io_context_ptr) {
        g_io_context_ptr->stop();
    }
}

int main(int argc, char* argv[]) {
    short tcp_port = 9000;
    std::string grpc_server_address = "localhost:50051"; // Default Python gRPC Auth Service address

    // Allow overriding port and gRPC server address via command line arguments for flexibility
    if (argc >= 2) {
        try {
            tcp_port = static_cast<short>(std::stoi(argv[1]));
        } catch (const std::exception& e) {
            std::cerr << "Warning: Invalid port number '" << argv[1] << "'. Using default " << tcp_port << ". Error: " << e.what() << std::endl;
        }
    }
    if (argc >= 3) {
        grpc_server_address = argv[2];
    }

    std::cout << "Auth TCP Server (C++) starting..." << std::endl;
    std::cout << "  TCP Listening on port : " << tcp_port << std::endl;
    std::cout << "  gRPC Auth Service at  : " << grpc_server_address << std::endl;

    try {
        boost::asio::io_context io_context;
        g_io_context_ptr = &io_context; // Set global pointer for signal handler

        // Register signal handlers for graceful shutdown
        // Using boost::asio::signal_set is generally preferred with Asio applications.
        boost::asio::signal_set signals(io_context, SIGINT, SIGTERM);
        signals.async_wait([&io_context](const boost::system::error_code& /*error*/, int signal_num) {
            std::cout << "\nSignal " << signal_num << " received via asio::signal_set. Stopping io_context." << std::endl;
            io_context.stop();
        });
        // Fallback basic C-style signal handler (less ideal with ASIO but can work)
        // std::signal(SIGINT, signal_handler_c_style);
        // std::signal(SIGTERM, signal_handler_c_style);


        AuthTcpServer auth_server(io_context, tcp_port, grpc_server_address);

        std::cout << "Auth TCP Server initialized and listening. Press Ctrl+C to exit." << std::endl;

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
