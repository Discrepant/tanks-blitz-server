#ifndef SESSION_MANAGER_H
#define SESSION_MANAGER_H

#include <string>
#include <map>
#include <memory>   // For std::shared_ptr
#include <mutex>    // For std::mutex and std::lock_guard
#include <vector>

#include "game_session.h"
#include "tank_pool.h"
#include "kafka_producer_handler.h" // For sending Kafka events

class SessionManager {
public:
    // Singleton access method
    // For the first call, tank_pool and kafka_handler must not be null.
    static SessionManager* get_instance(TankPool* tank_pool = nullptr, KafkaProducerHandler* kafka_handler = nullptr);

    // Deleted copy constructor and assignment operator for Singleton
    SessionManager(const SessionManager&) = delete;
    SessionManager& operator=(const SessionManager&) = delete;

    // Session management
    std::shared_ptr<GameSession> create_session(); // Creates a new game session
    std::shared_ptr<GameSession> get_session(const std::string& session_id);
    bool remove_session(const std::string& session_id, const std::string& reason = "explicitly_removed"); // Removes a session and all its players

    // Player management within sessions
    // Adds a player to a specific session. If session_id is empty, might try to find one or create new.
    std::shared_ptr<GameSession> add_player_to_session(const std::string& session_id,
                                                       const std::string& player_id,
                                                       const std::string& player_address_info,
                                                       std::shared_ptr<Tank> tank,
                                                       bool is_udp_player = true);

    // Removes a player from their current session. Releases their tank.
    bool remove_player_from_any_session(const std::string& player_id);

    std::shared_ptr<GameSession> get_session_by_player_id(const std::string& player_id);

    // Utility
    size_t get_active_sessions_count() const;
    std::vector<std::shared_ptr<GameSession>> get_all_sessions() const;


    static const std::string KAFKA_TOPIC_PLAYER_SESSIONS;

private:
    // Private constructor for Singleton
    SessionManager(TankPool* tank_pool, KafkaProducerHandler* kafka_handler);
    ~SessionManager() = default;

    void send_kafka_event(const nlohmann::json& event_payload) const;

    static SessionManager* instance_;
    static std::mutex mutex_;

    std::map<std::string, std::shared_ptr<GameSession>> sessions_; // session_id -> GameSession object
    std::map<std::string, std::string> player_to_session_map_; // player_id -> session_id

    TankPool* tank_pool_; // Raw pointer, lifetime managed externally by main
    KafkaProducerHandler* kafka_producer_handler_; // Raw pointer, lifetime managed externally by main

    long long next_session_numeric_id_ = 0; // For generating simple unique session IDs
};

#endif // SESSION_MANAGER_H
