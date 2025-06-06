#ifndef SESSION_MANAGER_H
#define SESSION_MANAGER_H

#include <string>
#include <map>
#include <memory>   // Для std::shared_ptr
#include <mutex>    // Для std::mutex и std::lock_guard
#include <vector>

#include "game_session.h"           // Определение GameSession
#include "tank_pool.h"              // Определение TankPool
#include "kafka_producer_handler.h" // Для отправки событий Kafka (опционально здесь, может быть только в .cpp)
#include <nlohmann/json_fwd.hpp>    // Предварительное объявление для nlohmann::json, если используется только в .cpp для Kafka

class SessionManager {
public:
    // Метод доступа к Singleton
    // При первом вызове tank_pool и kafka_handler не должны быть null.
    static SessionManager* get_instance(TankPool* tank_pool = nullptr, KafkaProducerHandler* kafka_handler = nullptr);

    // Удаленные конструктор копирования и оператор присваивания для паттерна Singleton
    SessionManager(const SessionManager&) = delete;
    SessionManager& operator=(const SessionManager&) = delete;

    // Управление сессиями
    std::shared_ptr<GameSession> create_session();
    std::shared_ptr<GameSession> get_session(const std::string& session_id);
    bool remove_session(const std::string& session_id, const std::string& reason = "explicitly_removed");

    // Управление игроками в сессиях
    std::shared_ptr<GameSession> add_player_to_session(
        const std::string& session_id,
        const std::string& player_id,
        const std::string& player_address_info, // Может быть UDP "ip:port" или TCP имя пользователя
        std::shared_ptr<Tank> tank,
        bool is_udp_player);

    bool remove_player_from_any_session(const std::string& player_id);

    std::shared_ptr<GameSession> get_session_by_player_id(const std::string& player_id);

    // Новый вспомогательный метод для поиска сессии со свободным местом или создания новой.
    std::shared_ptr<GameSession> find_or_create_session_for_player(
        const std::string& player_id,
        const std::string& player_address_info,
        std::shared_ptr<Tank> tank,
        bool is_udp_player,
        int max_players_per_session = 2); // Пример максимального количества игроков по умолчанию

    // Утилиты
    size_t get_active_sessions_count() const;
    std::vector<std::shared_ptr<GameSession>> get_all_sessions() const; // Для административных целей или широковещательной рассылки

    static const std::string KAFKA_TOPIC_PLAYER_SESSIONS;

private:
    // Приватный конструктор для Singleton
    SessionManager(TankPool* tank_pool, KafkaProducerHandler* kafka_handler);
    ~SessionManager() = default; // Деструктор по умолчанию подходит

    void send_kafka_event(const nlohmann::json& event_payload) const;

    static SessionManager* instance_;
    static std::mutex singleton_mutex_; // Мьютекс для потокобезопасного создания Singleton

    mutable std::mutex manager_mutex_; // Мьютекс для потокобезопасного доступа к картам SessionManager

    std::map<std::string, std::shared_ptr<GameSession>> sessions_; // session_id -> объект GameSession
    std::map<std::string, std::string> player_to_session_map_; // player_id -> session_id

    TankPool* tank_pool_; // Сырой указатель, время жизни управляется извне (например, main)
    KafkaProducerHandler* kafka_producer_handler_; // Сырой указатель, время жизни управляется извне

    long long next_session_numeric_id_ = 0; // Для генерации простых уникальных ID сессий
};

#endif // SESSION_MANAGER_H
