#include "catch2/catch_all.hpp"
#include "../game_server_cpp/session_manager.h"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h"

// Global KafkaProducerHandler and TankPool for SessionManager tests.
// This is needed because SessionManager is a singleton and depends on TankPool,
// which in turn depends on KafkaProducerHandler for its first initialization.
static KafkaProducerHandler sm_test_kafka_producer("localhost:9099"); // Dummy broker for tests
static TankPool* sm_test_tank_pool = TankPool::get_instance(5, &sm_test_kafka_producer); // Pool of 5 for tests

// Attempt to reset singleton state for SessionManager before each test case.
// This is hacky. A better solution would involve dependency injection for SessionManager
// or a dedicated reset method in the Singleton (which is an anti-pattern for singletons).
// For these tests, we'll create a new instance for each test case if possible by manipulating the static pointer.
// This is generally not safe if tests run in parallel. Catch2 runs tests serially by default.
struct SessionManagerTestFixture {
    SessionManagerTestFixture() {
        // This is a simplified reset. Proper singleton reset is complex.
        // We are relying on the fact that SessionManager::get_instance will re-create if instance_ is null.
        // The old instance memory is not being deleted here, which is a leak.
        // This is a common problem testing singletons.
        // For robust tests, avoid singletons or make them resettable/configurable for tests.
        // SessionManager::instance_ = nullptr; // Cannot access private member
        // For now, tests will share the SessionManager instance.
        // This means test order could matter, and cleanup between tests is important.

        // Ensure TankPool is available
        if (!sm_test_tank_pool) {
            sm_test_tank_pool = TankPool::get_instance(5, &sm_test_kafka_producer);
        }
    }

    ~SessionManagerTestFixture() {
        // Clean up sessions created during a test, to try and isolate tests somewhat.
        SessionManager* sm = SessionManager::get_instance(sm_test_tank_pool, &sm_test_kafka_producer);
        auto all_sessions = sm->get_all_sessions();
        for (auto& session : all_sessions) {
            sm->remove_session(session->get_id(), "test_cleanup");
        }
    }
};


TEST_CASE_METHOD(SessionManagerTestFixture, "SessionManager Tests", "[session_manager]") {
    REQUIRE(sm_test_tank_pool != nullptr); // Prerequisite for SessionManager
    SessionManager* sm = SessionManager::get_instance(sm_test_tank_pool, &sm_test_kafka_producer);
    REQUIRE(sm != nullptr);

    SECTION("SessionManager Singleton Instance") {
        SessionManager* sm1 = SessionManager::get_instance(sm_test_tank_pool, &sm_test_kafka_producer);
        SessionManager* sm2 = SessionManager::get_instance(); // Subsequent calls
        REQUIRE(sm1 == sm2);
        REQUIRE(sm1 != nullptr);
    }

    SECTION("Create and Get Session") {
        std::shared_ptr<GameSession> session1 = sm->create_session();
        REQUIRE(session1 != nullptr);
        REQUIRE_FALSE(session1->get_id().empty());
        REQUIRE(sm->get_active_sessions_count() >= 1); // Could be more if prior tests didn't clean up perfectly

        std::shared_ptr<GameSession> retrieved_session1 = sm->get_session(session1->get_id());
        REQUIRE(retrieved_session1 != nullptr);
        REQUIRE(retrieved_session1->get_id() == session1->get_id());

        std::shared_ptr<GameSession> non_existent_session = sm->get_session("non_existent_id_123");
        REQUIRE(non_existent_session == nullptr);
        sm->remove_session(session1->get_id()); // Cleanup
    }

    SECTION("Remove Session") {
        std::shared_ptr<GameSession> session_to_remove = sm->create_session();
        REQUIRE(session_to_remove != nullptr);
        std::string session_id = session_to_remove->get_id();

        // Add a player to test cleanup
        auto tank_for_remove_test = sm_test_tank_pool->acquire_tank();
        REQUIRE(tank_for_remove_test != nullptr);
        sm->add_player_to_session(session_id, "player_in_removed_session", "addr", tank_for_remove_test);
        REQUIRE(sm->get_session_by_player_id("player_in_removed_session") != nullptr);

        REQUIRE(sm->remove_session(session_id));
        REQUIRE(sm->get_session(session_id) == nullptr);
        REQUIRE(sm->get_session_by_player_id("player_in_removed_session") == nullptr); // Player should be unmapped
        // Tank should have been released - check by trying to acquire it (might get same ID or another)
        // This check is indirect for tank release.

        REQUIRE_FALSE(sm->remove_session("non_existent_id_456"));
    }

    SECTION("Player Lifecycle in SessionManager") {
        std::shared_ptr<GameSession> session = sm->create_session();
        REQUIRE(session != nullptr);
        std::string session_id = session->get_id();

        auto tank1 = sm_test_tank_pool->acquire_tank();
        REQUIRE(tank1 != nullptr);
        std::string tank1_id = tank1->get_id();

        // Add player to session
        std::shared_ptr<GameSession> joined_session = sm->add_player_to_session(session_id, "player_lc_1", "udp_addr_lc_1", tank1);
        REQUIRE(joined_session != nullptr);
        REQUIRE(joined_session->get_id() == session_id);
        REQUIRE(session->has_player("player_lc_1"));
        REQUIRE(sm->get_session_by_player_id("player_lc_1") == session);

        // Try adding same player again (should ideally fail or return existing session)
        // Current SessionManager::add_player_to_session returns existing session if player already mapped.
        auto tank_dup = sm_test_tank_pool->acquire_tank(); // Need another tank if it were to allow adding
        REQUIRE(tank_dup != nullptr);
        std::shared_ptr<GameSession> rejoined_session = sm->add_player_to_session(session_id, "player_lc_1", "udp_addr_lc_1_new", tank_dup);
        REQUIRE(rejoined_session != nullptr);
        REQUIRE(rejoined_session == session); // Should return the same session
        REQUIRE(session->get_players_count() == 1); // Player count should still be 1
        sm_test_tank_pool->release_tank(tank_dup->get_id()); // Release the unused duplicate tank


        // Remove player
        REQUIRE(sm->remove_player_from_any_session("player_lc_1"));
        REQUIRE_FALSE(session->has_player("player_lc_1")); // Player removed from GameSession
        REQUIRE(sm->get_session_by_player_id("player_lc_1") == nullptr); // Player unmapped
        // Tank should be released. We can check if it's available again.
        // This relies on TankPool's LIFO behavior for available tanks for a simple check.
        auto acquired_after_release = sm_test_tank_pool->acquire_tank();
        REQUIRE(acquired_after_release != nullptr);
        REQUIRE(acquired_after_release->get_id() == tank1_id); // Should get the same tank back
        sm_test_tank_pool->release_tank(acquired_after_release->get_id()); // Clean up


        // Removing non-existent player
        REQUIRE_FALSE(sm->remove_player_from_any_session("player_lc_non_existent"));

        // Session should be empty now and thus removed by remove_player_from_any_session
        REQUIRE(sm->get_session(session_id) == nullptr);
    }

    SECTION("Full Session Lifecycle with Multiple Players") {
        std::shared_ptr<GameSession> session = sm->create_session();
        REQUIRE(session != nullptr);
        std::string s_id = session->get_id();

        auto p1_tank = sm_test_tank_pool->acquire_tank();
        REQUIRE(p1_tank != nullptr);
        std::string p1_tank_id = p1_tank->get_id();
        sm->add_player_to_session(s_id, "p1_full", "addr1", p1_tank);

        auto p2_tank = sm_test_tank_pool->acquire_tank();
        REQUIRE(p2_tank != nullptr);
        std::string p2_tank_id = p2_tank->get_id();
        sm->add_player_to_session(s_id, "p2_full", "addr2", p2_tank);

        REQUIRE(session->get_players_count() == 2);
        REQUIRE(sm->get_session(s_id) != nullptr); // Session should exist

        // Remove player 1
        sm->remove_player_from_any_session("p1_full");
        REQUIRE(session->get_players_count() == 1);
        REQUIRE_FALSE(session->has_player("p1_full"));
        REQUIRE(sm->get_session(s_id) != nullptr); // Session should still exist

        // Check if p1_tank is available (indirectly by acquiring)
        auto acquired_p1_tank = sm_test_tank_pool->acquire_tank();
        REQUIRE(acquired_p1_tank != nullptr);
        REQUIRE(acquired_p1_tank->get_id() == p1_tank_id);
        sm_test_tank_pool->release_tank(acquired_p1_tank->get_id()); // release it back

        // Remove player 2
        sm->remove_player_from_any_session("p2_full");
        // Session should now be empty and automatically removed by SessionManager
        REQUIRE(sm->get_session(s_id) == nullptr);

        // Check if p2_tank is available
        auto acquired_p2_tank = sm_test_tank_pool->acquire_tank();
        REQUIRE(acquired_p2_tank != nullptr);
        REQUIRE(acquired_p2_tank->get_id() == p2_tank_id);
        sm_test_tank_pool->release_tank(acquired_p2_tank->get_id());
    }
}
