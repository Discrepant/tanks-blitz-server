#ifndef TANK_POOL_H
#define TANK_POOL_H

#include <vector>
#include <string>
#include <memory> // For std::shared_ptr
#include <map>
#include <mutex>    // For std::mutex and std::lock_guard
#include <stdexcept> // For std::runtime_error (optional, for errors)

#include "tank.h"
#include "kafka_producer_handler.h" // Assuming this is in the same directory or include paths are set

class TankPool {
public:
    // Singleton access method
    // For the first call, kafka_handler must not be null.
    // Subsequent calls can ignore pool_size and kafka_handler or use them to verify.
    static TankPool* get_instance(size_t pool_size = 10, KafkaProducerHandler* kafka_handler = nullptr);

    // Deleted copy constructor and assignment operator for Singleton
    TankPool(const TankPool&) = delete;
    TankPool& operator=(const TankPool&) = delete;

    std::shared_ptr<Tank> acquire_tank();
    void release_tank(const std::string& tank_id);
    std::shared_ptr<Tank> get_tank(const std::string& tank_id); // Get a tank currently in use

    // For cleanup if necessary, though Singleton typically lives for the program duration
    // static void destroy_instance();

private:
    // Private constructor for Singleton
    TankPool(size_t pool_size, KafkaProducerHandler* kafka_handler);
    ~TankPool() = default; // Default destructor is fine for now

    static TankPool* instance_;
    static std::mutex mutex_;

    // Holds all tank objects ever created. Tank ID is the key.
    std::map<std::string, std::shared_ptr<Tank>> all_tanks_;

    // IDs of tanks that are currently available for acquisition.
    std::vector<std::string> available_tank_ids_;

    // Tanks that are currently acquired and in use. Tank ID is the key.
    // Storing shared_ptr here to keep them alive while in use.
    std::map<std::string, std::shared_ptr<Tank>> in_use_tanks_;

    KafkaProducerHandler* kafka_producer_handler_; // Raw pointer, lifetime managed externally
    size_t initial_pool_size_;
};

#endif // TANK_POOL_H
