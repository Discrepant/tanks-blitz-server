#include "tank_pool.h"
#include <iostream> // For std::cout, std::cerr
#include <algorithm> // For std::remove

// Define static members
TankPool* TankPool::instance_ = nullptr;
std::mutex TankPool::mutex_;

TankPool::TankPool(size_t pool_size, KafkaProducerHandler* kafka_handler)
    : kafka_producer_handler_(kafka_handler), initial_pool_size_(pool_size) {
    if (!kafka_handler || !kafka_handler->is_valid()) {
        // This check is important, but get_instance should handle the null kafka_handler for first call.
        // However, if it's somehow constructed directly with an invalid handler, this is a fallback.
        std::cerr << "TankPool Error: KafkaProducerHandler is null or invalid during construction." << std::endl;
        // Optionally throw an exception or mark the pool as invalid.
        // For now, it will proceed but Kafka features in Tanks will be disabled.
    }

    std::cout << "Initializing TankPool with size: " << pool_size << std::endl;
    for (size_t i = 0; i < pool_size; ++i) {
        std::string tank_id = "tank_" + std::to_string(i);
        // Create tank with default position and health, pass the kafka_handler
        auto tank = std::make_shared<Tank>(tank_id, kafka_producer_handler_);
        all_tanks_[tank_id] = tank;
        available_tank_ids_.push_back(tank_id);
        // Tanks are initially inactive. They will be activated upon acquisition.
    }
    std::cout << initial_pool_size_ << " tanks initialized and added to the available pool." << std::endl;
}

TankPool* TankPool::get_instance(size_t pool_size, KafkaProducerHandler* kafka_handler) {
    std::lock_guard<std::mutex> lock(mutex_); // Thread-safe initialization
    if (instance_ == nullptr) {
        if (kafka_handler == nullptr) {
            std::cerr << "TankPool Critical Error: First call to get_instance() requires a valid KafkaProducerHandler." << std::endl;
            return nullptr; // Or throw std::runtime_error
        }
        if (!kafka_handler->is_valid()) {
             std::cerr << "TankPool Critical Error: Provided KafkaProducerHandler is not valid." << std::endl;
            return nullptr; // Or throw std::runtime_error
        }
        instance_ = new TankPool(pool_size, kafka_handler);
    }
    // Optionally, subsequent calls could verify if pool_size matches or log if different.
    // For now, they just return the existing instance.
    return instance_;
}

std::shared_ptr<Tank> TankPool::acquire_tank() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (available_tank_ids_.empty()) {
        std::cerr << "TankPool Warning: No tanks available for acquisition." << std::endl;
        return nullptr;
    }

    std::string tank_id = available_tank_ids_.back();
    available_tank_ids_.pop_back();

    auto tank_it = all_tanks_.find(tank_id);
    if (tank_it == all_tanks_.end()) {
        // This should not happen if available_tank_ids_ is consistent with all_tanks_
        std::cerr << "TankPool Error: Tank ID " << tank_id << " from available list not found in all_tanks_ map." << std::endl;
        // Attempt to recover or just return null
        return nullptr;
    }

    std::shared_ptr<Tank> tank = tank_it->second;
    in_use_tanks_[tank_id] = tank;

    tank->set_active(true); // Activate the tank
    // tank->reset(); // Ensure it's in a default state (reset already calls set_active(false), so set_active(true) must be after)
                     // Let's refine: reset should prepare it, then set_active(true).
                     // Current Tank::reset does not change active status, so set_active(true) is fine.
                     // However, a tank coming from pool should be in a pristine state.
    tank->reset(); // Reset to default position/health. set_active(false) is called within reset.
    tank->set_active(true); // Now activate it for use.

    std::cout << "TankPool: Tank " << tank_id << " acquired. Available tanks: " << available_tank_ids_.size() << std::endl;
    return tank;
}

void TankPool::release_tank(const std::string& tank_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = in_use_tanks_.find(tank_id);
    if (it == in_use_tanks_.end()) {
        std::cerr << "TankPool Warning: Attempted to release tank " << tank_id << " which is not in use or does not exist." << std::endl;
        return;
    }

    std::shared_ptr<Tank> tank = it->second;
    tank->reset(); // This will call set_active(false) and send Kafka event.

    in_use_tanks_.erase(it);

    // Check if tank_id is already in available_tank_ids_ to prevent duplicates (should not happen with proper logic)
    if (std::find(available_tank_ids_.begin(), available_tank_ids_.end(), tank_id) == available_tank_ids_.end()) {
        available_tank_ids_.push_back(tank_id);
    } else {
        std::cerr << "TankPool Warning: Tank ID " << tank_id << " already in available list during release." << std::endl;
    }

    std::cout << "TankPool: Tank " << tank_id << " released. Available tanks: " << available_tank_ids_.size() << std::endl;
}

std::shared_ptr<Tank> TankPool::get_tank(const std::string& tank_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = in_use_tanks_.find(tank_id);
    if (it != in_use_tanks_.end()) {
        return it->second;
    }
    // Optionally, check all_tanks_ if you want to get any tank, even if not in use.
    // For this method, "get_tank" implies getting an active/in-use tank.
    std::cout << "TankPool: Tank " << tank_id << " not found in in_use_tanks_." << std::endl;
    return nullptr;
}

// Optional: Implement destroy_instance if manual cleanup is ever needed
// void TankPool::destroy_instance() {
//     std::lock_guard<std::mutex> lock(mutex_);
//     delete instance_;
//     instance_ = nullptr;
// }
