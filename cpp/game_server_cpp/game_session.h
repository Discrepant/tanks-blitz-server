#ifndef GAME_SESSION_H
#define GAME_SESSION_H

#include <string>
#include <vector>
#include <map>
#include <memory> // For std::shared_ptr
#include <mutex>  // For std::mutex
#include <nlohmann/json.hpp>
#include "tank.h" // Assuming Tank class is defined
#include <iostream> // For logging in .cpp, good to have consistent includes

// Forward declaration if Tank includes GameSession or vice-versa, not needed here.

struct PlayerInSessionData {
    std::shared_ptr<Tank> tank;
    std::string address_info; // Stores UDP "ip:port" or TCP username
    bool is_udp_player = false;
    // Add other relevant player data if needed, e.g., score
};

class GameSession {
public:
    explicit GameSession(std::string id);

    // Adds a player to the session. Returns true if successful.
    bool add_player(const std::string& player_id, const std::string& player_address_info, std::shared_ptr<Tank> tank, bool is_udp);

    // Removes a player from the session. Returns true if successful.
    bool remove_player(const std::string& player_id);

    std::shared_ptr<Tank> get_tank_for_player(const std::string& player_id) const;
    PlayerInSessionData get_player_data(const std::string& player_id) const;

    size_t get_players_count() const;
    bool is_empty() const;

    // Returns a JSON array of all tank states in the session.
    nlohmann::json get_tanks_state() const;

    // Returns a list of UDP addresses for all UDP players.
    std::vector<std::string> get_all_player_udp_addresses() const;

    const std::string& get_id() const { return session_id_; }
    bool has_player(const std::string& player_id) const;

    const std::map<std::string, PlayerInSessionData>& get_players() const; // To allow SessionManager to iterate if needed

    nlohmann::json get_game_info() const;
    void set_game_info(const nlohmann::json& new_info);


private:
    mutable std::mutex session_mutex_; // Mutex for thread-safe access to session data

    std::string session_id_;
    std::map<std::string, PlayerInSessionData> players_in_session_; // player_id -> PlayerInSessionData

    nlohmann::json game_info_; // e.g., {"map_name": "default_map", "start_time": ..., "status": "pending"}
};

#endif // GAME_SESSION_H
