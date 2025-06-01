#include "udp_handler.h"
#include "tcp_handler.h"
#include "kafka_producer_handler.h"
#include "tank.h"
#include "tank_pool.h"
#include "game_session.h"
#include "session_manager.h"
#include "command_consumer.h"
#include <iostream>
#include <stdexcept>
#include <boost/asio/signal_set.hpp> // For signal handling
#include <grpcpp/grpcpp.h> // For gRPC channel

// Removed global io_context pointer

// Default configuration values
struct AppConfig {
    short udp_port = 8889;
    short tcp_port = 8888;
    std::string rmq_host = "rabbitmq"; // Default for Docker
    int rmq_port = 5672;
    std::string rmq_user = "user";
    std::string rmq_pass = "password";
    std::string kafka_brokers = "kafka:19092"; // Default for Docker
    std::string auth_grpc_host = "auth_server"; // Python gRPC Auth service, via Docker service name
    int auth_grpc_port = 50051;

    std::string get_auth_grpc_address() const {
        return auth_grpc_host + ":" + std::to_string(auth_grpc_port);
    }
};

// Helper to parse arguments - very basic
void parse_arguments(int argc, char* argv[], AppConfig& config) {
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        try {
            if (arg == "--udp_port" && i + 1 < argc) config.udp_port = static_cast<short>(std::stoi(argv[++i]));
            else if (arg == "--tcp_port" && i + 1 < argc) config.tcp_port = static_cast<short>(std::stoi(argv[++i]));
            else if (arg == "--rmq_host" && i + 1 < argc) config.rmq_host = argv[++i];
            else if (arg == "--rmq_port" && i + 1 < argc) config.rmq_port = std::stoi(argv[++i]);
            else if (arg == "--rmq_user" && i + 1 < argc) config.rmq_user = argv[++i];
            else if (arg == "--rmq_pass" && i + 1 < argc) config.rmq_pass = argv[++i];
            else if (arg == "--kafka_brokers" && i + 1 < argc) config.kafka_brokers = argv[++i];
            else if (arg == "--auth_grpc_host" && i + 1 < argc) config.auth_grpc_host = argv[++i];
            else if (arg == "--auth_grpc_port" && i + 1 < argc) config.auth_grpc_port = std::stoi(argv[++i]);
            else if (arg == "--help") {
                std::cout << "Usage: " << argv[0] << " [options]" << std::endl;
                std::cout << "Options:" << std::endl;
                std::cout << "  --udp_port <port>         Default: " << AppConfig{}.udp_port << std::endl;
                std::cout << "  --tcp_port <port>         Default: " << AppConfig{}.tcp_port << std::endl;
                std::cout << "  --rmq_host <host>         Default: " << AppConfig{}.rmq_host << std::endl;
                std::cout << "  --rmq_port <port>         Default: " << AppConfig{}.rmq_port << std::endl;
                std::cout << "  --rmq_user <user>         Default: " << AppConfig{}.rmq_user << std::endl;
                std::cout << "  --rmq_pass <password>     Default: " << AppConfig{}.rmq_pass << std::endl;
                std::cout << "  --kafka_brokers <brokers> Default: " << AppConfig{}.kafka_brokers << std::endl;
                std::cout << "  --auth_grpc_host <host>   Default: " << AppConfig{}.auth_grpc_host << std::endl;
                std::cout << "  --auth_grpc_port <port>   Default: " << AppConfig{}.auth_grpc_port << std::endl;
                exit(0);
            } else {
                std::cerr << "Warning: Unknown or incomplete argument: " << arg << std::endl;
            }
        } catch (const std::exception& e) {
            std::cerr << "Error parsing argument for " << arg << " (value: " << (argv[i] ? argv[i] : "N/A") << "): " << e.what() << std::endl;
        }
    }
}


int main(int argc, char* argv[]) {
    AppConfig config;
    parse_arguments(argc, argv, config);

    std::cout << "Initializing C++ Game Server with configuration:" << std::endl;
    std::cout << "  Config - UDP Port: " << config.udp_port << std::endl;
    std::cout << "  Config - TCP Port: " << config.tcp_port << std::endl;
    std::cout << "  Config - RabbitMQ: " << config.rmq_host << ":" << config.rmq_port
              << " (User: " << config.rmq_user << ")" << std::endl;
    std::cout << "  Config - Kafka: " << config.kafka_brokers << std::endl;
    std::cout << "  Config - Auth gRPC: " << config.get_auth_grpc_address() << std::endl;

    try {
        boost::asio::io_context io_context;

        // Setup signal handling for graceful shutdown
        boost::asio::signal_set signals(io_context, SIGINT, SIGTERM);
        signals.async_wait([&io_context](const boost::system::error_code& /*error*/, int signal_num) {
            std::cout << "\nSignal " << signal_num << " received. Game Server main stopping io_context." << std::endl;
            io_context.stop();
        });

        // 0. Initialize Kafka Producer Handler
        KafkaProducerHandler kafka_producer(config.kafka_brokers);
        if (!kafka_producer.is_valid()) {
            std::cerr << "FATAL: KafkaProducerHandler could not be initialized. Game Server will run without Kafka event publishing." << std::endl;
        } else {
            std::cout << "KafkaProducerHandler initialized successfully for brokers: " << config.kafka_brokers << std::endl;
        }

        // 1. Initialize TankPool Singleton
        TankPool* tank_pool_ptr = TankPool::get_instance(10, &kafka_producer);
        if (!tank_pool_ptr) {
            std::cerr << "FATAL: TankPool could not be initialized. Exiting." << std::endl;
            return 1;
        }

        // 2. Initialize SessionManager Singleton
        SessionManager* session_manager_ptr = SessionManager::get_instance(tank_pool_ptr, &kafka_producer);
        if (!session_manager_ptr) {
            std::cerr << "FATAL: SessionManager could not be initialized. Exiting." << std::endl;
            return 1;
        }

        // 3. Initialize UDP Handler (which sets up its own RabbitMQ connection)
        GameUDPHandler udp_server(io_context, config.udp_port, session_manager_ptr, tank_pool_ptr,
                                  config.rmq_host, config.rmq_port, config.rmq_user, config.rmq_pass);

        amqp_connection_state_t rmq_conn_state_for_tcp = nullptr;
        if (udp_server.is_rmq_connected()) {
            rmq_conn_state_for_tcp = udp_server.get_rmq_connection_state();
            std::cout << "RabbitMQ connection state obtained from UDP handler for TCP server use." << std::endl;
        } else {
            std::cerr << "Warning: UDP Handler's RabbitMQ connection failed. TCP handler RabbitMQ features might also fail or use separate connection." << std::endl;
        }

        // 4. Create gRPC Channel for Authentication Service
        std::string auth_grpc_server_address = config.get_auth_grpc_address();
        std::shared_ptr<grpc::Channel> auth_channel = grpc::CreateChannel(
            auth_grpc_server_address,
            grpc::InsecureChannelCredentials()
        );
        if(!auth_channel) {
             std::cerr << "FATAL: Failed to create gRPC channel to Auth Service at " << auth_grpc_server_address << ". TCP login will fail." << std::endl;
        } else {
            std::cout << "gRPC channel to Auth Service at " << auth_grpc_server_address << " created." << std::endl;
        }

        // 5. Initialize TCP Handler (Game Server)
        GameTCPServer tcp_server(io_context, config.tcp_port, session_manager_ptr, tank_pool_ptr, rmq_conn_state_for_tcp, auth_channel);

        // 6. Initialize and Start PlayerCommandConsumer
        PlayerCommandConsumer command_consumer(session_manager_ptr, tank_pool_ptr,
                                             config.rmq_host, config.rmq_port, config.rmq_user, config.rmq_pass);
        command_consumer.start();

        std::cout << "All game server components initialized. Running io_context. Press Ctrl+C to exit." << std::endl;
        io_context.run();

        std::cout << "Game Server io_context finished. Stopping command consumer..." << std::endl;
        // PlayerCommandConsumer::stop() should ideally be idempotent and check if running
        command_consumer.stop();
        std::cout << "Command consumer stopped." << std::endl;
        std::cout << "Game Server shut down gracefully." << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "Critical Error in Game Server main: " << e.what() << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "Unknown critical error in Game Server main." << std::endl;
        return 2;
    }

    return 0;
}
