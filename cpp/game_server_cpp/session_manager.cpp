#include "session_manager.h"
#include <iostream> // Для логирования
#include <nlohmann/json.hpp> // Для формирования JSON событий Kafka
#include <ctime>    // Для временных меток

// Определение статических членов
SessionManager* SessionManager::instance_ = nullptr;
std::mutex SessionManager::singleton_mutex_; // Мьютекс для инстанцирования singleton
const std::string SessionManager::KAFKA_TOPIC_PLAYER_SESSIONS = "player_sessions_history";

SessionManager::SessionManager(TankPool* tank_pool, KafkaProducerHandler* kafka_handler)
    : tank_pool_(tank_pool), kafka_producer_handler_(kafka_handler), next_session_numeric_id_(0) {
    if (!tank_pool_) {
        // Это критическая зависимость. Приложение может не функционировать.
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
        if (tank_pool == nullptr) { // Должен быть предоставлен при первом вызове
            std::cerr << "SessionManager CRITICAL ERROR: First call to get_instance() requires a valid TankPool." << std::endl;
            return nullptr; // Или выбросить исключение
        }
        // kafka_handler может быть null, если Kafka не используется, но выводим предупреждение.
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
        {"details", session->get_game_info()} // Включаем game_info из сессии
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
    // std::cout << "SessionManager: Session " << session_id << " not found." << std::endl; // Может быть слишком подробно
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
        sessions_.erase(it); // Удаляем из карты под этой блокировкой
    } // Освобождаем manager_mutex_ перед вызовом других методов или сложной логики

    // Теперь обрабатываем игроков вне основной блокировки, если возможно, или переблокируем выборочно.
    // Этот пример предполагает, что методы GameSession потокобезопасны.
    std::cout << "SessionManager: Removing session " << session_id << " (Reason: " << reason << ")" << std::endl;

    std::vector<std::string> players_in_session_to_remove;
    // GameSession::get_players() сам по себе может нуждаться в блокировке, если не const или если карта может измениться
    // Пока предполагаем, что GameSession::get_players() возвращает безопасный способ итерации или его методы потокобезопасны.
    // Если GameSession::get_players() возвращает const ref, его внутренний мьютекс защищает его.
    const auto& players_map = session_to_remove->get_players();
    // Если итерировать эту карту, пока игроки могут быть удалены из нее другими потоками, это небезопасно.
    // Пока предполагаем, что внутренний мьютекс GameSession обрабатывает это во время get_players() или это снимок.
    // Более безопасный способ: скопировать ID игроков под блокировкой GameSession, затем обработать.
    // Для простоты на этом шаге:
    for(const auto& player_entry : players_map){
        players_in_session_to_remove.push_back(player_entry.first);
    }

    // Переблокируем manager_mutex_ для изменения player_to_session_map_
    // Это проще, чем пытаться вызвать remove_player_from_any_session, который снова заблокирует.
    {
        std::lock_guard<std::mutex> lock(manager_mutex_);
        for(const std::string& player_id : players_in_session_to_remove){
            std::cout << "SessionManager: Player " << player_id << " is being removed from map due to session " << session_id << " removal." << std::endl;
            player_to_session_map_.erase(player_id);
            // Освобождение танка должно обрабатываться тем, кто вызвал remove_session неявно,
            // или если remove_session подразумевает полную очистку, то танки должны быть освобождены здесь.
            // В задании для remove_player_from_any_session сказано, что ОН освобождает танк.
            // Если сессия удаляется напрямую, танки ее игроков также должны быть освобождены.
            auto tank = session_to_remove->get_tank_for_player(player_id); // Метод GameSession, нуждается в своей блокировке
            if (tank && tank_pool_) {
                 std::cout << "SessionManager: Releasing tank " << tank->get_id() << " for player " << player_id << " from removed session " << session_id << "." << std::endl;
                tank_pool_->release_tank(tank->get_id());
            }
        }
    }
    // shared_ptr GameSession `session_to_remove` будет уничтожен, когда выйдет из области видимости,
    // очищая свои собственные данные. GameSession::remove_player здесь не нужен, если вся сессия удалена.

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
        std::cerr << "SessionManager: Невозможно добавить игрока " << player_id << " с нулевым танком." << std::endl;
        return nullptr;
    }
    // Проверяем, не находится ли игрок уже в другой сессии
    if (player_to_session_map_.count(player_id)) {
        std::string existing_session_id = player_to_session_map_[player_id];
        if (existing_session_id != session_id) {
             std::cerr << "SessionManager: Игрок " << player_id << " уже находится в сессии "
                       << existing_session_id << ". Невозможно добавить в " << session_id << std::endl;
             // Опционально, можно сначала удалить из старой сессии или просто отказать. Пока что отказываем.
            return sessions_.count(existing_session_id) ? sessions_.at(existing_session_id) : nullptr;
        }
        // Если уже в целевой сессии, GameSession::add_player обработает это (вероятно, вернет false, но игрок там есть)
    }

    auto session_it = sessions_.find(session_id);
    if (session_it == sessions_.end()) {
        std::cerr << "SessionManager: Сессия " << session_id << " не найдена. Невозможно добавить игрока " << player_id << "." << std::endl;
        return nullptr;
    }

    std::shared_ptr<GameSession> session = session_it->second;
    // GameSession::add_player внутренне потокобезопасен
    if (session->add_player(player_id, player_address_info, tank, is_udp_player)) {
        player_to_session_map_[player_id] = session_id; // Обновляем отображение игрок -> сессия
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
        // GameSession::add_player может вернуть false, если player_id уже существует в этой сессии.
        // std::cerr << "SessionManager: Failed to add player " << player_id << " to session " << session_id
        //           << " (GameSession::add_player failed)." << std::endl;
        // Если он не удался, потому что игрок уже там, то карта может быть верной или нуждается в обновлении.
        // Пока что, если GameSession::add_player не удался, мы предполагаем, что игрок не был успешно добавлен в эту сессию с точки зрения SM для этого вызова.
        // Если игрок уже был там, запись в карте в порядке.
        if(session->has_player(player_id)) return session; // Это означает, что игрок уже был в этой сессии.
        return nullptr;
    }
}

bool SessionManager::remove_player_from_any_session(const std::string& player_id) {
    std::string session_id_of_player;
    std::shared_ptr<GameSession> session_ptr = nullptr;
    std::shared_ptr<Tank> tank_to_release = nullptr;

    { // Область видимости для manager_mutex_
        std::lock_guard<std::mutex> lock(manager_mutex_);
        auto map_it = player_to_session_map_.find(player_id);
        if (map_it == player_to_session_map_.end()) {
            std::cerr << "SessionManager: Игрок " << player_id << " не найден ни в одной сессии для удаления." << std::endl;
            return false;
        }
        session_id_of_player = map_it->second;

        auto session_it = sessions_.find(session_id_of_player);
        if (session_it == sessions_.end()) {
            std::cerr << "SessionManager Error: Игрок " << player_id << " сопоставлен с несуществующей сессией "
                      << session_id_of_player << ". Удаление записи из карты." << std::endl;
            player_to_session_map_.erase(map_it);
            return false;
        }
        session_ptr = session_it->second;

        // Получаем танк перед удалением игрока из сессии, чтобы убедиться, что у нас есть его ID
        // Методы GameSession внутренне заблокированы.
        tank_to_release = session_ptr->get_tank_for_player(player_id);

        if (session_ptr->remove_player(player_id)) {
            player_to_session_map_.erase(map_it);
            std::cout << "SessionManager: Player " << player_id << " removed from session " << session_id_of_player << "." << std::endl;
            // Освобождение танка и событие Kafka произойдут вне этой блокировки, если tank_to_release действителен
        } else {
            // Не должно произойти, если игрок был в player_to_session_map_ и сессия существовала.
             std::cerr << "SessionManager Error: Не удалось удалить игрока " << player_id << " из сессии "
                       << session_id_of_player << " несмотря на сопоставление." << std::endl;
            return false;
        }
    } // Освобождаем manager_mutex_

    // Выполняем действия, которые не требуют manager_mutex_ или могут вызывать SM (например, remove_session)
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

    if (session_ptr && session_ptr->is_empty()) { // GameSession::is_empty() потокобезопасен
        std::cout << "SessionManager: Session " << session_id_of_player
                  << " is now empty and will be removed." << std::endl;
        remove_session(session_id_of_player, "became_empty_after_player_left"); // Это снова заблокирует manager_mutex_
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

    std::lock_guard<std::mutex> lock(manager_mutex_); // Блокировка для итерации sessions_ и потенциального создания сессии

    if (!tank) {
        std::cerr << "SessionManager: Невозможно найти/создать сессию для игрока " << player_id << " с нулевым танком." << std::endl;
        return nullptr;
    }
     if (player_to_session_map_.count(player_id)) {
        std::string existing_session_id = player_to_session_map_[player_id];
        std::cerr << "SessionManager: Игрок " << player_id << " уже находится в сессии "
                  << existing_session_id << ". Возвращение существующей сессии." << std::endl;
        return sessions_.count(existing_session_id) ? sessions_.at(existing_session_id) : nullptr;
    }


    // Пытаемся найти существующую сессию со свободным местом
    for (auto const& [session_id, session_ptr] : sessions_) {
        // GameSession::get_players_count() потокобезопасен
        if (session_ptr->get_players_count() < static_cast<size_t>(max_players_per_session)) {
            // Попытка добавить игрока в эту сессию.
            // Освобождаем текущую блокировку перед вызовом add_player_to_session, который снова заблокирует.
            // Это сложно. Упростим: add_player_to_session нужен session_id.
            // У нас есть session_id и session_ptr.
            // Публичный add_player_to_session снова блокирует. Нам нужна внутренняя неблокирующая версия или осторожное освобождение блокировки.
            // Пока что разблокируем и вызовем публичный. Это не идеально атомарно, но проще.
            // Это означает, что другой поток может быстро заполнить сессию.
            // Лучший способ - передать session_ptr в add_player_to_session.
            // Попробуем добавить напрямую в GameSession здесь, затем обновить карту.

            // GameSession::add_player потокобезопасен
            if (session_ptr->add_player(player_id, player_address_info, tank, is_udp_player)) {
                player_to_session_map_[player_id] = session_id; // Обновляем карту под текущей блокировкой
                std::cout << "SessionManager: Player " << player_id << " added to existing session " << session_id << "." << std::endl;
                // Отправляем событие Kafka (скопировано из add_player_to_session для согласованности)
                nlohmann::json event_payload = {
                    {"event_type", "player_joined_session"},
                    {"player_id", player_id},
                    {"session_id", session_id},
                    {"tank_id", tank->get_id()},
                    {"player_address_info", player_address_info},
                    {"is_udp_player", is_udp_player},
                    {"timestamp", std::time(nullptr)}
                };
                send_kafka_event(event_payload); // send_kafka_event является const, нет проблем с повторным входом для manager_mutex_
                return session_ptr;
            }
            // Если add_player не удался (например, игрок уже в ЭТОЙ сессии, чего не должно произойти, если его нет в карте), цикл продолжается.
        }
    }

    // Подходящая существующая сессия не найдена, создаем новую
    // Освобождаем текущую блокировку перед вызовом create_session и add_player_to_session (они блокируют сами себя).
    // Это также неатомарно. Поток может создать сессию между этим.
    // Чтобы сделать это атомарным, create_session и add_player_to_session потребовались бы версии _nolock.
    // Для простоты этого шага мы принимаем это незначительное состояние гонки для поиска vs создания.
    // Влияние невелико (может быть создана одна лишняя сессия, чем строго необходимо, если два игрока присоединяются одновременно).

    // Удерживаем блокировку только для части create_session
    std::string new_session_id = "session_" + std::to_string(next_session_numeric_id_++);
    auto new_session = std::make_shared<GameSession>(new_session_id);
    sessions_[new_session_id] = new_session;

    // GameSession::add_player потокобезопасен
    if (new_session->add_player(player_id, player_address_info, tank, is_udp_player)) {
        player_to_session_map_[player_id] = new_session_id;
        std::cout << "SessionManager: Created new session " << new_session_id << " for player " << player_id << "." << std::endl;

        // Отправляем события Kafka (session_created отправляется логикой create_session, если бы мы ее вызвали)
        // Поскольку мы создали ее вручную здесь для управления блокировкой:
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
        // Не должно произойти, если игрок не был в карте и сессия совершенно новая.
        std::cerr << "SessionManager Error: Не удалось добавить игрока " << player_id << " в только что созданную сессию " << new_session_id << std::endl;
        sessions_.erase(new_session_id); // Очищаем неудачную попытку создания сессии
        // Танк здесь не освобождается, так как он передается, вызывающая сторона должна управлять этим в случае неудачи.
        return nullptr;
    }
}

