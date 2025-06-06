#include "tank.h"
#include <iostream> // Для std::cout, std::cerr для логирования
#include <ctime>    // Для std::time для временных меток

// Инициализация статических const членов
// Изменено KAFKA_TOPIC_TANK_COORDINATES на "tank_coordinates_history" согласно заданию
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
      is_active_(false) { // По умолчанию неактивен
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
    // std::cout << "Tank " << tank_id_ << " moved to " << this->position_.dump() << std::endl; // Может быть слишком подробно

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_moved"},
            {"tank_id", this->tank_id_},
            {"position", this->position_}, // Изменено с "new_position" на "position" для согласованности
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
    // std::cout << "Tank " << tank_id_ << " shoots!" << std::endl; // Может быть слишком подробно

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
    if (damage <= 0) return; // Нет урона или лечения через этот метод

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
            {"is_destroyed", destroyed}, // Добавлен флаг
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, damage_event_message);

        if (destroyed) {
            // Событие "tank_destroyed" может быть избыточным, если "tank_took_damage" включает "is_destroyed: true"
            // Однако, специфическое событие может быть полезно для разных потребителей.
            nlohmann::json destroyed_event_message = {
                {"event_type", "tank_destroyed"},
                {"tank_id", this->tank_id_},
                {"last_position", this->position_},
                {"timestamp", std::time(nullptr)}
            };
            kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, destroyed_event_message);
            // Деактивация должна обрабатываться игровой логикой/TankPool при получении "tank_destroyed" или достижении здоровья 0.
            // Сам танк не деактивирует себя просто от получения урона. set_active(false) вызывается при сбросе.
        }
    }
}

void Tank::reset(nlohmann::json initial_position, int health) {
    this->position_ = std::move(initial_position);
    this->health_ = health;
    bool old_active_status = this->is_active_;

    // set_active(false) обработает отправку события деактивации, если он был активен
    set_active(false);

    // std::cout << "Tank " << tank_id_ << " has been reset. New state: " << get_state().dump() << std::endl;

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", "tank_reset"},
            {"tank_id", this->tank_id_},
            {"new_state", this->get_state()}, // get_state() теперь включает 'active:false'
            {"timestamp", std::time(nullptr)}
        };
        kafka_producer_handler_->send_message(KAFKA_TOPIC_GAME_EVENTS, kafka_message);
    }
}

void Tank::set_active(bool active_status) {
    if (this->is_active_ == active_status) { // Продолжаем, только если статус действительно изменился
        return;
    }

    this->is_active_ = active_status;
    // std::cout << "Tank " << tank_id_ << " active status set to: " << this->is_active_ << std::endl;

    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        nlohmann::json kafka_message = {
            {"event_type", this->is_active_ ? "tank_activated" : "tank_deactivated"},
            {"tank_id", this->tank_id_},
            {"current_state", this->get_state()}, // Отправляем полное состояние при активации/деактивации
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
        {"active", this->is_active_} // Изменено с "is_active" на "active" для согласованности
    };
}

bool Tank::is_active() const {
    return this->is_active_;
}

const std::string& Tank::get_id() const {
    return this->tank_id_;
}
