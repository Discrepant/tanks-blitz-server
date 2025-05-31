#include "game_session.h"
#include <iostream> // For logging

GameSession::GameSession(std::string id) : session_id_(std::move(id)) {
    game_state_info_ = {
        {"map_name", "default_arena"},
        {"status", "pending"},
        {"max_players", 8} // Example
    };
    std::cout << "GameSession " << session_id_ << " created." << std::endl;
}

bool GameSession::add_player(const std::string& player_id, const std::string& player_address_info, std::shared_ptr<Tank> tank, bool is_udp_player) {
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
    if (is_udp_player) {
        data.udp_address = player_address_info;
    } else {
        data.tcp_username = player_address_info; // Store username as address_info for TCP
    }

    players_in_session_[player_id] = data;
    std::cout << "GameSession " << session_id_ << ": Player " << player_id
              << " (Tank: " << tank->get_id()
              << ", Addr/User: " << player_address_info
              << ") added. Total players: " << players_in_session_.size() << std::endl;
    return true;
}

bool GameSession::remove_player(const std::string& player_id) {
    auto it = players_in_session_.find(player_id);
    if (it != players_in_session_.end()) {
        // The actual tank object's lifetime is managed by shared_ptr.
        // TankPool will handle its reset/release.
        std::cout << "GameSession " << session_id_ << ": Player " << player_id << " (Tank: " << it->second.tank->get_id() <<") removed." << std::endl;
        players_in_session_.erase(it);
        return true;
    }
    std::cerr << "GameSession " << session_id_ << ": Player " << player_id << " not found for removal." << std::endl;
    return false;
}

std::shared_ptr<Tank> GameSession::get_tank_for_player(const std::string& player_id) const {
    auto it = players_in_session_.find(player_id);
    if (it != players_in_session_.end()) {
        return it->second.tank;
    }
    return nullptr;
}

PlayerInSessionData GameSession::get_player_data(const std::string& player_id) const {
    auto it = players_in_session_.find(player_id);
    if (it != players_in_session_.end()) {
        return it->second;
    }
    // Return an empty/default PlayerInSessionData or throw an exception
    // For now, returning a default-constructed one (tank will be null)
    std::cerr << "GameSession " << session_id_ << ": Player " << player_id << " data not found." << std::endl;
    return PlayerInSessionData{};
}

size_t GameSession::get_players_count() const {
    return players_in_session_.size();
}

bool GameSession::is_empty() const {
    return players_in_session_.empty();
}

nlohmann::json GameSession::get_tanks_state() const {
    nlohmann::json tanks_array = nlohmann::json::array();
    for (const auto& pair : players_in_session_) {
        if (pair.second.tank) {
            tanks_array.push_back(pair.second.tank->get_state());
        }
    }
    return tanks_array;
}

std::vector<std::string> GameSession::get_all_player_udp_addresses() const {
    std::vector<std::string> addresses;
    for (const auto& pair : players_in_session_) {
        if (!pair.second.udp_address.empty()) {
            addresses.push_back(pair.second.udp_address);
        }
    }
    return addresses;
}

bool GameSession::has_player(const std::string& player_id) const {
    return players_in_session_.count(player_id);
}
