#include "session_manager.h"
#include <iostream> // For logging
#include <nlohmann/json.hpp> // For Kafka events

// Define static members
SessionManager* SessionManager::instance_ = nullptr;
std::mutex SessionManager::mutex_;
const std::string SessionManager::KAFKA_TOPIC_PLAYER_SESSIONS = "player_sessions";

SessionManager::SessionManager(TankPool* tank_pool, KafkaProducerHandler* kafka_handler)
    : tank_pool_(tank_pool), kafka_producer_handler_(kafka_handler), next_session_numeric_id_(0) {
    if (!tank_pool_) {
        std::cerr << "SessionManager Critical Error: TankPool is null during construction." << std::endl;
        // This is a critical dependency, consider throwing or marking manager as invalid.
    }
    if (!kafka_producer_handler_ || !kafka_producer_handler_->is_valid()) {
        std::cerr << "SessionManager Warning: KafkaProducerHandler is null or invalid. Kafka events for sessions will not be sent." << std::endl;
    }
    std::cout << "SessionManager initialized." << std::endl;
}

SessionManager* SessionManager::get_instance(TankPool* tank_pool, KafkaProducerHandler* kafka_handler) {
    std::lock_guard<std::mutex> lock(mutex_); // Thread-safe initialization
    if (instance_ == nullptr) {
        if (tank_pool == nullptr) {
            std::cerr << "SessionManager Critical Error: First call to get_instance() requires a valid TankPool." << std::endl;
            return nullptr;
        }
        // kafka_handler can be null if Kafka is not used for session events, but log a warning.
        if (kafka_handler == nullptr || !kafka_handler->is_valid()) {
             std::cerr << "SessionManager Warning: KafkaProducerHandler is null or invalid during first get_instance call. Session Kafka events may not be sent." << std::endl;
        }
        instance_ = new SessionManager(tank_pool, kafka_handler);
    }
    return instance_;
}

std::shared_ptr<GameSession> SessionManager::create_session() {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string session_id = "session_" + std::to_string(next_session_numeric_id_++);
    auto session = std::make_shared<GameSession>(session_id);
    sessions_[session_id] = session;

    std::cout << "SessionManager: Created new session " << session_id << std::endl;

    nlohmann::json event_payload = {
        {"event_type", "session_created"},
        {"session_id", session_id},
        {"timestamp", std::time(nullptr)},
        {"initial_state", session->get_game_state_info()}
    };
    send_kafka_event(event_payload);

    return session;
}

std::shared_ptr<GameSession> SessionManager::get_session(const std::string& session_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = sessions_.find(session_id);
    if (it != sessions_.end()) {
        return it->second;
    }
    std::cout << "SessionManager: Session " << session_id << " not found." << std::endl;
    return nullptr;
}

bool SessionManager::remove_session(const std::string& session_id, const std::string& reason) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = sessions_.find(session_id);
    if (it != sessions_.end()) {
        std::shared_ptr<GameSession> session_to_remove = it->second;
        std::cout << "SessionManager: Removing session " << session_id << " due to: " << reason << std::endl;

        // Remove all players from this session
        std::vector<std::string> players_in_session_to_remove;
        for(const auto& player_entry : session_to_remove->get_players()){
            players_in_session_to_remove.push_back(player_entry.first);
        }

        for(const std::string& player_id : players_in_session_to_remove){
            // This calls release_tank internally
            // We must call the public remove_player_from_any_session to ensure player_to_session_map_ is also cleared
            // However, that would re-lock the mutex. So, do the core logic here.
             std::cout << "SessionManager: Removing player " << player_id << " from session " << session_id << " during session removal." << std::endl;
            auto tank = session_to_remove->get_tank_for_player(player_id);
            if(tank && tank_pool_){
                tank_pool_->release_tank(tank->get_id());
            }
            player_to_session_map_.erase(player_id);
        }
        session_to_remove->get_players().clear(); // Clear internal map in GameSession, though it will be destroyed.

        sessions_.erase(it);
        std::cout << "SessionManager: Session " << session_id << " removed. Active sessions: " << sessions_.size() << std::endl;

        nlohmann::json event_payload = {
            {"event_type", "session_removed"},
            {"session_id", session_id},
            {"reason", reason},
            {"timestamp", std::time(nullptr)}
        };
        send_kafka_event(event_payload);
        return true;
    }
    std::cerr << "SessionManager: Session " << session_id << " not found for removal." << std::endl;
    return false;
}


std::shared_ptr<GameSession> SessionManager::add_player_to_session(
    const std::string& session_id,
    const std::string& player_id,
    const std::string& player_address_info,
    std::shared_ptr<Tank> tank,
    bool is_udp_player) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (!tank) {
        std::cerr << "SessionManager: Cannot add player " << player_id << " with a null tank." << std::endl;
        return nullptr;
    }
    if (player_to_session_map_.count(player_id)) {
         std::cerr << "SessionManager: Player " << player_id << " is already in session " << player_to_session_map_[player_id] << ". Cannot add to " << session_id << std::endl;
        return sessions_[player_to_session_map_[player_id]]; // Return existing session
    }

    auto session_it = sessions_.find(session_id);
    if (session_it == sessions_.end()) {
        std::cerr << "SessionManager: Session " << session_id << " not found. Cannot add player " << player_id << "." << std::endl;
        return nullptr; // Or create new session? For now, require explicit session.
    }

    std::shared_ptr<GameSession> session = session_it->second;
    if (session->add_player(player_id, player_address_info, tank, is_udp_player)) {
        player_to_session_map_[player_id] = session_id;
        std::cout << "SessionManager: Player " << player_id << " added to session " << session_id << "." << std::endl;

        nlohmann::json event_payload = {
            {"event_type", "player_joined_session"},
            {"player_id", player_id},
            {"session_id", session_id},
            {"tank_id", tank->get_id()},
            {"player_address_info", player_address_info},
            {"is_udp_player", is_udp_player},
            {"timestamp", std::time(nullptr)}
        };
        send_kafka_event(event_payload);
        return session;
    } else {
        std::cerr << "SessionManager: Failed to add player " << player_id << " to session " << session_id << " (GameSession::add_player failed)." << std::endl;
        return nullptr;
    }
}

bool SessionManager::remove_player_from_any_session(const std::string& player_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto map_it = player_to_session_map_.find(player_id);
    if (map_it == player_to_session_map_.end()) {
        std::cerr << "SessionManager: Player " << player_id << " not found in any session for removal." << std::endl;
        return false;
    }

    std::string session_id = map_it->second;
    auto session_it = sessions_.find(session_id);
    if (session_it == sessions_.end()) {
        // Should not happen if player_to_session_map_ is consistent
        std::cerr << "SessionManager Error: Player " << player_id << " mapped to non-existent session " << session_id << "." << std::endl;
        player_to_session_map_.erase(map_it); // Clean up inconsistent map entry
        return false;
    }

    std::shared_ptr<GameSession> session = session_it->second;
    std::shared_ptr<Tank> tank = session->get_tank_for_player(player_id);

    if (session->remove_player(player_id)) {
        player_to_session_map_.erase(map_it);
        std::cout << "SessionManager: Player " << player_id << " removed from session " << session_id << "." << std::endl;

        if (tank && tank_pool_) {
            tank_pool_->release_tank(tank->get_id()); // This also resets and deactivates the tank
        } else if (!tank_pool_) {
             std::cerr << "SessionManager Error: TankPool is null, cannot release tank for player " << player_id << std::endl;
        }


        nlohmann::json event_payload = {
            {"event_type", "player_left_session"},
            {"player_id", player_id},
            {"session_id", session_id},
            {"tank_id", tank ? tank->get_id() : "N/A"},
            {"timestamp", std::time(nullptr)}
        };
        send_kafka_event(event_payload);

        // Optional: Remove session if it becomes empty
        if (session->is_empty()) {
            std::cout << "SessionManager: Session " << session_id << " is now empty and will be removed." << std::endl;
            // Need to call the public remove_session to ensure Kafka event for session_removed
            // This will re-lock, which is not ideal. Better to have a private _remove_session_nolock
            // For now, this is simpler but less efficient.
            // To avoid re-locking, we can extract the core logic of remove_session.
            // For this pass, I'll leave it as is and note potential for re-entrancy or do a simpler erase.
             sessions_.erase(session_it); // Simpler erase without re-lock or full remove_session logic for now
             std::cout << "SessionManager: Session " << session_id << " (empty) directly erased." << std::endl;
             nlohmann::json empty_session_event = {
                {"event_type", "session_removed"},
                {"session_id", session_id},
                {"reason", "became_empty"},
                {"timestamp", std::time(nullptr)}
             };
             send_kafka_event(empty_session_event);

        }
        return true;
    }
    return false;
}

std::shared_ptr<GameSession> SessionManager::get_session_by_player_id(const std::string& player_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto map_it = player_to_session_map_.find(player_id);
    if (map_it != player_to_session_map_.end()) {
        auto session_it = sessions_.find(map_it->second);
        if (session_it != sessions_.end()) {
            return session_it->second;
        }
    }
    return nullptr;
}

size_t SessionManager::get_active_sessions_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return sessions_.size();
}

std::vector<std::shared_ptr<GameSession>> SessionManager::get_all_sessions() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::shared_ptr<GameSession>> all_sessions_vec;
    for (const auto& pair : sessions_) {
        all_sessions_vec.push_back(pair.second);
    }
    return all_sessions_vec;
}

void SessionManager::send_kafka_event(const nlohmann::json& event_payload) const {
    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        kafka_producer_handler_->send_message(KAFKA_TOPIC_PLAYER_SESSIONS, event_payload);
    } else {
        // std::cout << "SessionManager: Kafka producer not available, event not sent: " << event_payload.dump(2) << std::endl;
    }
}
