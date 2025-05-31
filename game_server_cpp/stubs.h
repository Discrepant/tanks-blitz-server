#ifndef STUBS_H
#define STUBS_H

#include <nlohmann/json.hpp>
#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <memory> // For std::shared_ptr

// Forward declaration if needed by other stubs, or include if simple
// class GameSessionStub; // Example if GameSessionStub needs TankStub

class TankStub {
public:
    TankStub(std::string id);
    std::string tank_id;
    nlohmann::json get_state();
    void shoot();
    void move(const nlohmann::json& position);
};

class TankPoolStub {
public:
    TankPoolStub();
    std::shared_ptr<TankStub> acquire_tank();
    void release_tank(const std::string& tank_id);
    std::shared_ptr<TankStub> get_tank(const std::string& tank_id);
};

class GameSessionStub {
public:
    GameSessionStub(std::string id);
    std::string session_id;
    std::map<std::string, nlohmann::json> players_data; // player_id -> {"address": addr_str, "tank_id": tank->tank_id}

    void add_player(const std::string& player_id, const std::string& addr_str, std::shared_ptr<TankStub> tank);
    void remove_player(const std::string& player_id);
    int get_players_count();
    bool has_player(const std::string& player_id);
    std::string get_tank_id_for_player(const std::string& player_id);
};

class SessionManagerStub {
public:
    SessionManagerStub();
    std::shared_ptr<GameSessionStub> create_session();
    std::shared_ptr<GameSessionStub> get_session_by_player_id(const std::string& player_id);
    void add_player_to_session(const std::string& session_id, const std::string& player_id, const std::string& addr_str, std::shared_ptr<TankStub> tank);
    void remove_player_from_session(const std::string& player_id);
    std::shared_ptr<GameSessionStub> get_session(const std::string& session_id);

private:
    std::map<std::string, std::shared_ptr<GameSessionStub>> active_sessions_;
    std::map<std::string, std::string> player_to_session_map_; // player_id -> session_id
};

#endif // STUBS_H
