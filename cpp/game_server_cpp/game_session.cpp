#include "game_session.h"
#include <iostream> // Для логирования
#include <ctime>    // Для временных меток в game_info_

GameSession::GameSession(std::string id)
    : session_id_(std::move(id)) {
    std::lock_guard<std::mutex> lock(session_mutex_);
    game_info_ = {
        {"map_name", "default_arena"},
        {"status", "pending_players"},
        {"max_players", 8}, // Пример, может быть настраиваемым
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
    // std::cerr << "GameSession " << session_id_ << ": Данные игрока " << player_id << " не найдены (возвращается значение по умолчанию)." << std::endl; // Player ... data not found (returning default).
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
    // Примечание: Возвращается ссылка на внутреннюю карту.
    // Если есть опасения по поводу внешнего изменения, следует возвращать копию или предоставлять специальные методы доступа.
    // Для итерации SessionManager это нормально, если SessionManager также обрабатывает блокировку.
    // Однако SessionManager должен в основном использовать публичные методы GameSession.
    // Пока предположим, что это для контролируемого доступа или специфических внутренних нужд.
    // Лучшим подходом могло бы быть предоставление итераторов или метода, принимающего функтор.
    // Пока оставим как есть, согласно предыдущей структуре, если она там была.
    // Если прямой доступ к карте проблематичен, это следует удалить или пересмотреть.
    // std::lock_guard<std::mutex> lock(session_mutex_); // Блокировка потребовалась бы, если бы карта могла изменяться во время итерации вызывающей стороной
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
