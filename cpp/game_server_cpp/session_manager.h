#ifndef SESSION_MANAGER_H
#define SESSION_MANAGER_H

#include <string>
#include <map>
#include <memory>   // For std::shared_ptr
#include <mutex>    // For std::mutex and std::lock_guard
#include <vector>

#include "game_session.h"           // Definition of GameSession
#include "tank_pool.h"              // Definition of TankPool
#include "kafka_producer_handler.h" // For sending Kafka events (optional here, could be only in .cpp)
#include <nlohmann/json_fwd.hpp>    // Forward declaration for nlohmann::json if only used in .cpp for Kafka

class SessionManager {
public:
    // Singleton access method
    // For the first call, tank_pool and kafka_handler must not be null.
    static SessionManager* get_instance(TankPool* tank_pool = nullptr, KafkaProducerHandler* kafka_handler = nullptr);

    // Deleted copy constructor and assignment operator for Singleton pattern
    SessionManager(const SessionManager&) = delete;
    SessionManager& operator=(const SessionManager&) = delete;

    // Session management
    std::shared_ptr<GameSession> create_session();
    std::shared_ptr<GameSession> get_session(const std::string& session_id);
    bool remove_session(const std::string& session_id, const std::string& reason = "explicitly_removed");

    // Player management within sessions
    std::shared_ptr<GameSession> add_player_to_session(
        const std::string& session_id,
        const std::string& player_id,
        const std::string& player_address_info, // Can be UDP "ip:port" or TCP username
        std::shared_ptr<Tank> tank,
        bool is_udp_player);

    bool remove_player_from_any_session(const std::string& player_id);

    std::shared_ptr<GameSession> get_session_by_player_id(const std::string& player_id);

    // New helper method to find a session with space or create a new one.
    std::shared_ptr<GameSession> find_or_create_session_for_player(
        const std::string& player_id,
        const std::string& player_address_info,
        std::shared_ptr<Tank> tank,
        bool is_udp_player,
        int max_players_per_session = 2); // Example default max players

    // Utility
    size_t get_active_sessions_count() const;
    std::vector<std::shared_ptr<GameSession>> get_all_sessions() const; // For admin or broadcast purposes

    static const std::string KAFKA_TOPIC_PLAYER_SESSIONS;

private:
    // Private constructor for Singleton
    SessionManager(TankPool* tank_pool, KafkaProducerHandler* kafka_handler);
    ~SessionManager() = default; // Default destructor is fine

    void send_kafka_event(const nlohmann::json& event_payload) const;

    static SessionManager* instance_;
    static std::mutex singleton_mutex_; // Mutex for thread-safe Singleton creation

    mutable std::mutex manager_mutex_; // Mutex for thread-safe access to SessionManager's maps

    std::map<std::string, std::shared_ptr<GameSession>> sessions_; // session_id -> GameSession object
    std::map<std::string, std::string> player_to_session_map_; // player_id -> session_id

    TankPool* tank_pool_; // Raw pointer, lifetime managed externally (e.g., by main)
    KafkaProducerHandler* kafka_producer_handler_; // Raw pointer, lifetime managed externally

    long long next_session_numeric_id_ = 0; // For generating simple unique session IDs
};

#endif // SESSION_MANAGER_H
