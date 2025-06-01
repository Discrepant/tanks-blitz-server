#include "catch2/catch_all.hpp"
#include "../game_server_cpp/tcp_session.h" // Class to test
#include "../game_server_cpp/session_manager.h"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h" // For SM/TP init
#include <boost/asio/io_context.hpp>
#include <grpcpp/create_channel.h> // For gRPC channel

// Static initializers for dependencies (Singletons)
static KafkaProducerHandler gtcp_test_kafka_producer("localhost:9099"); // Dummy for SM/TP
static TankPool* gtcp_test_tank_pool = TankPool::get_instance(5, &gtcp_test_kafka_producer);
static SessionManager* gtcp_test_session_manager = SessionManager::get_instance(gtcp_test_tank_pool, &gtcp_test_kafka_producer);

// Dummy AMQP connection state for GameTCPSession constructor
// In a real test involving RabbitMQ publishing, this would need to be a valid connection.
// For testing command parsing and gRPC calls, it can be nullptr if publish method handles it.
static amqp_connection_state_t gtcp_dummy_rmq_conn_state = nullptr;
// If GameTCPSession::publish_to_rabbitmq_internal rigorously checks this, calls might just log errors.

struct GameTCPSessionTestFixture {
    boost::asio::io_context test_io_context;
    std::shared_ptr<grpc::Channel> grpc_auth_channel;
    boost::asio::ip::tcp::socket test_socket; // Dummy socket
    std::shared_ptr<GameTCPSession> session;

    std::vector<std::string> sent_messages_capture; // Capture messages "sent"

    GameTCPSessionTestFixture() : test_socket(test_io_context) {
        REQUIRE(gtcp_test_tank_pool != nullptr);
        REQUIRE(gtcp_test_session_manager != nullptr);

        std::string grpc_server_address = "localhost:50051"; // Python Auth gRPC server
        grpc_auth_channel = grpc::CreateChannel(grpc_server_address, grpc::InsecureChannelCredentials());

        // Clean up any existing sessions/players from previous tests
        auto all_sessions = gtcp_test_session_manager->get_all_sessions();
        for (const auto& s : all_sessions) {
            gtcp_test_session_manager->remove_session(s->get_id(), "gtcp_fixture_setup_cleanup");
        }

        session = std::make_shared<GameTCPSession>(
            std::move(test_socket), // Socket moved, careful if reusing test_socket
            gtcp_test_session_manager,
            gtcp_test_tank_pool,
            gtcp_dummy_rmq_conn_state,
            grpc_auth_channel
        );
        // To test send_message output, GameTCPSession would need refactoring
        // to inject a mock sender or allow output capture.
        // For now, we call process_command and check observable side effects or lack of crashes.
    }

    ~GameTCPSessionTestFixture() {
        // Session might be closed by QUIT command tests.
        // if (session && session->socket().is_open()) { // socket() is private
        //    session->close_session("fixture_teardown");
        // }
    }

    // Helper function, now part of the fixture
    void perform_login(const std::string& user = "player1", const std::string& pass = "pass1") {
        session->process_command("LOGIN " + user + " " + pass);
        // Assume login is successful for subsequent tests.
        // A getter session->is_authenticated() would be good here.
    }
};

TEST_CASE_METHOD(GameTCPSessionTestFixture, "GameTCPSession::process_command Tests", "[game_tcp_session]") {

    INFO("Ensure Python gRPC Auth Server (auth_server/auth_grpc_server.py) is running on localhost:50051 for LOGIN tests.");

    SECTION("Process 'LOGIN' command - Successful") {
        // Assumes user "player1" pass "pass1" is valid in the Python gRPC Auth service.
        REQUIRE_NOTHROW(session->process_command("LOGIN player1 pass1"));
        // Expected: Several messages sent via send_message acknowledging login, game join, tank state.
        // Hard to verify actual sent content without send_message interception.
        // Check internal state:
        // REQUIRE(session->is_authenticated()); // Need a getter for these internal states
        // REQUIRE(session->get_username() == "player1");
        // These would require making username_ and authenticated_ public or adding getters.
        // For now, mainly testing no crash and gRPC interaction path.
        // If login is successful, a player and session should be created.
        auto game_session = gtcp_test_session_manager->get_session_by_player_id("player1");
        REQUIRE(game_session != nullptr); // Verify player was added to a session
        REQUIRE(game_session->get_tank_for_player("player1") != nullptr); // Verify tank was assigned
        gtcp_test_session_manager->remove_player_from_any_session("player1"); // Cleanup
    }

    SECTION("Process 'LOGIN' command - Failed (Wrong Password)") {
        REQUIRE_NOTHROW(session->process_command("LOGIN player1 wrongpass"));
        // Expected: LOGIN_FAILED message sent.
        // REQUIRE_FALSE(session->is_authenticated());
        auto game_session = gtcp_test_session_manager->get_session_by_player_id("player1");
        REQUIRE(game_session == nullptr); // Player should not be in a session
    }

    SECTION("Commands before authentication") {
        REQUIRE_NOTHROW(session->process_command("MOVE 10 20"));
        // Expected: UNAUTHORIZED message sent.
        REQUIRE_NOTHROW(session->process_command("SHOOT"));
        // Expected: UNAUTHORIZED message sent.
        REQUIRE_NOTHROW(session->process_command("PLAYERS"));
        // Expected: UNAUTHORIZED message sent.
    }

    SECTION("Process 'MOVE' command - Authenticated") {
        perform_login();
        // We need to get the tank_id that was assigned during login for this player
        auto game_session = gtcp_test_session_manager->get_session_by_player_id("player1");
        REQUIRE(game_session != nullptr);
        auto tank = game_session->get_tank_for_player("player1");
        REQUIRE(tank != nullptr);
        // tank->move({{"x",0},{"y",0}}); // Ensure known start pos if checking effect of RMQ message later

        REQUIRE_NOTHROW(session->process_command("MOVE 15 25"));
        // Expected: COMMAND_RECEIVED MOVE, and message published to RabbitMQ.
        // Tank state is not changed directly by GameTCPSession.
        // REQUIRE(tank->get_state()["position"]["x"] != 15); // This is true, consumer changes it.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'SHOOT' command - Authenticated") {
        perform_login();
        REQUIRE_NOTHROW(session->process_command("SHOOT"));
        // Expected: COMMAND_RECEIVED SHOOT, and message published to RabbitMQ.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'SAY' command - Authenticated") {
        perform_login();
        REQUIRE_NOTHROW(session->process_command("SAY Hello there General Kenobi"));
        // Expected: "You said: ..." and message published to RabbitMQ chat queue.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'HELP' command") {
        REQUIRE_NOTHROW(session->process_command("HELP")); // Test unauthenticated help
        perform_login();
        REQUIRE_NOTHROW(session->process_command("HELP")); // Test authenticated help
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'PLAYERS' command - Authenticated") {
        perform_login("player_list_test", "pass1"); // Use a unique player for this test
        REQUIRE_NOTHROW(session->process_command("PLAYERS"));
        // Expected: List of players in the current session.
        gtcp_test_session_manager->remove_player_from_any_session("player_list_test");
    }

    SECTION("Process 'QUIT' command") {
        perform_login("player_quit_test", "pass1");
        REQUIRE_NOTHROW(session->process_command("QUIT"));
        // Expected: GOODBYE message. Session closed. Player removed from SessionManager.
        // Check if player was removed
        REQUIRE(gtcp_test_session_manager->get_session_by_player_id("player_quit_test") == nullptr);
        // The socket in the session shared_ptr would be closed.
    }

    SECTION("Invalid command format / Unknown command") {
        perform_login(); // Some commands require auth to reach unknown command stage
        REQUIRE_NOTHROW(session->process_command("FLAPDOODLE 1 2 3"));
        // Expected: UNKNOWN_COMMAND message.
        REQUIRE_NOTHROW(session->process_command("MOVE too many args here and there"));
        // Expected: MOVE_FAILED (or specific error for arg count). Current impl might take first 2.
        // Current GameTCPSession::handle_move takes all args after "MOVE" and tries to stoi(args[0]), stoi(args[1]).
        // This test will check that it doesn't crash.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }
}
