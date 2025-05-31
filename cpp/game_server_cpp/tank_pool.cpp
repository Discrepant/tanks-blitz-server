#include "tank_pool.h"
#include <iostream>  // For std::cout, std::cerr for logging
#include <algorithm> // For std::find (used in release_tank to check for duplicates, optional)

// Define static members
TankPool* TankPool::instance_ = nullptr;
std::mutex TankPool::mutex_; // Ensure this is defined

TankPool::TankPool(size_t pool_size, KafkaProducerHandler* kafka_handler)
    : kafka_producer_handler_(kafka_handler), initial_pool_size_(pool_size) {

    if (pool_size > 0 && (!kafka_handler || !kafka_handler->is_valid())) {
        // This check is crucial if tanks require a valid kafka_handler to function correctly.
        std::cerr << "TankPool Warning: KafkaProducerHandler is null or invalid during construction, "
                  << "but pool_size is " << pool_size << ". Tanks may not function as expected." << std::endl;
        // Depending on strictness, could throw or mark TankPool as invalid.
    }

    std::cout << "TankPool: Initializing with pool size: " << pool_size << std::endl;
    for (size_t i = 0; i < pool_size; ++i) {
        std::string tank_id = "tank_" + std::to_string(i);
        // Create tank with default position and health, pass the kafka_handler
        auto tank = std::make_shared<Tank>(tank_id, kafka_producer_handler_);
        all_tanks_[tank_id] = tank;
        available_tank_ids_.push_back(tank_id);
        // Tanks are initially inactive (Tank constructor sets is_active_ = false).
    }
    std::cout << "TankPool: " << all_tanks_.size() << " tanks initialized and added to the available pool." << std::endl;
}

TankPool* TankPool::get_instance(size_t pool_size, KafkaProducerHandler* kafka_handler) {
    std::lock_guard<std::mutex> lock(mutex_); // Thread-safe initialization for the singleton
    if (instance_ == nullptr) {
        if (pool_size > 0 && kafka_handler == nullptr) { // Kafka handler is essential if tanks are to be created
            std::cerr << "TankPool Critical Error: First call to get_instance() with pool_size > 0 "
                      << "requires a valid KafkaProducerHandler." << std::endl;
            return nullptr;
        }
        if (pool_size > 0 && kafka_handler != nullptr && !kafka_handler->is_valid()) {
             std::cerr << "TankPool Critical Error: Provided KafkaProducerHandler is not valid for first init with pool_size > 0." << std::endl;
            return nullptr;
        }
        instance_ = new TankPool(pool_size, kafka_handler);
    }
    // Note: Subsequent calls to get_instance currently ignore pool_size and kafka_handler.
    // If re-configuration is desired, the singleton pattern might need adjustment or a separate reinit method.
    return instance_;
}

std::shared_ptr<Tank> TankPool::acquire_tank() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (available_tank_ids_.empty()) {
        std::cerr << "TankPool Warning: No tanks available for acquisition." << std::endl;
        return nullptr;
    }

    std::string tank_id = available_tank_ids_.back(); // LIFO behavior
    available_tank_ids_.pop_back();

    auto tank_it = all_tanks_.find(tank_id);
    if (tank_it == all_tanks_.end()) {
        // This indicates an inconsistency, should ideally not happen.
        std::cerr << "TankPool Error: Tank ID " << tank_id
                  << " from available list not found in all_tanks_ map. Re-adding ID to available." << std::endl;
        available_tank_ids_.push_back(tank_id); // Put it back to try to prevent endless loop if logic error
        return nullptr;
    }

    std::shared_ptr<Tank> tank = tank_it->second;

    tank->reset();          // Ensure tank is in a default state (also calls set_active(false))
    tank->set_active(true); // Now activate it for use (this will send "tank_activated" event)

    in_use_tanks_[tank_id] = tank;

    std::cout << "TankPool: Tank " << tank_id << " acquired. Available: " << available_tank_ids_.size()
              << ", In Use: " << in_use_tanks_.size() << std::endl;
    return tank;
}

void TankPool::release_tank(const std::string& tank_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = in_use_tanks_.find(tank_id);
    if (it == in_use_tanks_.end()) {
        std::cerr << "TankPool Warning: Attempted to release tank '" << tank_id
                  << "' which is not currently in use or does not exist." << std::endl;
        return;
    }

    std::shared_ptr<Tank> tank = it->second;
    tank->reset(); // This calls set_active(false) and sends "tank_reset" & "tank_deactivated" Kafka events.

    in_use_tanks_.erase(it);

    // Add ID back to available_tank_ids_ only if it's not already there (safety check)
    if (std::find(available_tank_ids_.begin(), available_tank_ids_.end(), tank_id) == available_tank_ids_.end()) {
        available_tank_ids_.push_back(tank_id);
    } else {
        // This case should ideally not be reached if acquire/release logic is sound.
        std::cerr << "TankPool Warning: Tank ID " << tank_id
                  << " already in available_tank_ids_ during release. Possible logic issue." << std::endl;
    }

    std::cout << "TankPool: Tank " << tank_id << " released. Available: " << available_tank_ids_.size()
              << ", In Use: " << in_use_tanks_.size() << std::endl;
}

std::shared_ptr<Tank> TankPool::get_tank(const std::string& tank_id) {
    std::lock_guard<std::mutex> lock(mutex_); // Protects access to in_use_tanks_
    auto it = in_use_tanks_.find(tank_id);
    if (it != in_use_tanks_.end()) {
        return it->second; // Return shared_ptr to the tank
    }
    // std::cout << "TankPool: Tank " << tank_id << " not found in in_use_tanks_." << std::endl; // Can be verbose
    return nullptr; // Tank not in use or doesn't exist by that ID in the "in_use" map
}

size_t TankPool::get_available_tanks_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return available_tank_ids_.size();
}

size_t TankPool::get_in_use_tanks_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return in_use_tanks_.size();
}

size_t TankPool::get_total_tanks_count() const {
     std::lock_guard<std::mutex> lock(mutex_);
    return all_tanks_.size();
}
