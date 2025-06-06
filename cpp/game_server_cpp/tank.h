#ifndef TANK_H
#define TANK_H

#include <string>
#include <nlohmann/json.hpp>
#include "kafka_producer_handler.h" // Предполагается, что kafka_producer_handler.h находится в том же каталоге

class Tank {
public:
    Tank(std::string id,
         KafkaProducerHandler* kafka_handler,
         nlohmann::json initial_position = {{"x", 0}, {"y", 0}},
         int initial_health = 100);

    // Удаленные конструктор копирования и оператор присваивания для предотвращения случайного копирования,
    // если объекты Tank должны быть уникальными и управляться TankPool.
    Tank(const Tank&) = delete;
    Tank& operator=(const Tank&) = delete;

    void move(const nlohmann::json& new_position);
    void shoot();
    void take_damage(int damage);
    void reset(nlohmann::json initial_position = {{"x", 0}, {"y", 0}}, int health = 100);

    nlohmann::json get_state() const;
    bool is_active() const;
    void set_active(bool active_status); // Управляет событиями активации и деактивации
    const std::string& get_id() const;

    // Статические константы для топиков Kafka
    static const std::string KAFKA_TOPIC_TANK_COORDINATES;
    static const std::string KAFKA_TOPIC_GAME_EVENTS;

private:
    std::string tank_id_;
    nlohmann::json position_; // например, {"x": 10, "y": 25}
    int health_;
    bool is_active_ = false; // Танки неактивны, пока явно не активированы

    KafkaProducerHandler* kafka_producer_handler_; // Сырой указатель, время жизни управляется извне
};

#endif // TANK_H
