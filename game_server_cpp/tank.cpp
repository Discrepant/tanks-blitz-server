#include "tank.h"
#include <iostream> // For std::cout, std::cerr

// Initialize static const members
const std::string Tank::KAFKA_TOPIC_TANK_COORDINATES = "tank_coordinates";
const std::string Tank::KAFKA_TOPIC_GAME_EVENTS = "game_events";

Tank::Tank(std::string id,
           KafkaProducerHandler* kafka_handler,
           nlohmann::json initial_position,
           int initial_health)
    : tank_id_(std::move(id)),
      kafka_producer_handler_(kafka_handler),
      position_(std::move(initial_position)),
      health_(initial_health),
      is_active_(false) { // Default to inactive
    std::cout << "Tank " << tank_id_ << " created. Initial state: " << get_state().dump() << std::endl;
    if (!kafka_producer_handler_ || !kafka_producer_handler_->is_valid()) {
        std::cerr << "Warning: KafkaProducerHandler is null or invalid for Tank " << tank_id_ << ". Kafka messages will not be sent." << std::endl;
    }
}

void Tank::move(const nlohmann::json& new_position) {
    if (!is_active_) {
        std::cout << "Tank " << tank_id_ << " is inactive. Move command ignored." << std::endl;
        return;
    }

    // Basic validation for new_position (e.g., ensure it has "x" and "y")
    if (!new_position.contains("x") || !new_position.contains("y")) {
        std::cerr << "Tank " << tank_id_ << " move error: new_position format is invalid. Expected {\"x\": value, \"y\": value}." << std::endl;
        return;
    }

    this->position_ = new_position;
    std::cout << "Tank " << tank_id_ << " moved to " << this->position_.dump() << std::endl;

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_moved"},
            {"tank_id", this->tank_id_},
            {"new_position", this->position_},
            {"timestamp", std::time(nullptr)} // Example timestamp
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_TANK_COORDINATES, kafka_message);
    }
}

void Tank::shoot() {
    if (!is_active_) {
        std::cout << "Tank " << tank_id_ << " is inactive. Shoot command ignored." << std::endl;
        return;
    }
    std::cout << "Tank " << tank_id_ << " shoots!" << std::endl;

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_shot"},
            {"tank_id", this->tank_id_},
            {"position", this->position_}, // Include position at time of shooting
            // Future: add projectile_id, direction, target_id etc.
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, kafka_message);
    }
}

void Tank::take_damage(int damage) {
    if (!is_active_) {
        // std::cout << "Tank " << tank_id_ << " is inactive. Cannot take damage." << std::endl;
        // Damage could still be applied if hit while inactive, depending on game rules.
        // For now, let's allow it.
    }

    this->health_ -= damage;
    bool destroyed = false;
    if (this->health_ <= 0) {
        this->health_ = 0;
        destroyed = true;
        // is_active_ = false; // Or handle deactivation in game logic/TankPool
        std::cout << "Tank " << tank_id_ << " took " << damage << " damage. Health is now " << this->health_ << ". Tank Destroyed!" << std::endl;
    } else {
        std::cout << "Tank " << tank_id_ << " took " << damage << " damage. Health is now " << this->health_ << std::endl;
    }

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json damage_event_message = {
            {"event_type", "tank_took_damage"},
            {"tank_id", this->tank_id_},
            {"damage_amount", damage},
            {"current_health", this->health_},
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, damage_event_message);

        if (destroyed) {
            nlohmann::json destroyed_event_message = {
                {"event_type", "tank_destroyed"},
                {"tank_id", this->tank_id_},
                {"last_position", this->position_},
                {"timestamp", std::time(nullptr)}
            };
            kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, destroyed_event_message);
            // Deactivation logic might be better handled by a TankPool or GameSession
            // set_active(false);
        }
    }
}

void Tank::reset(nlohmann::json initial_position, int health) {
    this->position_ = std::move(initial_position);
    this->health_ = health;
    set_active(false); // Ensure tank is marked inactive on reset and event is sent if status changed.
    std::cout << "Tank " << tank_id_ << " has been reset. New state: " << get_state().dump() << std::endl;

    // Optionally send a specific "tank_reset" event to Kafka if different from "tank_deactivated"
    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_reset"},
            {"tank_id", this->tank_id_},
            {"new_state", get_state()}, // Send the full new state on reset
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, kafka_message);
    }
}

nlohmann::json Tank::get_state() const {
    return {
        {"id", this->tank_id_},
        {"position", this->position_},
        {"health", this->health_},
        {"is_active", this->is_active_} // Include active status in state
    };
}

bool Tank::is_active() const {
    return this->is_active_;
}

void Tank::set_active(bool active_status) {
    if (this->is_active_ == active_status) return; // No change

    if (this->is_active_ == active_status) { // Only proceed if status actually changes
        // std::cout << "Tank " << tank_id_ << " active status already " << active_status << ". No change." << std::endl;
        return;
    }

    this->is_active_ = active_status;
    std::cout << "Tank " << tank_id_ << " active status set to: " << this->is_active_ << std::endl;

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", this->is_active_ ? "tank_activated" : "tank_deactivated"},
            {"tank_id", this->tank_id_},
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, kafka_message);
    }
}

const std::string& Tank::get_id() const {
    return this->tank_id_;
}
