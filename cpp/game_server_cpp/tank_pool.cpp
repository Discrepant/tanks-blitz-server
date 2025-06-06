#include "tank_pool.h"
#include <iostream>  // Для std::cout, std::cerr для логирования
#include <algorithm> // Для std::find (используется в release_tank для проверки дубликатов, опционально)

// Определение статических членов
TankPool* TankPool::instance_ = nullptr;
std::mutex TankPool::mutex_; // Убедимся, что это определено

TankPool::TankPool(size_t pool_size, KafkaProducerHandler* kafka_handler)
    : kafka_producer_handler_(kafka_handler), initial_pool_size_(pool_size) {

    if (pool_size > 0 && (!kafka_handler || !kafka_handler->is_valid())) {
        // Эта проверка критична, если танки требуют действительный kafka_handler для корректной работы.
        std::cerr << "TankPool Warning: KafkaProducerHandler is null or invalid during construction, "
                  << "but pool_size is " << pool_size << ". Tanks may not function as expected." << std::endl;
        // В зависимости от строгости, можно выбросить исключение или пометить TankPool как недействительный.
    }

    std::cout << "TankPool: Initializing with pool size: " << pool_size << std::endl;
    for (size_t i = 0; i < pool_size; ++i) {
        std::string tank_id = "tank_" + std::to_string(i);
        // Создаем танк с позицией и здоровьем по умолчанию, передаем kafka_handler
        auto tank = std::make_shared<Tank>(tank_id, kafka_producer_handler_);
        all_tanks_[tank_id] = tank;
        available_tank_ids_.push_back(tank_id);
        // Танки изначально неактивны (конструктор Tank устанавливает is_active_ = false).
    }
    std::cout << "TankPool: " << all_tanks_.size() << " tanks initialized and added to the available pool." << std::endl;
}

TankPool* TankPool::get_instance(size_t pool_size, KafkaProducerHandler* kafka_handler) {
    std::lock_guard<std::mutex> lock(mutex_); // Потокобезопасная инициализация для singleton
    if (instance_ == nullptr) {
        if (pool_size > 0 && kafka_handler == nullptr) { // Kafka handler важен, если создаются танки
            std::cerr << "TankPool Critical Error: First call to get_instance() with pool_size > 0 "
                      << "requires a valid KafkaProducerHandler." << std::endl;
            return nullptr;
        }
        if (pool_size > 0 && kafka_handler != nullptr && !kafka_handler->is_valid()) {
             std::cerr << "TankPool Critical Error: Provided KafkaProducerHandler is not valid for first init with pool_size > 0." << std::endl;
            return nullptr;
        }
        instance_ = new TankPool(pool_size, kafka_handler);
    }
    // Примечание: Последующие вызовы get_instance в настоящее время игнорируют pool_size и kafka_handler.
    // Если требуется реконфигурация, паттерн singleton может потребовать корректировки или отдельного метода reinit.
    return instance_;
}

std::shared_ptr<Tank> TankPool::acquire_tank() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (available_tank_ids_.empty()) {
        std::cerr << "TankPool Warning: No tanks available for acquisition." << std::endl;
        return nullptr;
    }

    std::string tank_id = available_tank_ids_.back(); // Поведение LIFO (последним пришел - первым вышел)
    available_tank_ids_.pop_back();

    auto tank_it = all_tanks_.find(tank_id);
    if (tank_it == all_tanks_.end()) {
        // Это указывает на несоответствие, в идеале такого происходить не должно.
        std::cerr << "TankPool Error: Tank ID " << tank_id
                  << " from available list not found in all_tanks_ map. Re-adding ID to available." << std::endl;
        available_tank_ids_.push_back(tank_id); // Возвращаем обратно, чтобы попытаться предотвратить бесконечный цикл при ошибке логики
        return nullptr;
    }

    std::shared_ptr<Tank> tank = tank_it->second;

    tank->reset();          // Убедимся, что танк в состоянии по умолчанию (также вызывает set_active(false))
    tank->set_active(true); // Теперь активируем его для использования (это отправит событие "tank_activated")

    in_use_tanks_[tank_id] = tank;

    std::cout << "TankPool: Tank " << tank_id << " acquired. Available: " << available_tank_ids_.size()
              << ", In Use: " << in_use_tanks_.size() << std::endl;
    return tank;
}

void TankPool::release_tank(const std::string& tank_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = in_use_tanks_.find(tank_id);
    if (it == in_use_tanks_.end()) {
        std::cerr << "TankPool Warning: Attempted to release tank '" << tank_id
                  << "' which is not currently in use or does not exist." << std::endl;
        return;
    }

    std::shared_ptr<Tank> tank = it->second;
    tank->reset(); // Это вызывает set_active(false) и отправляет события Kafka "tank_reset" и "tank_deactivated".

    in_use_tanks_.erase(it);

    // Добавляем ID обратно в available_tank_ids_ только если его там еще нет (проверка безопасности)
    if (std::find(available_tank_ids_.begin(), available_tank_ids_.end(), tank_id) == available_tank_ids_.end()) {
        available_tank_ids_.push_back(tank_id);
    } else {
        // Этот случай в идеале не должен достигаться, если логика acquire/release надежна.
        std::cerr << "TankPool Warning: Tank ID " << tank_id
                  << " already in available_tank_ids_ during release. Possible logic issue." << std::endl;
    }

    std::cout << "TankPool: Tank " << tank_id << " released. Available: " << available_tank_ids_.size()
              << ", In Use: " << in_use_tanks_.size() << std::endl;
}

std::shared_ptr<Tank> TankPool::get_tank(const std::string& tank_id) {
    std::lock_guard<std::mutex> lock(mutex_); // Защищает доступ к in_use_tanks_
    auto it = in_use_tanks_.find(tank_id);
    if (it != in_use_tanks_.end()) {
        return it->second; // Возвращаем shared_ptr на танк
    }
    // std::cout << "TankPool: Tank " << tank_id << " not found in in_use_tanks_." << std::endl; // Может быть слишком подробно
    return nullptr; // Танк не используется или не существует с таким ID в карте "in_use"
}

size_t TankPool::get_available_tanks_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return available_tank_ids_.size();
}

size_t TankPool::get_in_use_tanks_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return in_use_tanks_.size();
}

size_t TankPool::get_total_tanks_count() const {
     std::lock_guard<std::mutex> lock(mutex_);
    return all_tanks_.size();
}
