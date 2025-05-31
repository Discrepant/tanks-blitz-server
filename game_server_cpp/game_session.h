#ifndef GAME_SESSION_H
#define GAME_SESSION_H

#include <string>
#include <vector>
#include <map>
#include <memory> // For std::shared_ptr
#include <nlohmann/json.hpp>
#include "tank.h" // Assuming Tank class is defined

// Forward declaration if Tank includes GameSession or vice-versa, not needed here.

struct PlayerInSessionData {
    std::shared_ptr<Tank> tank;
    std::string udp_address;    // For UDP clients, format "ip:port"
    std::string tcp_username;   // For TCP clients, their authenticated username
    // Add other relevant player data if needed, e.g., score, connection type
};

class GameSession {
public:
    explicit GameSession(std::string id);

    // Adds a player to the session. Returns true if successful, false if player already exists or tank is null.
    bool add_player(const std::string& player_id, const std::string& player_address_info, std::shared_ptr<Tank> tank, bool is_udp_player = true);

    // Removes a player from the session. Returns true if successful.
    bool remove_player(const std::string& player_id);

    std::shared_ptr<Tank> get_tank_for_player(const std::string& player_id) const;
    PlayerInSessionData get_player_data(const std::string& player_id) const; // Consider returning const ref or optional

    size_t get_players_count() const;
    bool is_empty() const;

    // Returns a JSON array of all tank states in the session.
    nlohmann::json get_tanks_state() const;

    // Returns a list of UDP addresses for all players (primarily for UDP game state broadcast).
    std::vector<std::string> get_all_player_udp_addresses() const;

    const std::string& get_id() const { return session_id_; }
    bool has_player(const std::string& player_id) const;

    const std::map<std::string, PlayerInSessionData>& get_players() const { return players_in_session_; }

    // Game state related (example)
    nlohmann::json get_game_state_info() const { return game_state_info_; }
    void set_game_state_info(const nlohmann::json& new_state) { game_state_info_ = new_state; }


private:
    std::string session_id_;
    std::map<std::string, PlayerInSessionData> players_in_session_; // player_id -> PlayerInSessionData

    // Example game state specific to this session
    nlohmann::json game_state_info_; // e.g., {"map_name": "default_map", "status": "waiting_for_players"}
};

#endif // GAME_SESSION_H
