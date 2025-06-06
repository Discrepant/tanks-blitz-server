#include "catch2/catch_all.hpp"
#include "../game_server_cpp/session_manager.h"
#include "catch2/catch_all.hpp"
#include "../game_server_cpp/session_manager.h"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h"

// Глобальные KafkaProducerHandler и TankPool для тестов SessionManager.
static KafkaProducerHandler sm_test_kafka_producer_recreated("localhost:29092");
static TankPool* sm_test_tank_pool_recreated = nullptr; // Будет инициализирован в настройке фикстуры/основного теста

// Тестовая фикстура для SessionManager для обработки состояния Singleton
struct SessionManagerTestFixtureRecreated {
    SessionManagerTestFixtureRecreated() {
        // Убедимся, что TankPool инициализирован перед SessionManager
        if (!sm_test_tank_pool_recreated) {
            sm_test_tank_pool_recreated = TankPool::get_instance(5, &sm_test_kafka_producer_recreated);
        }
        // Это упрощенный сброс для целей этих тестов.
        // Он не удаляет старый экземпляр, если он существовал, что приводит к утечке.
        // Правильный тестируемый singleton мог бы иметь статический метод reset.
        // Принудительное пересоздание путем обнуления SessionManager::instance_ отсюда невозможно
        // без объявления `instance_` публичным или добавления дружественного класса, что является интрузивным.
        // Мы будем полагаться на то, что эти тесты, вероятно, запускаются в свежей среде или принимают общее состояние.
        // Для смягчения, очищаем любые сессии в конце каждого тестового случая или секции.
    }

    ~SessionManagerTestFixtureRecreated() {
        SessionManager* sm = SessionManager::get_instance(sm_test_tank_pool_recreated, &sm_test_kafka_producer_recreated);
        if(sm){
            auto all_sessions = sm->get_all_sessions();
            for (auto& session : all_sessions) {
                sm->remove_session(session->get_id(), "test_fixture_cleanup");
            }
        }
    }

    void cleanup_sessions(SessionManager* sm) {
        if (!sm) return;
        auto all_sessions = sm->get_all_sessions();
        for (auto& session : all_sessions) {
            sm->remove_session(session->get_id(), "explicit_cleanup");
        }
    }
};


TEST_CASE_METHOD(SessionManagerTestFixtureRecreated, "SessionManager Recreated Tests", "[session_manager_recreated]") {
    REQUIRE(sm_test_tank_pool_recreated != nullptr);
    SessionManager* sm = SessionManager::get_instance(sm_test_tank_pool_recreated, &sm_test_kafka_producer_recreated);
    REQUIRE(sm != nullptr);

    // Очистка перед каждой секцией для максимальной изоляции с Singleton.
    cleanup_sessions(sm);


    SECTION("SessionManager Singleton Instance") { // Экземпляр Singleton SessionManager
        SessionManager* sm1 = SessionManager::get_instance(sm_test_tank_pool_recreated, &sm_test_kafka_producer_recreated);
        SessionManager* sm2 = SessionManager::get_instance();
        REQUIRE(sm1 == sm2);
        REQUIRE(sm1 != nullptr);
    }

    SECTION("Create and Get Session") { // Создание и получение сессии
        std::shared_ptr<GameSession> session1 = sm->create_session();
        REQUIRE(session1 != nullptr);
        REQUIRE_FALSE(session1->get_id().empty());
        REQUIRE(sm->get_active_sessions_count() == 1);

        std::shared_ptr<GameSession> retrieved_session1 = sm->get_session(session1->get_id());
        REQUIRE(retrieved_session1 != nullptr);
        REQUIRE(retrieved_session1->get_id() == session1->get_id());

        std::shared_ptr<GameSession> non_existent_session = sm->get_session("non_existent_id_rc_123");
        REQUIRE(non_existent_session == nullptr);
    }

    SECTION("Remove Session") { // Удаление сессии
        std::shared_ptr<GameSession> session_to_remove = sm->create_session();
        REQUIRE(session_to_remove != nullptr);
        std::string session_id = session_to_remove->get_id();

        auto tank_for_remove_test = sm_test_tank_pool_recreated->acquire_tank();
        REQUIRE(tank_for_remove_test != nullptr);
        sm->add_player_to_session(session_id, "player_in_removed_session_rc", "addr_rc", tank_for_remove_test, true);
        REQUIRE(sm->get_session_by_player_id("player_in_removed_session_rc") != nullptr);

        REQUIRE(sm->remove_session(session_id));
        REQUIRE(sm->get_session(session_id) == nullptr);
        REQUIRE(sm->get_session_by_player_id("player_in_removed_session_rc") == nullptr);

        REQUIRE_FALSE(sm->remove_session("non_existent_id_rc_456"));
    }

    SECTION("Player Lifecycle in SessionManager") { // Жизненный цикл игрока в SessionManager
        std::shared_ptr<GameSession> session = sm->create_session();
        REQUIRE(session != nullptr);
        std::string session_id = session->get_id();

        auto tank1 = sm_test_tank_pool_recreated->acquire_tank();
        REQUIRE(tank1 != nullptr);
        std::string tank1_id = tank1->get_id();

        std::shared_ptr<GameSession> joined_session = sm->add_player_to_session(session_id, "player_lc_rc_1", "udp_addr_lc_rc_1", tank1, true);
        REQUIRE(joined_session != nullptr);
        REQUIRE(joined_session->get_id() == session_id);
        REQUIRE(session->has_player("player_lc_rc_1"));
        REQUIRE(sm->get_session_by_player_id("player_lc_rc_1") == session);

        // Пытаемся добавить того же игрока снова (SessionManager::add_player_to_session обрабатывает это, возвращая существующую сессию)
        auto tank_dup = sm_test_tank_pool_recreated->acquire_tank();
        REQUIRE(tank_dup != nullptr);
        std::shared_ptr<GameSession> rejoined_session = sm->add_player_to_session(session_id, "player_lc_rc_1", "udp_addr_lc_rc_1_new", tank_dup, true);
        REQUIRE(rejoined_session != nullptr);
        REQUIRE(rejoined_session == session);
        REQUIRE(session->get_players_count() == 1);
        sm_test_tank_pool_recreated->release_tank(tank_dup->get_id()); // Освобождаем неиспользуемый танк

        REQUIRE(sm->remove_player_from_any_session("player_lc_rc_1"));
        REQUIRE_FALSE(session->has_player("player_lc_rc_1"));
        REQUIRE(sm->get_session_by_player_id("player_lc_rc_1") == nullptr);

        auto acquired_after_release = sm_test_tank_pool_recreated->acquire_tank();
        REQUIRE(acquired_after_release != nullptr);
        REQUIRE(acquired_after_release->get_id() == tank1_id);
        sm_test_tank_pool_recreated->release_tank(acquired_after_release->get_id());

        REQUIRE_FALSE(sm->remove_player_from_any_session("player_lc_rc_non_existent"));
        REQUIRE(sm->get_session(session_id) == nullptr); // Сессия должна быть автоматически удалена
    }

    SECTION("find_or_create_session_for_player") { // find_or_create_session_for_player
        int max_p = 2;
        auto p1_tank = sm_test_tank_pool_recreated->acquire_tank();
        REQUIRE(p1_tank != nullptr);
        std::shared_ptr<GameSession> s1 = sm->find_or_create_session_for_player("p_find_rc_1", "addr_f1", p1_tank, true, max_p);
        REQUIRE(s1 != nullptr);
        REQUIRE(s1->get_players_count() == 1);
        std::string s1_id = s1->get_id();

        auto p2_tank = sm_test_tank_pool_recreated->acquire_tank();
        REQUIRE(p2_tank != nullptr);
        std::shared_ptr<GameSession> s2 = sm->find_or_create_session_for_player("p_find_rc_2", "addr_f2", p2_tank, true, max_p);
        REQUIRE(s2 != nullptr);
        REQUIRE(s2->get_id() == s1_id); // Должен присоединиться к существующей сессии s1
        REQUIRE(s1->get_players_count() == 2);

        auto p3_tank = sm_test_tank_pool_recreated->acquire_tank();
        REQUIRE(p3_tank != nullptr);
        std::shared_ptr<GameSession> s3 = sm->find_or_create_session_for_player("p_find_rc_3", "addr_f3", p3_tank, true, max_p);
        REQUIRE(s3 != nullptr);
        REQUIRE(s3->get_id() != s1_id); // Должен создать новую сессию, так как s1 заполнена
        REQUIRE(s3->get_players_count() == 1);

        // Очищаем танки, удаляя игроков
        sm->remove_player_from_any_session("p_find_rc_1");
        sm->remove_player_from_any_session("p_find_rc_2"); // s1 должна быть автоматически удалена
        sm->remove_player_from_any_session("p_find_rc_3"); // s3 должна быть автоматически удалена
        REQUIRE(sm->get_session(s1_id) == nullptr);
        REQUIRE(sm->get_session(s3->get_id()) == nullptr);
    }
}
