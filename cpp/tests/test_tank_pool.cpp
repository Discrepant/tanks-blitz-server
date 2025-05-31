#include "catch2/catch_all.hpp"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h" // For TankPool construction

// Global KafkaProducerHandler for tests requiring it for TankPool::get_instance first call
// This is tricky because TankPool is a singleton and takes KafkaProducerHandler*.
// If tests run in parallel or if Catch2 reorders them, the first call to get_instance matters.
// For simplicity, we'll create one here. In a more complex scenario, a fixture might be needed.
// Or, TankPool::get_instance could be made to not require KafkaProducerHandler after first init,
// or allow re-init with a new one (undesirable for singleton).
// Current TankPool::get_instance only uses kafka_handler if instance_ is nullptr.
static KafkaProducerHandler test_tp_kafka_producer("localhost:9099"); // Dummy broker

// Helper to reset TankPool singleton state for isolated tests if possible.
// This is generally NOT how singletons are tested. Proper singleton testing is complex.
// For these tests, we assume get_instance() is called and then we work with that instance.
// We cannot easily reset the singleton without a dedicated reset method, which is an anti-pattern.
// So, tests will operate on the same TankPool instance. Order might matter.
// Catch2 runs test cases in order they appear, but sections can be reordered.

TEST_CASE("TankPool Tests", "[tank_pool]") {
    // Ensure a valid KafkaProducerHandler for the first get_instance call in a test run.
    // If Kafka is not running, TankPool will still initialize, but Tanks won't send messages.
    // This is acceptable for testing TankPool's logic.
    size_t initial_pool_size = 5;
    TankPool* tank_pool = TankPool::get_instance(initial_pool_size, &test_tp_kafka_producer);
    REQUIRE(tank_pool != nullptr);

    // Note: Since TankPool is a singleton, its state persists across SECTIONs within this TEST_CASE
    // if they are run by the same Catch2 session invocation without recompile/restart.
    // This is not ideal for unit test isolation. A proper test setup might involve
    // a way to reset the singleton or use a dependency injection pattern for TankPool.
    // For now, we write tests knowing this limitation.

    SECTION("TankPool Singleton Instance") {
        TankPool* tp1 = TankPool::get_instance(initial_pool_size, &test_tp_kafka_producer);
        TankPool* tp2 = TankPool::get_instance(); // Subsequent calls shouldn't need params
        REQUIRE(tp1 == tp2);
        REQUIRE(tp1 != nullptr);
    }

    // SECTION("TankPool Initialization")
    // This is hard to test in isolation due to singleton state.
    // The first get_instance in this file already initializes it.
    // We can infer its state from acquire/release tests.
    // For example, after the first get_instance, try acquiring `initial_pool_size` tanks.

    SECTION("Acquire and Release Tanks") {
        std::shared_ptr<Tank> t1 = tank_pool->acquire_tank();
        REQUIRE(t1 != nullptr);
        REQUIRE(t1->is_active() == true);
        REQUIRE(t1->get_state()["is_active"] == true);
        std::string t1_id = t1->get_id();

        std::shared_ptr<Tank> t2 = tank_pool->acquire_tank();
        REQUIRE(t2 != nullptr);
        REQUIRE(t2->is_active() == true);
        REQUIRE(t1_id != t2->get_id()); // Should be different tanks
        std::string t2_id = t2->get_id();

        // Get an in-use tank
        std::shared_ptr<Tank> get_t1 = tank_pool->get_tank(t1_id);
        REQUIRE(get_t1 != nullptr);
        REQUIRE(get_t1 == t1);

        tank_pool->release_tank(t1_id);
        REQUIRE_FALSE(t1->is_active()); // Tank t1 (shared_ptr still exists) should be inactive
                                       // and reset (health 100, pos 0,0)
        REQUIRE(t1->get_state()["health"] == 100);
        REQUIRE(t1->get_state()["position"]["x"] == 0);


        std::shared_ptr<Tank> get_t1_after_release = tank_pool->get_tank(t1_id);
        REQUIRE(get_t1_after_release == nullptr); // Should not be in "in_use_tanks"

        // Acquire again, might get t1 back
        std::shared_ptr<Tank> t3 = tank_pool->acquire_tank();
        REQUIRE(t3 != nullptr);
        REQUIRE(t3->is_active() == true);
        // It's possible t3 is t1 if only one was released and it's LIFO.
        // If t1_id was pushed to back of available_tank_ids_ and then popped.
        REQUIRE(t3->get_id() == t1_id); // Assuming LIFO for available_tank_ids_

        tank_pool->release_tank(t2_id);
        tank_pool->release_tank(t3->get_id()); // which is t1
    }

    SECTION("Acquire all tanks and try one more") {
        std::vector<std::shared_ptr<Tank>> acquired_tanks;
        for (size_t i = 0; i < initial_pool_size; ++i) {
            std::shared_ptr<Tank> t = tank_pool->acquire_tank();
            REQUIRE(t != nullptr);
            acquired_tanks.push_back(t);
        }

        // Try to acquire one more than available
        std::shared_ptr<Tank> extra_tank = tank_pool->acquire_tank();
        REQUIRE(extra_tank == nullptr);

        // Release all acquired tanks
        for (const auto& t : acquired_tanks) {
            if (t) tank_pool->release_tank(t->get_id());
        }
        acquired_tanks.clear();
    }

    SECTION("Release non-existent or already released tank") {
        // Ensure pool is in a somewhat known state, e.g. at least one tank available
        std::shared_ptr<Tank> t = tank_pool->acquire_tank();
        REQUIRE(t != nullptr);
        std::string valid_id = t->get_id();
        tank_pool->release_tank(valid_id); // Release it

        REQUIRE_NOTHROW(tank_pool->release_tank("non_existent_tank_id_123"));
        REQUIRE_NOTHROW(tank_pool->release_tank(valid_id)); // Re-releasing already released tank
    }

    SECTION("Get non-existent tank") {
        std::shared_ptr<Tank> non_existent = tank_pool->get_tank("tank_id_that_does_not_exist_456");
        REQUIRE(non_existent == nullptr);
    }
}
