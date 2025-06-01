#include "catch2/catch_all.hpp"
#include "../game_server_cpp/udp_handler.h"
#include "../game_server_cpp/session_manager.h"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h" // For initializing SM and TP
#include <boost/asio/io_context.hpp>
#include <boost/asio/ip/udp.hpp>

// Static initializers for dependencies
static KafkaProducerHandler gudp_test_kafka_producer("localhost:9099"); // Dummy broker
static TankPool* gudp_test_tank_pool = TankPool::get_instance(5, &gudp_test_kafka_producer);
static SessionManager* gudp_test_session_manager = SessionManager::get_instance(gudp_test_tank_pool, &gudp_test_kafka_producer);

struct GameUDPHandlerTestFixture {
    boost::asio::io_context test_io_context;
    // GameUDPHandler constructor needs a live io_context and port to bind the socket.
    // For testing process_message directly, we might not need a fully functional socket.
    // However, send_json_response uses the socket.
    // We can pass a dummy port and not run io_context for these specific tests.
    // Or, use a real ephemeral port.
    std::unique_ptr<GameUDPHandler> udp_handler;
    udp::endpoint dummy_sender_endpoint;


    GameUDPHandlerTestFixture() {
        REQUIRE(gudp_test_tank_pool != nullptr);
        REQUIRE(gudp_test_session_manager != nullptr);

        // Clean up any existing sessions/players
        auto all_sessions = gudp_test_session_manager->get_all_sessions();
        for (const auto& session : all_sessions) {
            gudp_test_session_manager->remove_session(session->get_id(), "gudp_fixture_setup_cleanup");
        }
        // Note: TankPool state (which tanks are acquired) might persist. Tests should manage tanks they use.

        // For testing process_message, the actual listening port of GameUDPHandler is not critical
        // as long as its internal socket_ can be used for send_json_response (even if it fails to send to network).
        // The RabbitMQ connection details are also dummy for this direct testing of message logic.
        udp_handler = std::make_unique<GameUDPHandler>(
            test_io_context,
            0, // Use ephemeral port for socket creation, won't actually listen.
            gudp_test_session_manager,
            gudp_test_tank_pool,
            "dummy_rmq_host", 5672, "user", "pass"
        );

        // Create a dummy sender endpoint
        dummy_sender_endpoint = udp::endpoint(boost::asio::ip::make_address_v4("127.0.0.1"), 12345);
    }

    ~GameUDPHandlerTestFixture() {
        // udp_handler->stop(); // If it had a separate stop, or destructor handles.
        // test_io_context.stop(); // If it was running
    }

    std::shared_ptr<Tank> setup_player_for_udp(const std::string& player_id, const std::string& udp_addr_str_from_endpoint) {
        auto tank = gudp_test_tank_pool->acquire_tank();
        REQUIRE(tank != nullptr);
        tank->set_active(true);
        auto session = gudp_test_session_manager->find_or_create_session_for_player(player_id, udp_addr_str_from_endpoint, tank, true);
        REQUIRE(session != nullptr);
        REQUIRE(session->has_player(player_id));
        return tank;
    }
};

TEST_CASE_METHOD(GameUDPHandlerTestFixture, "GameUDPHandler::process_message Tests", "[game_udp_handler]") {

    SECTION("Process 'join_game' command - new player") {
        json join_req = {
            {"action", "join_game"},
            {"player_id", "udp_player_join"}
        };
        // process_message calls send_json_response internally. We don't capture actual sent data here.
        // We check that the call doesn't crash and that side effects (session/tank) are correct.
        REQUIRE_NOTHROW(udp_handler->process_message(join_req.dump(), dummy_sender_endpoint));

        auto session = gudp_test_session_manager->get_session_by_player_id("udp_player_join");
        REQUIRE(session != nullptr);
        REQUIRE(session->get_players_count() == 1);
        auto tank = session->get_tank_for_player("udp_player_join");
        REQUIRE(tank != nullptr);
        REQUIRE(tank->is_active());

        // Cleanup
        gudp_test_session_manager->remove_player_from_any_session("udp_player_join");
    }

    SECTION("Process 'join_game' command - existing player") {
        std::string player_id = "udp_player_rejoin";
        setup_player_for_udp(player_id, dummy_sender_endpoint.address().to_string() + ":" + std::to_string(dummy_sender_endpoint.port()));

        json join_req = { {"action", "join_game"}, {"player_id", player_id} };
        REQUIRE_NOTHROW(udp_handler->process_message(join_req.dump(), dummy_sender_endpoint));
        // Expected: send_json_response with "already_in_session" or similar.
        // Player count in their original session should remain 1.
        auto session = gudp_test_session_manager->get_session_by_player_id(player_id);
        REQUIRE(session != nullptr);
        REQUIRE(session->get_players_count() == 1);

        gudp_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Process 'move' command") {
        std::string player_id = "udp_player_move";
        auto tank = setup_player_for_udp(player_id, dummy_sender_endpoint.address().to_string() + ":" + std::to_string(dummy_sender_endpoint.port()));
        REQUIRE(tank != nullptr);

        json move_req = {
            {"action", "move"},
            {"player_id", player_id},
            {"details", {{"new_position", {{"x", 55}, {"y", 66}}}}}
        };
        REQUIRE_NOTHROW(udp_handler->process_message(move_req.dump(), dummy_sender_endpoint));
        // This should publish to RabbitMQ. Tank's state is NOT changed by GameUDPHandler directly for move.
        // It's changed by PlayerCommandConsumer when it processes the RMQ message.
        // So, tank's position here should still be its initial one.
        REQUIRE(tank->get_state()["position"]["x"] != 55); // Assuming initial is not 55

        gudp_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Process 'shoot' command") {
        std::string player_id = "udp_player_shoot";
        setup_player_for_udp(player_id, dummy_sender_endpoint.address().to_string() + ":" + std::to_string(dummy_sender_endpoint.port()));

        json shoot_req = {
            {"action", "shoot"},
            {"player_id", player_id},
            {"details", {}}
        };
        REQUIRE_NOTHROW(udp_handler->process_message(shoot_req.dump(), dummy_sender_endpoint));
        // Should publish to RabbitMQ. No direct state change to verify here.

        gudp_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Process 'leave_game' command") {
        std::string player_id = "udp_player_leave";
        auto tank = setup_player_for_udp(player_id, dummy_sender_endpoint.address().to_string() + ":" + std::to_string(dummy_sender_endpoint.port()));
        std::string tank_id = tank->get_id();

        json leave_req = { {"action", "leave_game"}, {"player_id", player_id} };
        REQUIRE_NOTHROW(udp_handler->process_message(leave_req.dump(), dummy_sender_endpoint));

        REQUIRE(gudp_test_session_manager->get_session_by_player_id(player_id) == nullptr);
        // Check if tank was released by trying to acquire it again - it should be available.
        // This relies on TankPool's LIFO behavior for simplicity.
        auto released_tank = gudp_test_tank_pool->acquire_tank();
        REQUIRE(released_tank != nullptr);
        REQUIRE(released_tank->get_id() == tank_id); // Should get the same tank back
        gudp_test_tank_pool->release_tank(released_tank->get_id()); // Release it back
    }

    SECTION("Invalid JSON message") {
        std::string invalid_json_str = "this is not json";
        REQUIRE_NOTHROW(udp_handler->process_message(invalid_json_str, dummy_sender_endpoint));
        // Expect send_json_response with "Invalid JSON format"
    }

    SECTION("JSON missing fields") {
        json missing_action = { {"player_id", "player_missing_action"} };
        REQUIRE_NOTHROW(udp_handler->process_message(missing_action.dump(), dummy_sender_endpoint));
        // Expect send_json_response with "Missing player_id or action"

        json missing_playerid = { {"action", "move"} };
         REQUIRE_NOTHROW(udp_handler->process_message(missing_playerid.dump(), dummy_sender_endpoint));
        // Expect send_json_response with "Missing player_id or action"
    }

    SECTION("Unknown action") {
        json unknown_action = { {"player_id", "player_unknown"}, {"action", "fly"} };
        REQUIRE_NOTHROW(udp_handler->process_message(unknown_action.dump(), dummy_sender_endpoint));
        // Expect send_json_response with "Unknown action"
    }
}
