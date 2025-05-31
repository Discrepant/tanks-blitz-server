#include "catch2/catch_all.hpp"
#include "../game_server_cpp/command_consumer.h"
#include "../game_server_cpp/session_manager.h"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h" // For initializing SM and TP
#include "../game_server_cpp/tank.h" // To check tank state

// Static initializers for dependencies (TankPool and SessionManager are singletons)
static KafkaProducerHandler cc_test_kafka_producer("localhost:9099"); // Dummy broker
static TankPool* cc_test_tank_pool = TankPool::get_instance(5, &cc_test_kafka_producer);
static SessionManager* cc_test_session_manager = SessionManager::get_instance(cc_test_tank_pool, &cc_test_kafka_producer);

struct CommandConsumerTestFixture {
    PlayerCommandConsumer consumer;

    CommandConsumerTestFixture()
        : consumer(cc_test_session_manager, cc_test_tank_pool, "dummy_host", 0, "dummy_user", "dummy_pass") {
        // Ensure singletons are initialized
        REQUIRE(cc_test_tank_pool != nullptr);
        REQUIRE(cc_test_session_manager != nullptr);

        // Clean up any existing sessions/players from previous test cases to ensure isolation
        auto all_sessions = cc_test_session_manager->get_all_sessions();
        for (const auto& session : all_sessions) {
            cc_test_session_manager->remove_session(session->get_id(), "fixture_setup_cleanup");
        }
        // Ensure all tanks in the pool are available (released)
        // This is complex as we don't have a direct "release_all_tanks" or reset on the pool itself.
        // For now, rely on individual tests to manage the tanks they acquire.
    }

    ~CommandConsumerTestFixture() {
        // Consumer destructor will call stop() if it was started.
        // Here, we are only testing handle_command_logic, not starting the consumer thread.
    }

    // Helper to create a player and assign a tank for tests
    std::shared_ptr<Tank> setup_player_in_session(const std::string& player_id, const std::string& session_id_hint = "test_session") {
        auto tank = cc_test_tank_pool->acquire_tank();
        REQUIRE(tank != nullptr); // Ensure tank acquisition was successful
        tank->set_active(true);

        // Using find_or_create_session to ensure player is in a session
        // If specific session ID is needed, create it first then add player.
        auto session = cc_test_session_manager->find_or_create_session_for_player(
            player_id,
            "udp_test_addr",
            tank,
            true);
        REQUIRE(session != nullptr); // Ensure session was created/found
        REQUIRE(session->has_player(player_id));
        return tank;
    }
};

TEST_CASE_METHOD(CommandConsumerTestFixture, "PlayerCommandConsumer::handle_command_logic Tests", "[command_consumer]") {

    SECTION("Valid 'move' command") {
        std::string player_id = "player_move_test";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);
        tank->move({{"x", 0}, {"y", 0}}); // Reset position for predictable test

        nlohmann::json move_payload = {
            {"player_id", player_id},
            {"command", "move"},
            {"details", {
                {"new_position", {{"x", 10}, {"y", 20}}}
            }}
        };

        REQUIRE_NOTHROW(consumer.handle_command_logic(move_payload));

        // Verify tank's state
        auto session = cc_test_session_manager->get_session_by_player_id(player_id);
        REQUIRE(session != nullptr);
        auto tank_in_session = session->get_tank_for_player(player_id);
        REQUIRE(tank_in_session != nullptr);
        REQUIRE(tank_in_session->get_state()["position"]["x"] == 10);
        REQUIRE(tank_in_session->get_state()["position"]["y"] == 20);

        // Cleanup
        cc_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Valid 'shoot' command") {
        std::string player_id = "player_shoot_test";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);

        nlohmann::json shoot_payload = {
            {"player_id", player_id},
            {"command", "shoot"},
            {"details", {}} // Shoot details might be empty for now
        };

        // We are checking that it doesn't throw and is accepted by logic.
        // Actual tank->shoot() sends a Kafka message, which we don't check here.
        REQUIRE(consumer.handle_command_logic(shoot_payload) == true);
        // No direct state change in Tank object from shoot() to verify here.

        // Cleanup
        cc_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Command for player not in session") {
        nlohmann::json move_payload = {
            {"player_id", "player_not_in_session"},
            {"command", "move"},
            {"details", {{"new_position", {{"x", 5}, {"y", 5}}}}}
        };
        // Should be handled gracefully, logged, and message ACKed (returns true)
        REQUIRE(consumer.handle_command_logic(move_payload) == true);
    }

    SECTION("Command for player in session but tank is inactive") {
        std::string player_id = "player_inactive_tank";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);
        tank->set_active(false); // Make tank inactive
        tank->move({{"x", 0}, {"y", 0}}); // Known position

        nlohmann::json move_payload = {
            {"player_id", player_id},
            {"command", "move"},
            {"details", {{"new_position", {{"x", 15}, {"y", 25}}}}}
        };
        REQUIRE(consumer.handle_command_logic(move_payload) == true); // Command processed, but tank ignores it

        REQUIRE(tank->get_state()["position"]["x"] == 0); // Position should not have changed
        REQUIRE(tank->get_state()["position"]["y"] == 0);

        cc_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Invalid JSON payload structure") {
        nlohmann::json missing_player_id = {
            // player_id is missing
            {"command", "move"},
            {"details", {{"new_position", {{"x", 1}, {"y", 1}}}}}
        };
         // handle_command_logic throws runtime_error for missing fields
        REQUIRE_THROWS_AS(consumer.handle_command_logic(missing_player_id), std::runtime_error);


        nlohmann::json missing_command = {
            {"player_id", "some_player"},
            // command is missing
            {"details", {{"new_position", {{"x", 1}, {"y", 1}}}}}
        };
        REQUIRE_THROWS_AS(consumer.handle_command_logic(missing_command), std::runtime_error);

        nlohmann::json missing_details = {
            {"player_id", "some_player"},
            {"command", "move"}
            // details is missing
        };
        // For 'move', details.new_position is checked inside handle_command_logic -> tank->move
        // handle_command_logic itself might not throw if only details is missing, but move specific logic would.
        // The current handle_command_logic for "move" checks details.contains("new_position")
        REQUIRE_THROWS_AS(consumer.handle_command_logic(missing_details), std::runtime_error);
    }

    SECTION("Move command missing new_position in details") {
        std::string player_id = "player_move_bad_details";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);

        nlohmann::json move_bad_details_payload = {
            {"player_id", player_id},
            {"command", "move"},
            {"details", {}} // new_position is missing
        };
        // Tank::move will log an error and not move. handle_command_logic will throw.
        REQUIRE_THROWS_AS(consumer.handle_command_logic(move_bad_details_payload), std::runtime_error);

        cc_test_session_manager->remove_player_from_any_session(player_id);
    }


    SECTION("Unknown command type") {
        std::string player_id = "player_unknown_cmd";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);

        nlohmann::json unknown_command_payload = {
            {"player_id", player_id},
            {"command", "dance"}, // Unknown command
            {"details", {}}
        };
        // Unknown commands are logged and ACKed (returns true)
        REQUIRE(consumer.handle_command_logic(unknown_command_payload) == true);

        cc_test_session_manager->remove_player_from_any_session(player_id);
    }
}
