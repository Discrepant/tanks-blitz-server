#include "stubs.h"

// --- TankStub Implementation ---
TankStub::TankStub(std::string id) : tank_id(id) {
    std::cout << "TankStub created with ID: " << tank_id << std::endl;
}

nlohmann::json TankStub::get_state() {
    nlohmann::json state = {
        {"id", tank_id},
        {"position", {0, 0}}, // Default position
        {"health", 100}       // Default health
    };
    std::cout << "TankStub " << tank_id << " get_state called. Returning: " << state.dump() << std::endl;
    return state;
}

void TankStub::shoot() {
    std::cout << "TankStub " << tank_id << " shoot called." << std::endl;
}

void TankStub::move(const nlohmann::json& position) {
    std::cout << "TankStub " << tank_id << " move called with position: " << position.dump() << std::endl;
}

// --- TankPoolStub Implementation ---
TankPoolStub::TankPoolStub() {
    std::cout << "TankPoolStub created." << std::endl;
}

std::shared_ptr<TankStub> TankPoolStub::acquire_tank() {
    std::string new_tank_id = "stub_tank_" + std::to_string(rand() % 1000); // Simple unique ID
    std::cout << "TankPoolStub acquire_tank called. Acquired tank ID: " << new_tank_id << std::endl;
    return std::make_shared<TankStub>(new_tank_id);
}

void TankPoolStub::release_tank(const std::string& tank_id) {
    std::cout << "TankPoolStub release_tank called for tank ID: " << tank_id << std::endl;
}

std::shared_ptr<TankStub> TankPoolStub::get_tank(const std::string& tank_id) {
    std::cout << "TankPoolStub get_tank called for tank ID: " << tank_id << std::endl;
    return std::make_shared<TankStub>(tank_id); // Always returns a new stub for simplicity
}

// --- GameSessionStub Implementation ---
GameSessionStub::GameSessionStub(std::string id) : session_id(id) {
    std::cout << "GameSessionStub created with ID: " << session_id << std::endl;
}

void GameSessionStub::add_player(const std::string& player_id, const std::string& addr_str, std::shared_ptr<TankStub> tank) {
    players_data[player_id] = {
        {"address", addr_str},
        {"tank_id", tank ? tank->tank_id : "null"}
    };
    std::cout << "GameSessionStub " << session_id << ": player " << player_id << " (tank: " << (tank ? tank->tank_id : "null") << ", addr: " << addr_str << ") added." << std::endl;
}

void GameSessionStub::remove_player(const std::string& player_id) {
    if (players_data.erase(player_id)) {
        std::cout << "GameSessionStub " << session_id << ": player " << player_id << " removed." << std::endl;
    } else {
        std::cout << "GameSessionStub " << session_id << ": player " << player_id << " not found for removal." << std::endl;
    }
}

int GameSessionStub::get_players_count() {
    int count = players_data.size();
    std::cout << "GameSessionStub " << session_id << " get_players_count called. Count: " << count << std::endl;
    return count > 0 ? count : 1; // Stub behavior, ensure at least 1 if not empty for some logic
}

bool GameSessionStub::has_player(const std::string& player_id) {
    return players_data.count(player_id);
}

std::string GameSessionStub::get_tank_id_for_player(const std::string& player_id) {
    if (has_player(player_id) && players_data[player_id].contains("tank_id")) {
        return players_data[player_id]["tank_id"].get<std::string>();
    }
    return "";
}


// --- SessionManagerStub Implementation ---
SessionManagerStub::SessionManagerStub() {
    std::cout << "SessionManagerStub created." << std::endl;
}

std::shared_ptr<GameSessionStub> SessionManagerStub::create_session() {
    std::string new_session_id = "stub_session_" + std::to_string(rand() % 100); // Simple unique ID
    auto session = std::make_shared<GameSessionStub>(new_session_id);
    active_sessions_[new_session_id] = session;
    std::cout << "SessionManagerStub create_session called. Created session ID: " << new_session_id << std::endl;
    return session;
}

std::shared_ptr<GameSessionStub> SessionManagerStub::get_session_by_player_id(const std::string& player_id) {
    std::cout << "SessionManagerStub get_session_by_player_id called for player ID: " << player_id << std::endl;
    if (player_to_session_map_.count(player_id)) {
        std::string session_id = player_to_session_map_[player_id];
        if (active_sessions_.count(session_id)) {
            std::cout << "Player " << player_id << " found in session " << session_id << std::endl;
            return active_sessions_[session_id];
        }
    }
    std::cout << "Player " << player_id << " not found in any active session." << std::endl;
    return nullptr;
}

void SessionManagerStub::add_player_to_session(const std::string& session_id, const std::string& player_id, const std::string& addr_str, std::shared_ptr<TankStub> tank) {
    if (active_sessions_.count(session_id)) {
        active_sessions_[session_id]->add_player(player_id, addr_str, tank);
        player_to_session_map_[player_id] = session_id;
        std::cout << "SessionManagerStub added player " << player_id << " to session " << session_id << std::endl;
    } else {
        std::cout << "SessionManagerStub add_player_to_session: Session " << session_id << " not found." << std::endl;
    }
}

void SessionManagerStub::remove_player_from_session(const std::string& player_id) {
    std::cout << "SessionManagerStub remove_player_from_session called for player ID: " << player_id << std::endl;
    if (player_to_session_map_.count(player_id)) {
        std::string session_id = player_to_session_map_[player_id];
        if (active_sessions_.count(session_id)) {
            active_sessions_[session_id]->remove_player(player_id);
            // Optional: remove session if empty
            // if (active_sessions_[session_id]->get_players_count() == 0) {
            //     active_sessions_.erase(session_id);
            //     std::cout << "Session " << session_id << " is empty and removed." << std::endl;
            // }
        }
        player_to_session_map_.erase(player_id);
        std::cout << "Player " << player_id << " removed from session management." << std::endl;
    } else {
         std::cout << "Player " << player_id << " not mapped to any session." << std::endl;
    }
}

std::shared_ptr<GameSessionStub> SessionManagerStub::get_session(const std::string& session_id) {
    std::cout << "SessionManagerStub get_session called for session ID: " << session_id << std::endl;
    if (active_sessions_.count(session_id)) {
        return active_sessions_[session_id];
    }
    std::cout << "Session " << session_id << " not found. Returning a new default one for stub behavior." << std::endl;
    // Stub behavior: return a new one if not found, or could return nullptr
    return std::make_shared<GameSessionStub>(session_id);
}
