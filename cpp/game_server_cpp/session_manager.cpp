#include "session_manager.h"
#include <iostream> // For logging
#include <nlohmann/json.hpp> // For Kafka events JSON construction
#include <ctime>    // For timestamps

// Define static members
SessionManager* SessionManager::instance_ = nullptr;
std::mutex SessionManager::singleton_mutex_; // Mutex for singleton instantiation
const std::string SessionManager::KAFKA_TOPIC_PLAYER_SESSIONS = "player_sessions_history";

SessionManager::SessionManager(TankPool* tank_pool, KafkaProducerHandler* kafka_handler)
    : tank_pool_(tank_pool), kafka_producer_handler_(kafka_handler), next_session_numeric_id_(0) {
    if (!tank_pool_) {
        // This is a critical dependency. The application might not be able to function.
        std::cerr << "SessionManager CRITICAL ERROR: TankPool instance is null during construction." << std::endl;
        throw std::runtime_error("SessionManager requires a valid TankPool instance.");
    }
    if (!kafka_producer_handler_ || !kafka_producer_handler_->is_valid()) {
        std::cerr << "SessionManager WARNING: KafkaProducerHandler is null or invalid. "
                  << "Session-related Kafka events will not be sent." << std::endl;
    }
    std::cout << "SessionManager initialized." << std::endl;
}

SessionManager* SessionManager::get_instance(TankPool* tank_pool, KafkaProducerHandler* kafka_handler) {
    std::lock_guard<std::mutex> lock(singleton_mutex_);
    if (instance_ == nullptr) {
        if (tank_pool == nullptr) { // Must be provided on first call
            std::cerr << "SessionManager CRITICAL ERROR: First call to get_instance() requires a valid TankPool." << std::endl;
            return nullptr; // Or throw
        }
        // kafka_handler can be null if Kafka is not used, but log a warning.
        if (kafka_handler == nullptr || !kafka_handler->is_valid()) {
             std::cerr << "SessionManager WARNING: KafkaProducerHandler is null or invalid during first get_instance call. "
                       << "Session Kafka events may not be sent." << std::endl;
        }
        instance_ = new SessionManager(tank_pool, kafka_handler);
    }
    return instance_;
}

std::shared_ptr<GameSession> SessionManager::create_session() {
    std::lock_guard<std::mutex> lock(manager_mutex_);
    std::string session_id = "session_" + std::to_string(next_session_numeric_id_++);
    auto session = std::make_shared<GameSession>(session_id);
    sessions_[session_id] = session;

    std::cout << "SessionManager: Created new session " << session_id << std::endl;

    nlohmann::json event_payload = {
        {"event_type", "session_created"},
        {"session_id", session_id},
        {"timestamp", std::time(nullptr)},
        {"details", session->get_game_info()} // Include game_info from session
    };
    send_kafka_event(event_payload);

    return session;
}

std::shared_ptr<GameSession> SessionManager::get_session(const std::string& session_id) {
    std::lock_guard<std::mutex> lock(manager_mutex_);
    auto it = sessions_.find(session_id);
    if (it != sessions_.end()) {
        return it->second;
    }
    // std::cout << "SessionManager: Session " << session_id << " not found." << std::endl; // Can be verbose
    return nullptr;
}

bool SessionManager::remove_session(const std::string& session_id, const std::string& reason) {
    std::shared_ptr<GameSession> session_to_remove = nullptr;
    {
        std::lock_guard<std::mutex> lock(manager_mutex_);
        auto it = sessions_.find(session_id);
        if (it == sessions_.end()) {
            std::cerr << "SessionManager: Session " << session_id << " not found for removal." << std::endl;
            return false;
        }
        session_to_remove = it->second;
        sessions_.erase(it); // Remove from map under this lock
    } // Release manager_mutex_ before calling other methods or complex logic

    // Now handle players outside the main lock if possible, or re-lock selectively.
    // This example assumes GameSession methods are thread-safe.
    std::cout << "SessionManager: Removing session " << session_id << " (Reason: " << reason << ")" << std::endl;

    std::vector<std::string> players_in_session_to_remove;
    // GameSession::get_players() itself might need a lock if not const or if map can change
    // For now, assume GameSession::get_players() returns a safe way to iterate or its methods are thread-safe.
    // If GameSession::get_players() returns a const ref, its internal mutex protects it.
    const auto& players_map = session_to_remove->get_players();
    // If iterating this map while players can be removed from it by other threads, this is not safe.
    // For now, assume GameSession's internal mutex handles this during get_players() or it's a snapshot.
    // A safer way: copy player IDs under GameSession's lock, then process.
    // For simplicity in this step:
    for(const auto& player_entry : players_map){
        players_in_session_to_remove.push_back(player_entry.first);
    }

    // Re-lock manager_mutex_ to modify player_to_session_map_
    // This is simpler than trying to call remove_player_from_any_session which would re-lock.
    {
        std::lock_guard<std::mutex> lock(manager_mutex_);
        for(const std::string& player_id : players_in_session_to_remove){
            std::cout << "SessionManager: Player " << player_id << " is being removed from map due to session " << session_id << " removal." << std::endl;
            player_to_session_map_.erase(player_id);
            // Tank release should be handled by whoever called remove_session implicitly,
            // or if remove_session implies full cleanup, then tanks must be released here.
            // The prompt for remove_player_from_any_session says IT releases the tank.
            // If a session is removed directly, its players' tanks also need releasing.
            auto tank = session_to_remove->get_tank_for_player(player_id); // GameSession method, needs its own lock
            if (tank && tank_pool_) {
                 std::cout << "SessionManager: Releasing tank " << tank->get_id() << " for player " << player_id << " from removed session " << session_id << "." << std::endl;
                tank_pool_->release_tank(tank->get_id());
            }
        }
    }
    // The GameSession shared_ptr `session_to_remove` will be destroyed when it goes out of scope,
    // cleaning up its own data. GameSession::remove_player is not needed here if the whole session is gone.

    std::cout << "SessionManager: Session " << session_id << " removed. Active sessions: " << get_active_sessions_count() << std::endl;

    nlohmann::json event_payload = {
        {"event_type", "session_removed"},
        {"session_id", session_id},
        {"reason", reason},
        {"timestamp", std::time(nullptr)}
    };
    send_kafka_event(event_payload);
    return true;
}

std::shared_ptr<GameSession> SessionManager::add_player_to_session(
    const std::string& session_id,
    const std::string& player_id,
    const std::string& player_address_info,
    std::shared_ptr<Tank> tank,
    bool is_udp_player) {
    std::lock_guard<std::mutex> lock(manager_mutex_);

    if (!tank) {
        std::cerr << "SessionManager: Cannot add player " << player_id << " with a null tank." << std::endl;
        return nullptr;
    }
    // Check if player is already in another session
    if (player_to_session_map_.count(player_id)) {
        std::string existing_session_id = player_to_session_map_[player_id];
        if (existing_session_id != session_id) {
             std::cerr << "SessionManager: Player " << player_id << " is already in session "
                       << existing_session_id << ". Cannot add to " << session_id << std::endl;
             // Optionally, could remove from old session first, or just fail. For now, fail.
            return sessions_.count(existing_session_id) ? sessions_.at(existing_session_id) : nullptr;
        }
        // If already in the target session, GameSession::add_player will handle it (likely return false but player is there)
    }

    auto session_it = sessions_.find(session_id);
    if (session_it == sessions_.end()) {
        std::cerr << "SessionManager: Session " << session_id << " not found. Cannot add player " << player_id << "." << std::endl;
        return nullptr;
    }

    std::shared_ptr<GameSession> session = session_it->second;
    // GameSession::add_player is internally thread-safe
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
        // GameSession::add_player might fail if player_id already exists in that session.
        // std::cerr << "SessionManager: Failed to add player " << player_id << " to session " << session_id
        //           << " (GameSession::add_player failed)." << std::endl;
        // If it failed because player already there, then map might be correct or needs update.
        // For now, if GameSession::add_player fails, we assume player is not successfully in that session from SM's perspective for this call.
        // If player was already there, map entry is fine.
        if(session->has_player(player_id)) return session; // It means player was already in this session.
        return nullptr;
    }
}

bool SessionManager::remove_player_from_any_session(const std::string& player_id) {
    std::string session_id_of_player;
    std::shared_ptr<GameSession> session_ptr = nullptr;
    std::shared_ptr<Tank> tank_to_release = nullptr;

    { // Scope for manager_mutex_
        std::lock_guard<std::mutex> lock(manager_mutex_);
        auto map_it = player_to_session_map_.find(player_id);
        if (map_it == player_to_session_map_.end()) {
            std::cerr << "SessionManager: Player " << player_id << " not found in any session for removal." << std::endl;
            return false;
        }
        session_id_of_player = map_it->second;

        auto session_it = sessions_.find(session_id_of_player);
        if (session_it == sessions_.end()) {
            std::cerr << "SessionManager Error: Player " << player_id << " mapped to non-existent session "
                      << session_id_of_player << ". Removing map entry." << std::endl;
            player_to_session_map_.erase(map_it);
            return false;
        }
        session_ptr = session_it->second;

        // Get tank before removing player from session, to ensure we have its ID
        // GameSession methods are internally locked.
        tank_to_release = session_ptr->get_tank_for_player(player_id);

        if (session_ptr->remove_player(player_id)) {
            player_to_session_map_.erase(map_it);
            std::cout << "SessionManager: Player " << player_id << " removed from session " << session_id_of_player << "." << std::endl;
            // Tank release and Kafka event will happen outside this lock if tank_to_release is valid
        } else {
            // Should not happen if player was in player_to_session_map_ and session existed.
             std::cerr << "SessionManager Error: Failed to remove player " << player_id << " from session "
                       << session_id_of_player << " despite being mapped." << std::endl;
            return false;
        }
    } // Release manager_mutex_

    // Perform actions that don't require manager_mutex_ or might call back into SM (like remove_session)
    if (tank_to_release && tank_pool_) {
        tank_pool_->release_tank(tank_to_release->get_id());
    } else if (!tank_pool_) {
         std::cerr << "SessionManager Error: TankPool is null. Cannot release tank for player " << player_id << std::endl;
    }

    nlohmann::json event_payload = {
        {"event_type", "player_left_session"},
        {"player_id", player_id},
        {"session_id", session_id_of_player},
        {"tank_id", tank_to_release ? tank_to_release->get_id() : "N/A"},
        {"timestamp", std::time(nullptr)}
    };
    send_kafka_event(event_payload);

    if (session_ptr && session_ptr->is_empty()) { // GameSession::is_empty() is thread-safe
        std::cout << "SessionManager: Session " << session_id_of_player
                  << " is now empty and will be removed." << std::endl;
        remove_session(session_id_of_player, "became_empty_after_player_left"); // This will re-lock manager_mutex_
    }
    return true;
}

std::shared_ptr<GameSession> SessionManager::get_session_by_player_id(const std::string& player_id) {
    std::lock_guard<std::mutex> lock(manager_mutex_);
    auto map_it = player_to_session_map_.find(player_id);
    if (map_it != player_to_session_map_.end()) {
        auto session_it = sessions_.find(map_it->second);
        if (session_it != sessions_.end()) {
            return session_it->second;
        }
    }
    return nullptr;
}

std::shared_ptr<GameSession> SessionManager::find_or_create_session_for_player(
    const std::string& player_id,
    const std::string& player_address_info,
    std::shared_ptr<Tank> tank,
    bool is_udp_player,
    int max_players_per_session) {

    std::lock_guard<std::mutex> lock(manager_mutex_); // Lock for iterating sessions_ and potentially creating one

    if (!tank) {
        std::cerr << "SessionManager: Cannot find/create session for player " << player_id << " with a null tank." << std::endl;
        return nullptr;
    }
     if (player_to_session_map_.count(player_id)) {
        std::string existing_session_id = player_to_session_map_[player_id];
        std::cerr << "SessionManager: Player " << player_id << " is already in session "
                  << existing_session_id << ". Returning existing session." << std::endl;
        return sessions_.count(existing_session_id) ? sessions_.at(existing_session_id) : nullptr;
    }


    // Try to find an existing session with space
    for (auto const& [session_id, session_ptr] : sessions_) {
        // GameSession::get_players_count() is thread-safe
        if (session_ptr->get_players_count() < static_cast<size_t>(max_players_per_session)) {
            // Attempt to add player to this session.
            // Release current lock before calling add_player_to_session which will re-lock.
            // This is tricky. Let's simplify: add_player_to_session needs the session_id.
            // We have session_id and session_ptr.
            // The public add_player_to_session re-locks. We need an internal non-locking version or careful lock release.
            // For now, let's unlock and call the public one. This is not perfectly atomic but simpler.
            // This means another thread could quickly fill the session.
            // A better way would be to pass the session_ptr to add_player_to_session.
            // Let's try to add directly to GameSession here, then update map.

            // GameSession::add_player is thread-safe
            if (session_ptr->add_player(player_id, player_address_info, tank, is_udp_player)) {
                player_to_session_map_[player_id] = session_id; // Update map under current lock
                std::cout << "SessionManager: Player " << player_id << " added to existing session " << session_id << "." << std::endl;
                // Send Kafka event (copied from add_player_to_session for consistency)
                nlohmann::json event_payload = {
                    {"event_type", "player_joined_session"},
                    {"player_id", player_id},
                    {"session_id", session_id},
                    {"tank_id", tank->get_id()},
                    {"player_address_info", player_address_info},
                    {"is_udp_player", is_udp_player},
                    {"timestamp", std::time(nullptr)}
                };
                send_kafka_event(event_payload); // send_kafka_event is const, no re-entrancy issues with manager_mutex_
                return session_ptr;
            }
            // If add_player failed (e.g. player already in THAT session, which shouldn't happen if not in map), loop continues.
        }
    }

    // No suitable existing session found, create a new one
    // Release current lock before calling create_session and add_player_to_session (they lock themselves).
    // This is also non-atomic. A thread could create a session in between.
    // To make it atomic, create_session and add_player_to_session would need _nolock versions.
    // For simplicity of this step, we accept this minor race condition for finding vs creating.
    // The impact is low (might create one extra session than strictly needed if two players join simultaneously).

    // Hold lock for create_session part only
    std::string new_session_id = "session_" + std::to_string(next_session_numeric_id_++);
    auto new_session = std::make_shared<GameSession>(new_session_id);
    sessions_[new_session_id] = new_session;

    // GameSession::add_player is thread-safe
    if (new_session->add_player(player_id, player_address_info, tank, is_udp_player)) {
        player_to_session_map_[player_id] = new_session_id;
        std::cout << "SessionManager: Created new session " << new_session_id << " for player " << player_id << "." << std::endl;

        // Send Kafka events (session_created is sent by create_session logic if we called that)
        // Since we created it manually here to control locking:
        nlohmann::json session_event = {
            {"event_type", "session_created"},
            {"session_id", new_session_id},
            {"timestamp", std::time(nullptr)},
            {"details", new_session->get_game_info()}
        };
        send_kafka_event(session_event);

        nlohmann::json player_event = {
            {"event_type", "player_joined_session"},
            {"player_id", player_id},
            {"session_id", new_session_id},
            {"tank_id", tank->get_id()},
            {"player_address_info", player_address_info},
            {"is_udp_player", is_udp_player},
            {"timestamp", std::time(nullptr)}
        };
        send_kafka_event(player_event);
        return new_session;
    } else {
        // Should not happen if player wasn't in map and session is brand new.
        std::cerr << "SessionManager Error: Failed to add player " << player_id << " to newly created session " << new_session_id << std::endl;
        sessions_.erase(new_session_id); // Clean up failed session creation attempt
        // Tank is not released here as it's passed in, caller should manage if this fails.
        return nullptr;
    }
}


size_t SessionManager::get_active_sessions_count() const {
    std::lock_guard<std::mutex> lock(manager_mutex_);
    return sessions_.size();
}

std::vector<std::shared_ptr<GameSession>> SessionManager::get_all_sessions() const {
    std::lock_guard<std::mutex> lock(manager_mutex_);
    std::vector<std::shared_ptr<GameSession>> all_sessions_vec;
    all_sessions_vec.reserve(sessions_.size());
    for (const auto& pair : sessions_) {
        all_sessions_vec.push_back(pair.second);
    }
    return all_sessions_vec;
}

void SessionManager::send_kafka_event(const nlohmann::json& event_payload) const {
    if (kafka_producer_handler_ && kafka_producer_handler_->is_valid()) {
        kafka_producer_handler_->send_message(KAFKA_TOPIC_PLAYER_SESSIONS, event_payload);
    } else {
        // This might be too verbose if Kafka is intentionally disabled.
        // std::cout << "SessionManager: Kafka producer not available, event not sent: " << event_payload.dump(2) << std::endl;
    }
}
