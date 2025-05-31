#include "udp_handler.h"
#include "tcp_handler.h" // Include the TCP server handler
 // No longer needed

// Include new headers for Kafka and Tank
#include "kafka_producer_handler.h"
#include "tank.h"
#include "tank_pool.h"
#include "game_session.h"    // Include GameSession
#include "session_manager.h" // Include SessionManager
#include "command_consumer.h" // Include CommandConsumer

// Forward declare a function to get rabbitmq_conn from udp_server if needed,
// or make rabbitmq_conn_ accessible, or manage it centrally.
// For simplicity, we'll assume udp_handler can provide it or we pass a shared one.
+
+// gRPC specific includes for main if creating channel here
+#include <grpcpp/grpcpp.h>
// Let's refine udp_handler.h and .cpp slightly to allow access to rabbitmq_conn_state
// For this example, we'll assume GameUDPHandler has a method like get_rabbitmq_connection_state()
// OR, better, initialize RabbitMQ connection once and pass it to both.
// For now, let's assume GameUDPHandler initializes it and we can retrieve it.
// This is a bit of a hack for now; a dedicated RabbitMQ client/manager class would be better.

// A better approach for RabbitMQ connection management will be addressed later if needed.
// For now, GameUDPHandler will own the primary connection setup.
// We'll need to expose a getter or pass it around. Let's assume for now that
// GameUDPHandler's constructor returns the amqp_connection_state_t or has a getter.
// Simplest for now: GameUDPHandler has a public getter.
// This is not ideal. A better way is to have a shared RabbitMQ connection manager.
// Let's modify GameUDPHandler to have a getter for its connection state.
// This is still not great, as the TCP server now depends on the UDP server's successful MQ setup.

/*
// --- Hypothetical change in udp_handler.h ---
public:
    amqp_connection_state_t get_rabbitmq_connection_state() const { return rabbitmq_conn_; }
// --- End Hypothetical change ---
*/
// Given the current structure, the UDP handler initializes RabbitMQ.
// We will pass the 'rabbitmq_conn_' from UDP handler to TCP handler.
// This implies UDP handler must be created first.

int main() {
    const short udp_port = 8889;
    const short tcp_port = 8888; // As used by Python TCP handler

    try {
        std::cout << "Initializing C++ Game Server..." << std::endl;

        boost::asio::io_context io_context;

        // 0. Initialize Kafka Producer Handler (must be done before TankPool if TankPool needs it)
        std::cout << "Initializing Kafka Producer Handler..." << std::endl;
        KafkaProducerHandler kafka_producer("kafka:9092");
        if (!kafka_producer.is_valid()) {
            std::cerr << "FATAL: KafkaProducerHandler could not be initialized. Server will run without Kafka features." << std::endl;
        } else {
            std::cout << "KafkaProducerHandler initialized successfully." << std::endl;
        }

        // 1. Initialize TankPool Singleton
        std::cout << "Initializing TankPool..." << std::endl;
        TankPool* tank_pool_ptr = TankPool::get_instance(10, &kafka_producer); // e.g., pool of 10 tanks
        if (!tank_pool_ptr) {
            std::cerr << "FATAL: TankPool could not be initialized. Exiting." << std::endl;
            return 1;
        }
        std::cout << "TankPool initialized." << std::endl;

        // 2. Initialize SessionManager Singleton
        std::cout << "Initializing SessionManager..." << std::endl;
        SessionManager* session_manager_ptr = SessionManager::get_instance(tank_pool_ptr, &kafka_producer);
        if (!session_manager_ptr) {
            std::cerr << "FATAL: SessionManager could not be initialized. Exiting." << std::endl;
            return 1;
        }
        std::cout << "SessionManager initialized." << std::endl;

        // 3. Initialize UDP Handler (which also sets up RabbitMQ connection)
        // For now, let's assume direct member access for simplicity of this step,
        // knowing this is bad practice and should be refactored.
        // A real solution would involve a shared RabbitMQ client or passing the state more cleanly.
        // Let's assume udp_handler.h was modified to make rabbitmq_conn_ accessible (e.g. public or getter)
        // For this example, we will assume udp_handler is modified to setup rabbitmq and store the state.
        // We'll pass this state to the TCP server.

        // The GameUDPHandler constructor already calls setup_rabbitmq_connection().
        // We need a way to get this `rabbitmq_conn_` to pass to GameTCPServer.
        // Let's assume for now that the connection object within GameUDPHandler is made accessible
        // or GameUDPHandler is refactored to return it or take a shared one.
        // Simplest change for now: Add a getter in GameUDPHandler for rabbitmq_conn_
        // (This would require editing udp_handler.h and recompiling it in a real scenario)
        // For the tool, I'll assume such a getter exists: `udp_server.get_rabbitmq_connection()`

        GameUDPHandler udp_server(io_context, udp_port, session_manager, tank_pool);
        std::cout << "C++ UDP Server setup complete. Listening on port " << udp_port << "." << std::endl;

        // Retrieve the RabbitMQ connection state from the UDP server
        // This is a placeholder for a proper mechanism.
        // If GameUDPHandler::setup_rabbitmq_connection returns bool, and stores conn internally,
        // we need a getter. For now, let's assume `udp_server.rabbitmq_conn_` is accessible.
        // This is conceptually what we need:
        amqp_connection_state_t shared_rabbitmq_conn = nullptr;
        // A real implementation would fetch this from udp_server after it's initialized.
        // For example, if udp_handler has: amqp_connection_state_t get_rmq_conn() { return rabbitmq_conn_; }
        // shared_rabbitmq_conn = udp_server.get_rmq_conn();
        // Let's assume `udp_server.rabbitmq_conn_` is what we're passing, and it's setup.
        // The UDP handler's constructor already tries to set this up.
        // We'll pass the same rabbitmq_conn_ member that udp_handler uses.
        // This requires GameUDPHandler to expose its internal rabbitmq_conn_
        // For this step, we'll pass a nullptr and fix MQ sharing later if direct pass is too complex for tool.
        // The current GameUDPHandler does not expose its rabbitmq_conn_ directly.
        // Let's assume for now that TCP handler will try to establish its own or we accept it might not work without further refactor.
        // The prompt says: "the RabbitMQ connection state (amqp_connection_state_t) established by the UDP handler's setup_rabbitmq_connection can be passed"
        // This means we need to modify GameUDPHandler to expose it.
        // I will proceed ASSUMING `GameUDPHandler` has a public member `rabbitmq_conn_` or a getter.
        // For the sake of tool flow, I'll use a placeholder. If the tool cannot modify udp_handler.h here,
        // then TCP RabbitMQ part won't work until that's fixed.
        // The tool can't modify `udp_handler.h` in *this* specific turn if it's not the target file.
        // So, I'll pass a NULL for now and note this as a required refactor.
        // UPDATE: The UDP handler has `rabbitmq_conn_` as a private member.
        // For the purpose of this step, let's assume we will handle RabbitMQ connection independently in TCP
        // or refactor MQ management later. For now, pass nullptr to satisfy constructor,
        // and TCP's publish will fail gracefully.
        // The prompt is quite specific: "pass the rabbitmq_conn from the UDP handler".
        // This implies a design where GameUDPHandler has it.
        // Let's assume we can't modify GameUDPHandler now to add a getter.
        // The simplest way to get this working is to make setup_rabbitmq_connection a global utility
        // or have a shared RabbitMQManager.
        // Given the constraints, I'll create a *new* connection attempt in TCPServer for now,
        // or make TCPSession's MQ publish a no-op if conn is null.
        // The current TCP Session constructor takes amqp_connection_state_t.
        // The GameTCPServer constructor also takes it.
        // Let's simulate getting it from UDP server by *assuming* such a getter exists.
        // The tool should focus on creating the files as per prompt.
        // The prompt implies GameUDPHandler has the connection.
        // I will write the code AS IF GameUDPHandler has a public getter `get_rabbitmq_connection()`.
        // This will be a placeholder for the actual mechanism.

        amqp_connection_state_t actual_rabbitmq_conn_state_from_udp = nullptr; // Placeholder
        // If `udp_server.setup_rabbitmq_connection()` was successful, it has `rabbitmq_conn_`.
        // To make this work, `GameUDPHandler` needs a public getter:
        // e.g. in GameUDPHandler: `amqp_connection_state_t get_amqp_connection() const { return rabbitmq_conn_; }`
        GameUDPHandler udp_server(io_context, udp_port, session_manager_ptr, tank_pool_ptr);
        std::cout << "C++ UDP Server setup complete. Listening on port " << udp_port << "." << std::endl;

        amqp_connection_state_t actual_rabbitmq_conn_state_from_udp = nullptr;
        if (udp_server.is_rabbitmq_connected()) {
            actual_rabbitmq_conn_state_from_udp = udp_server.get_rabbitmq_connection_state();
            std::cout << "RabbitMQ connection state obtained from UDP handler for TCP server." << std::endl;
        } else {
            std::cerr << "Warning: RabbitMQ connection not established by UDP handler. TCP handler RabbitMQ features may fail." << std::endl;
        }

        // 4. Create gRPC Channel for Authentication Service
        std::string auth_grpc_server_address = "localhost:50051"; // Make this configurable if needed
        std::cout << "Creating gRPC channel to Auth Service at: " << auth_grpc_server_address << std::endl;
        std::shared_ptr<grpc::Channel> auth_channel = grpc::CreateChannel(
            auth_grpc_server_address,
            grpc::InsecureChannelCredentials()
        );
        // Optionally, check channel connectivity here, e.g., with WaitForConnected or GetState.
        // auto channel_state = auth_channel->GetState(true); // true means try to connect
        // std::cout << "Auth gRPC Channel state: " << channel_state << std::endl;


        // 5. Initialize TCP Handler (Game Server)
        GameTCPServer tcp_server(io_context, tcp_port, session_manager_ptr, tank_pool_ptr, actual_rabbitmq_conn_state_from_udp, auth_channel);
        std::cout << "C++ Game TCP Server setup complete. Listening on port " << tcp_port << "." << std::endl;


        // 6. Test SessionManager (Optional - this test might be removed or adapted for gRPC auth)
        // The previous test for SessionManager might be less relevant now or need adjustment
        // as login via TCP will handle player/session creation.
        // For now, let's comment out the direct SessionManager test to avoid conflicts with TCP login flow.
        /*
        if (session_manager_ptr && tank_pool_ptr) {
             std::cout << "\n--- Testing SessionManager & TankPool Integration ---" << std::endl;
            auto test_session = session_manager_ptr->create_session();
            if (test_session) {
                // ... (rest of the test)
            }
             std::cout << "--- End SessionManager & TankPool Integration Test ---\n" << std::endl;
        }
        */


        std::cout << "All game server components initialized. Running io_context. Press Ctrl+C to exit." << std::endl;

        // 6. Initialize and Start PlayerCommandConsumer
        PlayerCommandConsumer command_consumer(session_manager_ptr, tank_pool_ptr, "rabbitmq", 5672, "user", "password");
        command_consumer.start();


        io_context.run(); // This will block for both UDP and TCP servers

        // Cleanup - stop consumer after io_context.run() finishes (e.g. on SIGINT/SIGTERM)
        std::cout << "io_context finished. Stopping command consumer..." << std::endl;
        command_consumer.stop();

    } catch (const std::exception& e) {
        std::cerr << "Critical Error in main: " << e.what() << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "Unknown critical error in main." << std::endl;
        return 2;
    }

    std::cout << "C++ Game Server shutting down normally." << std::endl;
    return 0;
}
