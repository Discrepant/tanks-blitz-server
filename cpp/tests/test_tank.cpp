#include "catch2/catch_all.hpp"
#include "../game_server_cpp/tank.h"
#include "../game_server_cpp/kafka_producer_handler.h" // Include real Kafka handler

// Note: For these tests to run without Kafka-related errors logged to console (if Kafka isn't running),
// the KafkaProducerHandler should gracefully handle construction failure or send_message failure.
// The tests themselves will focus on Tank's state, not successful Kafka delivery.

TEST_CASE("Tank Class Tests", "[tank]") {
    // A KafkaProducerHandler is needed by the Tank constructor.
    // It's created here but its Kafka instance might not be running during tests.
    // Operations that send Kafka messages will attempt to do so; tests focus on Tank state.
    // Using a placeholder broker address as it might not connect during unit tests.
    // If Kafka connection is critical for tests, a mock or test Kafka instance would be needed.
    KafkaProducerHandler test_kafka_producer("localhost:9099"); // Dummy broker for tests if real one not needed

    SECTION("Tank Initialization") {
        Tank tank("tank_init_01", &test_kafka_producer, {{"x", 10}, {"y", 20}}, 150);
        REQUIRE(tank.get_id() == "tank_init_01");
        REQUIRE(tank.get_state()["health"] == 150);
        REQUIRE(tank.get_state()["position"]["x"] == 10);
        REQUIRE(tank.get_state()["position"]["y"] == 20);
        REQUIRE_FALSE(tank.is_active()); // Tanks are inactive by default
        REQUIRE(tank.get_state()["is_active"] == false);
    }

    SECTION("Tank Activation and Deactivation") {
        Tank tank("tank_active_01", &test_kafka_producer);
        REQUIRE_FALSE(tank.is_active());

        tank.set_active(true);
        REQUIRE(tank.is_active());
        REQUIRE(tank.get_state()["is_active"] == true);

        // Setting active to true again should not change anything
        tank.set_active(true);
        REQUIRE(tank.is_active());

        tank.set_active(false);
        REQUIRE_FALSE(tank.is_active());
        REQUIRE(tank.get_state()["is_active"] == false);

        // Setting active to false again should not change anything
        tank.set_active(false);
        REQUIRE_FALSE(tank.is_active());
    }

    SECTION("Tank Reset") {
        Tank tank("tank_reset_01", &test_kafka_producer, {{"x", 5}, {"y", 5}}, 50);
        tank.set_active(true); // Activate it first
        REQUIRE(tank.is_active());

        tank.reset({{"x", 1}, {"y", 2}}, 90);
        REQUIRE(tank.get_id() == "tank_reset_01"); // ID should persist
        REQUIRE(tank.get_state()["health"] == 90);
        REQUIRE(tank.get_state()["position"]["x"] == 1);
        REQUIRE(tank.get_state()["position"]["y"] == 2);
        REQUIRE_FALSE(tank.is_active()); // Reset should deactivate
        REQUIRE(tank.get_state()["is_active"] == false);

        // Reset to default values
        tank.set_active(true);
        tank.reset();
        REQUIRE(tank.get_state()["health"] == 100); // Default health
        REQUIRE(tank.get_state()["position"]["x"] == 0); // Default x
        REQUIRE(tank.get_state()["position"]["y"] == 0); // Default y
        REQUIRE_FALSE(tank.is_active());
    }

    SECTION("Tank Movement") {
        Tank tank("tank_move_01", &test_kafka_producer);
        tank.set_active(true); // Must be active to move

        nlohmann::json new_pos = {{"x", 100}, {"y", 200}};
        tank.move(new_pos);
        REQUIRE(tank.get_state()["position"]["x"] == 100);
        REQUIRE(tank.get_state()["position"]["y"] == 200);

        // Moving while inactive should not change position
        tank.set_active(false);
        nlohmann::json another_pos = {{"x", -50}, {"y", -50}};
        tank.move(another_pos);
        REQUIRE(tank.get_state()["position"]["x"] == 100); // Position should remain unchanged
        REQUIRE(tank.get_state()["position"]["y"] == 200);
    }

    SECTION("Tank Shooting") {
        Tank tank("tank_shoot_01", &test_kafka_producer);
        tank.set_active(true);
        // Test is conceptual for Kafka message. No state change in Tank object itself from shoot().
        // We would need a mock KafkaProducerHandler to verify message was sent.
        // For now, just ensure it doesn't crash.
        REQUIRE_NOTHROW(tank.shoot());

        // Shooting while inactive should not do anything / send message
        tank.set_active(false);
        REQUIRE_NOTHROW(tank.shoot());
    }

    SECTION("Tank Damage and Destruction") {
        Tank tank("tank_dmg_01", &test_kafka_producer, {{"x",0},{"y",0}}, 100);
        tank.set_active(true);

        tank.take_damage(30);
        REQUIRE(tank.get_state()["health"] == 70);

        tank.take_damage(60);
        REQUIRE(tank.get_state()["health"] == 10);

        // Damage exceeding current health
        tank.take_damage(25);
        REQUIRE(tank.get_state()["health"] == 0);
        // Tank might become inactive upon destruction, depending on game logic.
        // Current Tank::take_damage does not set inactive, Tank::reset does.
        // This behavior should be consistent or tested against specific game rules.
        // For now, let's assume it remains active but with 0 health until explicitly reset/deactivated by game logic.
        REQUIRE(tank.is_active()); // Or REQUIRE_FALSE(tank.is_active()) if take_damage(fatal) deactivates

        // Further damage when health is 0 should not change health
        tank.take_damage(10);
        REQUIRE(tank.get_state()["health"] == 0);
    }

    SECTION("Tank get_state method") {
        Tank tank("tank_getstate_01", &test_kafka_producer, {{"x", 7},{"y", 17}}, 77);
        nlohmann::json state = tank.get_state();
        REQUIRE(state["id"] == "tank_getstate_01");
        REQUIRE(state["position"]["x"] == 7);
        REQUIRE(state["position"]["y"] == 17);
        REQUIRE(state["health"] == 77);
        REQUIRE(state["is_active"] == false);

        tank.set_active(true);
        state = tank.get_state();
        REQUIRE(state["is_active"] == true);
    }
}
