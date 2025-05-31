#ifndef TANK_H
#define TANK_H

#include <string>
#include <nlohmann/json.hpp>
#include "kafka_producer_handler.h" // Assumes kafka_producer_handler.h is in the same directory

class Tank {
public:
    Tank(std::string id,
         KafkaProducerHandler* kafka_handler,
         nlohmann::json initial_position = {{"x", 0}, {"y", 0}},
         int initial_health = 100);

    // Deleted copy constructor and assignment operator to prevent accidental copying
    // if Tank objects are meant to be unique and managed by TankPool.
    Tank(const Tank&) = delete;
    Tank& operator=(const Tank&) = delete;

    void move(const nlohmann::json& new_position);
    void shoot();
    void take_damage(int damage);
    void reset(nlohmann::json initial_position = {{"x", 0}, {"y", 0}}, int health = 100);

    nlohmann::json get_state() const;
    bool is_active() const;
    void set_active(bool active_status); // Manages activation and deactivation events
    const std::string& get_id() const;

    // Static constants for Kafka topics
    static const std::string KAFKA_TOPIC_TANK_COORDINATES;
    static const std::string KAFKA_TOPIC_GAME_EVENTS;

private:
    std::string tank_id_;
    nlohmann::json position_; // e.g., {"x": 10, "y": 25}
    int health_;
    bool is_active_ = false; // Tanks are inactive until explicitly set active

    KafkaProducerHandler* kafka_producer_handler_; // Raw pointer, lifetime managed externally
};

#endif // TANK_H
