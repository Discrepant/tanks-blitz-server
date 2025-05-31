#ifndef TANK_POOL_H
#define TANK_POOL_H

#include <vector>
#include <string>
#include <memory> // For std::shared_ptr
#include <map>
#include <mutex>    // For std::mutex and std::lock_guard
#include <stdexcept> // For std::runtime_error (optional, for errors if needed)

#include "tank.h"                   // Definition of the Tank class
#include "kafka_producer_handler.h" // For KafkaProducerHandler pointer

class TankPool {
public:
    // Singleton access method
    // For the first call, kafka_handler must not be null if pool_size > 0.
    static TankPool* get_instance(size_t pool_size = 10, KafkaProducerHandler* kafka_handler = nullptr);

    // Deleted copy constructor and assignment operator for Singleton pattern
    TankPool(const TankPool&) = delete;
    TankPool& operator=(const TankPool&) = delete;

    std::shared_ptr<Tank> acquire_tank();
    void release_tank(const std::string& tank_id);
    std::shared_ptr<Tank> get_tank(const std::string& tank_id); // Get a tank currently in use

    // Optional: Method to get current pool status (e.g., for monitoring or testing)
    size_t get_available_tanks_count() const;
    size_t get_in_use_tanks_count() const;
    size_t get_total_tanks_count() const;


private:
    // Private constructor for Singleton
    TankPool(size_t pool_size, KafkaProducerHandler* kafka_handler);
    // Private destructor to prevent accidental deletion via base class pointer if TankPool were to be inherited
    // and to ensure it's only deleted by a potential destroy_instance() or at program exit if needed.
    // For a simple singleton that lives for the duration of the app, default is often fine.
    ~TankPool() = default;

    static TankPool* instance_;
    static std::mutex mutex_; // Mutex for thread-safe singleton creation and pool operations

    // Holds all tank objects ever created. Tank ID is the key.
    std::map<std::string, std::shared_ptr<Tank>> all_tanks_;

    // IDs of tanks that are currently available for acquisition.
    std::vector<std::string> available_tank_ids_;

    // Tanks that are currently acquired and in use. Tank ID is the key.
    // Storing shared_ptr here to keep them alive while in use and allow shared access.
    std::map<std::string, std::shared_ptr<Tank>> in_use_tanks_;

    KafkaProducerHandler* kafka_producer_handler_; // Raw pointer, lifetime managed externally (e.g., by main)
    size_t initial_pool_size_;
};

#endif // TANK_POOL_H
