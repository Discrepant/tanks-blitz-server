#include "catch2/catch_all.hpp"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h" // Для конструктора TankPool

// Глобальный KafkaProducerHandler для тестов, требующих его для первого вызова TankPool::get_instance
// Это сложно, потому что TankPool - это синглтон и принимает KafkaProducerHandler*.
// Если тесты запускаются параллельно или Catch2 изменяет их порядок, важен первый вызов get_instance.
// Для простоты мы создадим его здесь. В более сложном сценарии может потребоваться фикстура.
// Или TankPool::get_instance можно сделать так, чтобы он не требовал KafkaProducerHandler после первой инициализации,
// или разрешить повторную инициализацию с новым (нежелательно для синглтона).
// Текущий TankPool::get_instance использует kafka_handler, только если instance_ равен nullptr.
static KafkaProducerHandler test_tp_kafka_producer("localhost:29092"); // Фиктивный брокер

// Вспомогательная функция для сброса состояния синглтона TankPool для изолированных тестов, если возможно.
// Обычно синглтоны так не тестируются. Правильное тестирование синглтонов сложно.
// Для этих тестов мы предполагаем, что get_instance() вызывается, и затем мы работаем с этим экземпляром.
// Мы не можем легко сбросить синглтон без специального метода сброса, что является анти-паттерном.
// Таким образом, тесты будут работать с одним и тем же экземпляром TankPool. Порядок может иметь значение.
// Catch2 запускает тестовые случаи в порядке их появления, но секции могут быть переупорядочены.

TEST_CASE("TankPool Tests", "[tank_pool]") {
    // Убедимся в наличии действительного KafkaProducerHandler для первого вызова get_instance в тестовом запуске.
    // Если Kafka не запущена, TankPool все равно инициализируется, но Танки не будут отправлять сообщения.
    // Это приемлемо для тестирования логики TankPool.
    size_t initial_pool_size = 5;
    TankPool* tank_pool = TankPool::get_instance(initial_pool_size, &test_tp_kafka_producer);
    REQUIRE(tank_pool != nullptr);

    // Примечание: Поскольку TankPool является синглтоном, его состояние сохраняется между SECTION в этом TEST_CASE
    // если они запускаются одним и тем же вызовом сессии Catch2 без перекомпиляции/перезапуска.
    // Это не идеально для изоляции модульных тестов. Правильная настройка тестов может включать
    // способ сброса синглтона или использование паттерна внедрения зависимостей для TankPool.
    // Пока что мы пишем тесты, зная это ограничение.

    SECTION("TankPool Singleton Instance") { // Экземпляр Singleton TankPool
        TankPool* tp1 = TankPool::get_instance(initial_pool_size, &test_tp_kafka_producer);
        TankPool* tp2 = TankPool::get_instance(); // Последующие вызовы не должны требовать параметров
        REQUIRE(tp1 == tp2);
        REQUIRE(tp1 != nullptr);
    }

    // SECTION("TankPool Initialization") // Инициализация TankPool
    // Это сложно протестировать в изоляции из-за состояния синглтона.
    // Первый вызов get_instance в этом файле уже инициализирует его.
    // Мы можем сделать вывод о его состоянии из тестов acquire/release.
    // Например, после первого get_instance попытаться получить `initial_pool_size` танков.

    SECTION("Acquire and Release Tanks") { // Получение и освобождение танков
        std::shared_ptr<Tank> t1 = tank_pool->acquire_tank();
        REQUIRE(t1 != nullptr);
        REQUIRE(t1->is_active() == true);
        REQUIRE(t1->get_state()["active"] == true);
        std::string t1_id = t1->get_id();

        std::shared_ptr<Tank> t2 = tank_pool->acquire_tank();
        REQUIRE(t2 != nullptr);
        REQUIRE(t2->is_active() == true);
        REQUIRE(t1_id != t2->get_id()); // Должны быть разные танки
        std::string t2_id = t2->get_id();

        // Получаем используемый танк
        std::shared_ptr<Tank> get_t1 = tank_pool->get_tank(t1_id);
        REQUIRE(get_t1 != nullptr);
        REQUIRE(get_t1 == t1);

        tank_pool->release_tank(t1_id);
        REQUIRE_FALSE(t1->is_active()); // Танк t1 (shared_ptr все еще существует) должен быть неактивным
                                       // и сброшен (здоровье 100, поз. 0,0)
        REQUIRE(t1->get_state()["health"] == 100);
        REQUIRE(t1->get_state()["position"]["x"] == 0);


        std::shared_ptr<Tank> get_t1_after_release = tank_pool->get_tank(t1_id);
        REQUIRE(get_t1_after_release == nullptr); // Не должен быть в "in_use_tanks"

        // Получаем снова, можем получить t1 обратно
        std::shared_ptr<Tank> t3 = tank_pool->acquire_tank();
        REQUIRE(t3 != nullptr);
        REQUIRE(t3->is_active() == true);
        // Возможно, t3 - это t1, если только один был освобожден и используется LIFO.
        // Если t1_id был помещен в конец available_tank_ids_, а затем извлечен.
        REQUIRE(t3->get_id() == t1_id); // Предполагаем LIFO для available_tank_ids_

        tank_pool->release_tank(t2_id);
        tank_pool->release_tank(t3->get_id()); // который является t1
    }

    SECTION("Acquire all tanks and try one more") { // Получить все танки и попробовать еще один
        std::vector<std::shared_ptr<Tank>> acquired_tanks;
        for (size_t i = 0; i < initial_pool_size; ++i) {
            std::shared_ptr<Tank> t = tank_pool->acquire_tank();
            REQUIRE(t != nullptr);
            acquired_tanks.push_back(t);
        }

        // Пытаемся получить на один больше, чем доступно
        std::shared_ptr<Tank> extra_tank = tank_pool->acquire_tank();
        REQUIRE(extra_tank == nullptr);

        // Освобождаем все полученные танки
        for (const auto& t : acquired_tanks) {
            if (t) tank_pool->release_tank(t->get_id());
        }
        acquired_tanks.clear();
    }

    SECTION("Release non-existent or already released tank") { // Освобождение несуществующего или уже освобожденного танка
        // Убедимся, что пул в каком-то известном состоянии, например, доступен хотя бы один танк
        std::shared_ptr<Tank> t = tank_pool->acquire_tank();
        REQUIRE(t != nullptr);
        std::string valid_id = t->get_id();
        tank_pool->release_tank(valid_id); // Освобождаем его

        REQUIRE_NOTHROW(tank_pool->release_tank("non_existent_tank_id_123"));
        REQUIRE_NOTHROW(tank_pool->release_tank(valid_id)); // Повторное освобождение уже освобожденного танка
    }

    SECTION("Get non-existent tank") { // Получение несуществующего танка
        std::shared_ptr<Tank> non_existent = tank_pool->get_tank("tank_id_that_does_not_exist_456");
        REQUIRE(non_existent == nullptr);
    }
}
