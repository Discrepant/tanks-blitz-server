#include "catch2/catch_all.hpp"
#include "../game_server_cpp/tank.h"
#include "../game_server_cpp/kafka_producer_handler.h" // Включаем реальный обработчик Kafka

// Примечание: Чтобы эти тесты выполнялись без ошибок, связанных с Kafka, выводимых в консоль (если Kafka не запущена),
// KafkaProducerHandler должен корректно обрабатывать сбой конструктора или сбой send_message.
// Сами тесты будут сосредоточены на состоянии Tank, а не на успешной доставке Kafka.

TEST_CASE("Tank Class Tests", "[tank]") {
    // Для конструктора Tank необходим KafkaProducerHandler.
    // Он создается здесь, но его экземпляр Kafka может не работать во время тестов.
    // Операции, отправляющие сообщения Kafka, попытаются это сделать; тесты сосредоточены на состоянии Tank.
    // Используется фиктивный адрес брокера, так как он может не подключаться во время модульных тестов.
    // Если соединение Kafka критично для тестов, потребуется мок или тестовый экземпляр Kafka.
    KafkaProducerHandler test_kafka_producer("localhost:29092"); // Фиктивный брокер для тестов, если реальный не нужен

    SECTION("Tank Initialization") { // Инициализация танка
        Tank tank("tank_init_01", &test_kafka_producer, {{"x", 10}, {"y", 20}}, 150);
        REQUIRE(tank.get_id() == "tank_init_01");
        REQUIRE(tank.get_state()["health"] == 150);
        REQUIRE(tank.get_state()["position"]["x"] == 10);
        REQUIRE(tank.get_state()["position"]["y"] == 20);
        REQUIRE_FALSE(tank.is_active()); // Танки по умолчанию неактивны
        REQUIRE(tank.get_state()["active"] == false);
    }

    SECTION("Tank Activation and Deactivation") { // Активация и деактивация танка
        Tank tank("tank_active_01", &test_kafka_producer);
        REQUIRE_FALSE(tank.is_active());

        tank.set_active(true);
        REQUIRE(tank.is_active());
        REQUIRE(tank.get_state()["active"] == true);

        // Повторная установка active в true не должна ничего менять
        tank.set_active(true);
        REQUIRE(tank.is_active());

        tank.set_active(false);
        REQUIRE_FALSE(tank.is_active());
        REQUIRE(tank.get_state()["active"] == false);

        // Повторная установка active в false не должна ничего менять
        tank.set_active(false);
        REQUIRE_FALSE(tank.is_active());
    }

    SECTION("Tank Reset") { // Сброс состояния танка
        Tank tank("tank_reset_01", &test_kafka_producer, {{"x", 5}, {"y", 5}}, 50);
        tank.set_active(true); // Сначала активируем его
        REQUIRE(tank.is_active());

        tank.reset({{"x", 1}, {"y", 2}}, 90);
        REQUIRE(tank.get_id() == "tank_reset_01"); // ID должен сохраниться
        REQUIRE(tank.get_state()["health"] == 90);
        REQUIRE(tank.get_state()["position"]["x"] == 1);
        REQUIRE(tank.get_state()["position"]["y"] == 2);
        REQUIRE_FALSE(tank.is_active()); // Сброс должен деактивировать
        REQUIRE(tank.get_state()["active"] == false);

        // Сброс к значениям по умолчанию
        tank.set_active(true);
        tank.reset();
        REQUIRE(tank.get_state()["health"] == 100); // Здоровье по умолчанию
        REQUIRE(tank.get_state()["position"]["x"] == 0); // X по умолчанию
        REQUIRE(tank.get_state()["position"]["y"] == 0); // Y по умолчанию
        REQUIRE_FALSE(tank.is_active());
    }

    SECTION("Tank Movement") { // Перемещение танка
        Tank tank("tank_move_01", &test_kafka_producer);
        tank.set_active(true); // Должен быть активен для перемещения

        nlohmann::json new_pos = {{"x", 100}, {"y", 200}};
        tank.move(new_pos);
        REQUIRE(tank.get_state()["position"]["x"] == 100);
        REQUIRE(tank.get_state()["position"]["y"] == 200);

        // Перемещение в неактивном состоянии не должно изменять позицию
        tank.set_active(false);
        nlohmann::json another_pos = {{"x", -50}, {"y", -50}};
        tank.move(another_pos);
        REQUIRE(tank.get_state()["position"]["x"] == 100); // Позиция должна остаться неизменной
        REQUIRE(tank.get_state()["position"]["y"] == 200);
    }

    SECTION("Tank Shooting") { // Стрельба танка
        Tank tank("tank_shoot_01", &test_kafka_producer);
        tank.set_active(true);
        // Тест концептуален для сообщения Kafka. В самом объекте Tank состояние от shoot() не меняется.
        // Потребовался бы мок KafkaProducerHandler для проверки отправки сообщения.
        // Пока что просто убедимся, что не падает.
        REQUIRE_NOTHROW(tank.shoot());

        // Стрельба в неактивном состоянии не должна ничего делать / отправлять сообщение
        tank.set_active(false);
        REQUIRE_NOTHROW(tank.shoot());
    }

    SECTION("Tank Damage and Destruction") { // Получение урона и уничтожение танка
        Tank tank("tank_dmg_01", &test_kafka_producer, {{"x",0},{"y",0}}, 100);
        tank.set_active(true);

        tank.take_damage(30);
        REQUIRE(tank.get_state()["health"] == 70);

        tank.take_damage(60);
        REQUIRE(tank.get_state()["health"] == 10);

        // Урон, превышающий текущее здоровье
        tank.take_damage(25);
        REQUIRE(tank.get_state()["health"] == 0);
        // Танк может стать неактивным при уничтожении, в зависимости от игровой логики.
        // Текущий Tank::take_damage не устанавливает неактивность, это делает Tank::reset.
        // Это поведение должно быть согласованным или протестировано на соответствие конкретным правилам игры.
        // Пока предположим, что он остается активным, но с 0 здоровья, до явного сброса/деактивации игровой логикой.
        REQUIRE(tank.is_active()); // Или REQUIRE_FALSE(tank.is_active()), если take_damage(фатальный) деактивирует

        // Дальнейший урон при здоровье 0 не должен изменять здоровье
        tank.take_damage(10);
        REQUIRE(tank.get_state()["health"] == 0);
    }

    SECTION("Tank get_state method") { // Метод get_state танка
        Tank tank("tank_getstate_01", &test_kafka_producer, {{"x", 7},{"y", 17}}, 77);
        nlohmann::json state = tank.get_state();
        REQUIRE(state["id"] == "tank_getstate_01");
        REQUIRE(state["position"]["x"] == 7);
        REQUIRE(state["position"]["y"] == 17);
        REQUIRE(state["health"] == 77);
        REQUIRE(state["active"] == false);

        tank.set_active(true);
        state = tank.get_state();
        REQUIRE(state["active"] == true);
    }
}
