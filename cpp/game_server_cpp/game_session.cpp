#include "game_session.h"
#include <iostream> // For logging
#include <ctime>    // For timestamps in game_info_

GameSession::GameSession(std::string id)
    : session_id_(std::move(id)) {
    std::lock_guard<std::mutex> lock(session_mutex_);
    game_info_ = {
        {"map_name", "default_arena"},
        {"status", "pending_players"},
        {"max_players", 8}, // Example, could be configurable
        {"creation_time", std::time(nullptr)}
    };
    std::cout << "GameSession " << session_id_ << " created. Info: " << game_info_.dump() << std::endl;
}

bool GameSession::add_player(const std::string& player_id, const std::string& player_address_info, std::shared_ptr<Tank> tank, bool is_udp) {
    std::lock_guard<std::mutex> lock(session_mutex_);
    if (players_in_session_.count(player_id)) {
        std::cerr << "GameSession " << session_id_ << ": Player " << player_id << " already in session." << std::endl;
        return false;
    }
    if (!tank) {
        std::cerr << "GameSession " << session_id_ << ": Cannot add player " << player_id << " with null tank." << std::endl;
        return false;
    }

    PlayerInSessionData data;
    data.tank = tank;
    data.address_info = player_address_info;
    data.is_udp_player = is_udp;

    players_in_session_[player_id] = data;
    std::cout << "GameSession " << session_id_ << ": Player " << player_id
              << " (Tank: " << tank->get_id()
              << ", Addr/User: " << player_address_info
              << ", UDP: " << is_udp
              << ") added. Total players: " << players_in_session_.size() << std::endl;
    return true;
}

bool GameSession::remove_player(const std::string& player_id) {
    std::lock_guard<std::mutex> lock(session_mutex_);
    auto it = players_in_session_.find(player_id);
    if (it != players_in_session_.end()) {
        std::cout << "GameSession " << session_id_ << ": Player " << player_id
                  << " (Tank: " << (it->second.tank ? it->second.tank->get_id() : "N/A") <<") removed." << std::endl;
        players_in_session_.erase(it);
        return true;
    }
    std::cerr << "GameSession " << session_id_ << ": Player " << player_id << " not found for removal." << std::endl;
    return false;
}

std::shared_ptr<Tank> GameSession::get_tank_for_player(const std::string& player_id) const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    auto it = players_in_session_.find(player_id);
    if (it != players_in_session_.end()) {
        return it->second.tank;
    }
    return nullptr;
}

PlayerInSessionData GameSession::get_player_data(const std::string& player_id) const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    auto it = players_in_session_.find(player_id);
    if (it != players_in_session_.end()) {
        return it->second;
    }
    // std::cerr << "GameSession " << session_id_ << ": Player " << player_id << " data not found (returning default)." << std::endl;
    return PlayerInSessionData{};
}

size_t GameSession::get_players_count() const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    return players_in_session_.size();
}

bool GameSession::is_empty() const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    return players_in_session_.empty();
}

nlohmann::json GameSession::get_tanks_state() const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    nlohmann::json tanks_array = nlohmann::json::array();
    for (const auto& pair : players_in_session_) {
        if (pair.second.tank) {
            tanks_array.push_back(pair.second.tank->get_state());
        }
    }
    return tanks_array;
}

std::vector<std::string> GameSession::get_all_player_udp_addresses() const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    std::vector<std::string> addresses;
    for (const auto& pair : players_in_session_) {
        if (pair.second.is_udp_player && !pair.second.address_info.empty()) {
            addresses.push_back(pair.second.address_info);
        }
    }
    return addresses;
}

bool GameSession::has_player(const std::string& player_id) const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    return players_in_session_.count(player_id);
}

const std::map<std::string, PlayerInSessionData>& GameSession::get_players() const {
    // Note: Returning a reference to the internal map.
    // If external modification is a concern, should return a copy or provide specific accessors.
    // For SessionManager iteration, this is fine if SessionManager also handles locking.
    // However, SessionManager should use GameSession's public methods primarily.
    // Let's assume for now this is for controlled access or specific internal needs.
    // A better approach might be to provide iterators or a method that takes a functor.
    // For now, keep as is per previous structure if it was there.
    // If direct map access is problematic, this should be removed or re-evaluated.
    // std::lock_guard<std::mutex> lock(session_mutex_); // Lock would be needed if map can be modified during iteration by caller
    return players_in_session_;
}

nlohmann::json GameSession::get_game_info() const {
    std::lock_guard<std::mutex> lock(session_mutex_);
    return game_info_;
}

void GameSession::set_game_info(const nlohmann::json& new_info) {
    std::lock_guard<std::mutex> lock(session_mutex_);
    game_info_ = new_info;
    std::cout << "GameSession " << session_id_ << " game_info updated: " << game_info_.dump() << std::endl;
}
