#include "catch2/catch_all.hpp"
#include "../game_server_cpp/command_consumer.h"
#include "../game_server_cpp/session_manager.h"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h" // Для инициализации SM и TP
#include "../game_server_cpp/tank.h" // Для проверки состояния танка

// Статические инициализаторы для зависимостей (TankPool и SessionManager являются синглтонами)
static KafkaProducerHandler cc_test_kafka_producer("localhost:29092"); // Фиктивный брокер
static TankPool* cc_test_tank_pool = TankPool::get_instance(5, &cc_test_kafka_producer);
static SessionManager* cc_test_session_manager = SessionManager::get_instance(cc_test_tank_pool, &cc_test_kafka_producer);

struct CommandConsumerTestFixture {
    PlayerCommandConsumer consumer;

    CommandConsumerTestFixture()
        : consumer(cc_test_session_manager, cc_test_tank_pool, "dummy_host", 0, "dummy_user", "dummy_pass") {
        // Убедимся, что синглтоны инициализированы
        REQUIRE(cc_test_tank_pool != nullptr);
        REQUIRE(cc_test_session_manager != nullptr);

        // Очищаем существующие сессии/игроков из предыдущих тестовых случаев для обеспечения изоляции
        auto all_sessions = cc_test_session_manager->get_all_sessions();
        for (const auto& session : all_sessions) {
            cc_test_session_manager->remove_session(session->get_id(), "fixture_setup_cleanup");
        }
        // Убедимся, что все танки в пуле доступны (освобождены)
        // Это сложно, так как у нас нет прямого "release_all_tanks" или сброса самого пула.
        // Пока что полагаемся на то, что отдельные тесты управляют приобретаемыми ими танками.
    }

    ~CommandConsumerTestFixture() {
        // Деструктор Consumer вызовет stop(), если он был запущен.
        // Здесь мы тестируем только handle_command_logic, а не запускаем поток потребителя.
    }

    // Вспомогательная функция для создания игрока и назначения ему танка для тестов
    std::shared_ptr<Tank> setup_player_in_session(const std::string& player_id, const std::string& session_id_hint = "test_session") {
        auto tank = cc_test_tank_pool->acquire_tank();
        REQUIRE(tank != nullptr); // Убедимся, что танк успешно получен
        tank->set_active(true);

        // Используем find_or_create_session, чтобы убедиться, что игрок находится в сессии
        // Если нужен конкретный ID сессии, сначала создайте ее, затем добавьте игрока.
        auto session = cc_test_session_manager->find_or_create_session_for_player(
            player_id,
            "udp_test_addr",
            tank,
            true);
        REQUIRE(session != nullptr); // Убедимся, что сессия была создана/найдена
        REQUIRE(session->has_player(player_id));
        return tank;
    }
};

TEST_CASE_METHOD(CommandConsumerTestFixture, "PlayerCommandConsumer::handle_command_logic Tests", "[command_consumer]") {

    SECTION("Valid 'move' command") { // Корректная команда 'move'
        std::string player_id = "player_move_test";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);
        tank->move({{"x", 0}, {"y", 0}}); // Сбрасываем позицию для предсказуемого теста

        nlohmann::json move_payload = {
            {"player_id", player_id},
            {"command", "move"},
            {"details", {
                {"new_position", {{"x", 10}, {"y", 20}}}
            }}
        };

        REQUIRE_NOTHROW(consumer.handle_command_logic(move_payload));

        // Проверяем состояние танка
        auto session = cc_test_session_manager->get_session_by_player_id(player_id);
        REQUIRE(session != nullptr);
        auto tank_in_session = session->get_tank_for_player(player_id);
        REQUIRE(tank_in_session != nullptr);
        REQUIRE(tank_in_session->get_state()["position"]["x"] == 10);
        REQUIRE(tank_in_session->get_state()["position"]["y"] == 20);

        // Очистка
        cc_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Valid 'shoot' command") { // Корректная команда 'shoot'
        std::string player_id = "player_shoot_test";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);

        nlohmann::json shoot_payload = {
            {"player_id", player_id},
            {"command", "shoot"},
            {"details", {}} // Детали выстрела пока могут быть пустыми
        };

        // Проверяем, что не выбрасывается исключение и команда принимается логикой.
        // Фактический tank->shoot() отправляет сообщение Kafka, которое мы здесь не проверяем.
        REQUIRE(consumer.handle_command_logic(shoot_payload) == true);
        // Прямого изменения состояния в объекте Tank от shoot() для проверки здесь нет.

        // Очистка
        cc_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Command for player not in session") { // Команда для игрока не в сессии
        nlohmann::json move_payload = {
            {"player_id", "player_not_in_session"},
            {"command", "move"},
            {"details", {{"new_position", {{"x", 5}, {"y", 5}}}}}
        };
        // Должно быть обработано корректно, залогировано, и сообщение подтверждено (возвращает true)
        REQUIRE(consumer.handle_command_logic(move_payload) == true);
    }

    SECTION("Command for player in session but tank is inactive") { // Команда для игрока в сессии, но танк неактивен
        std::string player_id = "player_inactive_tank";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);
        tank->set_active(false); // Делаем танк неактивным
        tank->move({{"x", 0}, {"y", 0}}); // Известная позиция

        nlohmann::json move_payload = {
            {"player_id", player_id},
            {"command", "move"},
            {"details", {{"new_position", {{"x", 15}, {"y", 25}}}}}
        };
        REQUIRE(consumer.handle_command_logic(move_payload) == true); // Команда обработана, но танк ее игнорирует

        REQUIRE(tank->get_state()["position"]["x"] == 0); // Позиция не должна была измениться
        REQUIRE(tank->get_state()["position"]["y"] == 0);

        cc_test_session_manager->remove_player_from_any_session(player_id);
    }

    SECTION("Invalid JSON payload structure") { // Некорректная структура JSON-нагрузки
        nlohmann::json missing_player_id = {
            // player_id отсутствует
            {"command", "move"},
            {"details", {{"new_position", {{"x", 1}, {"y", 1}}}}}
        };
         // handle_command_logic выбрасывает runtime_error для отсутствующих полей
        REQUIRE_THROWS_AS(consumer.handle_command_logic(missing_player_id), std::runtime_error);


        nlohmann::json missing_command = {
            {"player_id", "some_player"},
            // command отсутствует
            {"details", {{"new_position", {{"x", 1}, {"y", 1}}}}}
        };
        REQUIRE_THROWS_AS(consumer.handle_command_logic(missing_command), std::runtime_error);

        nlohmann::json missing_details = {
            {"player_id", "some_player"},
            {"command", "move"}
            // details отсутствует
        };
        // Для 'move' details.new_position проверяется внутри handle_command_logic -> tank->move
        // Сам handle_command_logic может не выбросить исключение, если отсутствует только details, но специфичная логика move выбросит.
        // Текущий handle_command_logic для "move" проверяет details.contains("new_position")
        REQUIRE_THROWS_AS(consumer.handle_command_logic(missing_details), std::runtime_error);
    }

    SECTION("Move command missing new_position in details") { // Команда 'move' без new_position в details
        std::string player_id = "player_move_bad_details";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);

        nlohmann::json move_bad_details_payload = {
            {"player_id", player_id},
            {"command", "move"},
            {"details", {}} // new_position отсутствует
        };
        // Tank::move залогирует ошибку и не сдвинется. handle_command_logic выбросит исключение.
        REQUIRE_THROWS_AS(consumer.handle_command_logic(move_bad_details_payload), std::runtime_error);

        cc_test_session_manager->remove_player_from_any_session(player_id);
    }


    SECTION("Unknown command type") { // Неизвестный тип команды
        std::string player_id = "player_unknown_cmd";
        auto tank = setup_player_in_session(player_id);
        REQUIRE(tank != nullptr);

        nlohmann::json unknown_command_payload = {
            {"player_id", player_id},
            {"command", "dance"}, // Неизвестная команда
            {"details", {}}
        };
        // Неизвестные команды логируются и подтверждаются (возвращает true)
        REQUIRE(consumer.handle_command_logic(unknown_command_payload) == true);

        cc_test_session_manager->remove_player_from_any_session(player_id);
    }
}
