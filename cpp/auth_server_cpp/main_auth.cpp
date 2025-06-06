#include "auth_tcp_server.h"
#include <iostream>
#include <boost/asio/signal_set.hpp> // Для обработки сигналов (SIGINT, SIGTERM)
#include <csignal> // Для std::signal и констант сигналов (альтернатива asio::signal_set)

// Удален глобальный указатель io_context и обработчик сигналов в стиле C для простоты с asio::signal_set

int main(int argc, char* argv[]) {
    short tcp_port = 9000; // Порт TCP для прослушивания по умолчанию
    std::string grpc_server_address = "localhost:50051"; // Адрес Python gRPC Auth Service по умолчанию

    // Базовый разбор аргументов командной строки
    // Использование: ./auth_server_app [tcp_listen_port] [grpc_auth_service_address]
    // Пример: ./auth_server_app 9000 localhost:50051
    // Пример для Docker: ./auth_server_app 9000 auth_server:50051 (где auth_server - имя сервиса Python gRPC)

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
    // Старый разбор позиционных аргументов удален в пользу именованных аргументов.
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

        // Настройка обработки сигналов для корректного завершения работы
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
