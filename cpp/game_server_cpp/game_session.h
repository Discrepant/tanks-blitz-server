#ifndef GAME_SESSION_H
#define GAME_SESSION_H

#include <string>
#include <vector>
#include <map>
#include <memory> // Для std::shared_ptr
#include <mutex>  // Для std::mutex
#include <nlohmann/json.hpp>
#include "tank.h" // Предполагается, что класс Tank определен
#include <iostream> // Для логирования в .cpp, хорошо иметь согласованные включения

// Предварительное объявление, если Tank включает GameSession или наоборот, здесь не требуется.

struct PlayerInSessionData {
    std::shared_ptr<Tank> tank;
    std::string address_info; // Хранит UDP "ip:port" или TCP имя пользователя
    bool is_udp_player = false;
    // При необходимости добавьте другие релевантные данные игрока, например, счет
};

class GameSession {
public:
    explicit GameSession(std::string id);

    // Добавляет игрока в сессию. Возвращает true в случае успеха.
    bool add_player(const std::string& player_id, const std::string& player_address_info, std::shared_ptr<Tank> tank, bool is_udp);

    // Удаляет игрока из сессии. Возвращает true в случае успеха.
    bool remove_player(const std::string& player_id);

    std::shared_ptr<Tank> get_tank_for_player(const std::string& player_id) const;
    PlayerInSessionData get_player_data(const std::string& player_id) const;

    size_t get_players_count() const;
    bool is_empty() const;

    // Возвращает JSON-массив состояний всех танков в сессии.
    nlohmann::json get_tanks_state() const;

    // Возвращает список UDP-адресов всех UDP-игроков.
    std::vector<std::string> get_all_player_udp_addresses() const;

    const std::string& get_id() const { return session_id_; }
    bool has_player(const std::string& player_id) const;

    const std::map<std::string, PlayerInSessionData>& get_players() const; // Чтобы позволить SessionManager итерировать при необходимости

    nlohmann::json get_game_info() const;
    void set_game_info(const nlohmann::json& new_info);


private:
    mutable std::mutex session_mutex_; // Мьютекс для потокобезопасного доступа к данным сессии

    std::string session_id_;
    std::map<std::string, PlayerInSessionData> players_in_session_; // player_id -> PlayerInSessionData

    nlohmann::json game_info_; // например, {"map_name": "default_map", "start_time": ..., "status": "pending"}
};

#endif // GAME_SESSION_H
