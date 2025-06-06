#ifndef TANK_POOL_H
#define TANK_POOL_H

#include <vector>
#include <string>
#include <memory> // Для std::shared_ptr
#include <map>
#include <mutex>    // Для std::mutex и std::lock_guard
#include <stdexcept> // Для std::runtime_error (опционально, для ошибок при необходимости)

#include "tank.h"                   // Определение класса Tank
#include "kafka_producer_handler.h" // Для указателя KafkaProducerHandler

class TankPool {
public:
    // Метод доступа к Singleton
    // При первом вызове kafka_handler не должен быть null, если pool_size > 0.
    static TankPool* get_instance(size_t pool_size = 10, KafkaProducerHandler* kafka_handler = nullptr);

    // Удаленные конструктор копирования и оператор присваивания для паттерна Singleton
    TankPool(const TankPool&) = delete;
    TankPool& operator=(const TankPool&) = delete;

    std::shared_ptr<Tank> acquire_tank();
    void release_tank(const std::string& tank_id);
    std::shared_ptr<Tank> get_tank(const std::string& tank_id); // Получить танк, используемый в данный момент

    // Опционально: Метод для получения текущего статуса пула (например, для мониторинга или тестирования)
    size_t get_available_tanks_count() const;
    size_t get_in_use_tanks_count() const;
    size_t get_total_tanks_count() const;


private:
    // Приватный конструктор для Singleton
    TankPool(size_t pool_size, KafkaProducerHandler* kafka_handler);
    // Приватный деструктор для предотвращения случайного удаления через указатель базового класса, если TankPool наследовался бы,
    // и для обеспечения того, что он удаляется только потенциальным destroy_instance() или при выходе из программы, если это необходимо.
    // Для простого singleton, который живет в течение всего времени работы приложения, деструктор по умолчанию часто подходит.
    ~TankPool() = default;

    static TankPool* instance_;
    static std::mutex mutex_; // Мьютекс для потокобезопасного создания singleton и операций с пулом

    // Хранит все когда-либо созданные объекты танков. Ключ - ID танка.
    std::map<std::string, std::shared_ptr<Tank>> all_tanks_;

    // ID танков, которые в данный момент доступны для получения.
    std::vector<std::string> available_tank_ids_;

    // Танки, которые в данный момент получены и используются. Ключ - ID танка.
    // Хранение shared_ptr здесь для поддержания их жизни во время использования и обеспечения общего доступа.
    std::map<std::string, std::shared_ptr<Tank>> in_use_tanks_;

    KafkaProducerHandler* kafka_producer_handler_; // Сырой указатель, время жизни управляется извне (например, main)
    size_t initial_pool_size_;
};

#endif // TANK_POOL_H
