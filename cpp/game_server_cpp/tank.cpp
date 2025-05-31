#include "tank.h"
#include <iostream> // For std::cout, std::cerr for logging
#include <ctime>    // For std::time for timestamps

// Initialize static const members
// Changed KAFKA_TOPIC_TANK_COORDINATES to "tank_coordinates_history" as per prompt
const std::string Tank::KAFKA_TOPIC_TANK_COORDINATES = "tank_coordinates_history";
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
        std::cerr << "Tank " << tank_id_ << " Warning: KafkaProducerHandler is null or invalid. Kafka messages will not be sent." << std::endl;
    }
}

void Tank::move(const nlohmann::json& new_position) {
    if (!is_active_) {
        std::cout << "Tank " << tank_id_ << " is inactive. Move command ignored." << std::endl;
        return;
    }

    if (!new_position.contains("x") || !new_position.contains("y") ||
        !new_position["x"].is_number() || !new_position["y"].is_number()) {
        std::cerr << "Tank " << tank_id_ << " move error: new_position format is invalid. Expected {\"x\": number, \"y\": number}." << std::endl;
        return;
    }

    this->position_ = new_position;
    // std::cout << "Tank " << tank_id_ << " moved to " << this->position_.dump() << std::endl; // Can be verbose

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_moved"},
            {"tank_id", this->tank_id_},
            {"position", this->position_}, // Changed from "new_position" to "position" for consistency
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_TANK_COORDINATES, kafka_message);
    }
}

void Tank::shoot() {
    if (!is_active_) {
        std::cout << "Tank " << tank_id_ << " is inactive. Shoot command ignored." << std::endl;
        return;
    }
    // std::cout << "Tank " << tank_id_ << " shoots!" << std::endl; // Can be verbose

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_shot"},
            {"tank_id", this->tank_id_},
            {"position_at_shot", this->position_},
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, kafka_message);
    }
}

void Tank::take_damage(int damage) {
    if (damage <= 0) return; // No damage or healing through this method

    this->health_ -= damage;
    bool destroyed = false;
    if (this->health_ <= 0) {
        this->health_ = 0;
        destroyed = true;
        // std::cout << "Tank " << tank_id_ << " took " << damage << " damage. Health is now " << this->health_ << ". Tank Destroyed!" << std::endl;
    } else {
        // std::cout << "Tank " << tank_id_ << " took " << damage << " damage. Health is now " << this->health_ << std::endl;
    }

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json damage_event_message = {
            {"event_type", "tank_took_damage"},
            {"tank_id", this->tank_id_},
            {"damage_amount", damage},
            {"current_health", this->health_},
            {"is_destroyed", destroyed}, // Added flag
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, damage_event_message);

        if (destroyed) {
            // The "tank_destroyed" event might be redundant if "tank_took_damage" includes "is_destroyed: true"
            // However, specific event might be useful for different consumers.
            nlohmann::json destroyed_event_message = {
                {"event_type", "tank_destroyed"},
                {"tank_id", this->tank_id_},
                {"last_position", this->position_},
                {"timestamp", std::time(nullptr)}
            };
            kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, destroyed_event_message);
            // Deactivation should be handled by game logic/TankPool upon receiving "tank_destroyed" or health reaching 0.
            // Tank itself does not deactivate itself from just taking damage. set_active(false) is called on reset.
        }
    }
}

void Tank::reset(nlohmann::json initial_position, int health) {
    this->position_ = std::move(initial_position);
    this->health_ = health;
    bool old_active_status = this->is_active_;

    // set_active(false) will handle sending deactivation event if it was active
    set_active(false);

    // std::cout << "Tank " << tank_id_ << " has been reset. New state: " << get_state().dump() << std::endl;

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_reset"},
            {"tank_id", this->tank_id_},
            {"new_state", this->get_state()}, // get_state() now includes 'active:false'
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, kafka_message);
    }
}

void Tank::set_active(bool active_status) {
    if (this->is_active_ == active_status) { // Only proceed if status actually changes
        return;
    }

    this->is_active_ = active_status;
    // std::cout << "Tank " << tank_id_ << " active status set to: " << this->is_active_ << std::endl;

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", this->is_active_ ? "tank_activated" : "tank_deactivated"},
            {"tank_id", this->tank_id_},
            {"current_state", this->get_state()}, // Send full state on activation/deactivation
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
        {"active", this->is_active_} // Changed from "is_active" to "active" for consistency
    };
}

bool Tank::is_active() const {
    return this->is_active_;
}

const std::string& Tank::get_id() const {
    return this->tank_id_;
}
