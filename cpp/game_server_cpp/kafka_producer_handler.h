#ifndef KAFKA_PRODUCER_HANDLER_H
#define KAFKA_PRODUCER_HANDLER_H

#include <librdkafka/rdkafkacpp.h>
#include <string>
#include <nlohmann/json.hpp>
#include <iostream>
#include <memory> // Для std::unique_ptr
#include <vector> // Напрямую не используется в этом заголовке, но может быть полезно для .cpp файла

// Класс обратного вызова для отчета о доставке
class ExampleDeliveryReportCb : public RdKafka::DeliveryReportCb {
public:
    void dr_cb(RdKafka::Message &message) override;
};

class KafkaProducerHandler {
public:
    KafkaProducerHandler(const std::string& brokers);
    ~KafkaProducerHandler();

    // Удаленные конструктор копирования и оператор присваивания
    KafkaProducerHandler(const KafkaProducerHandler&) = delete;
    KafkaProducerHandler& operator=(const KafkaProducerHandler&) = delete;

    bool is_valid() const { return producer_ != nullptr && producer_valid_; } // Добавлена проверка producer_valid_
    void send_message(const std::string& topic_name, const nlohmann::json& message_json);
    RdKafka::Producer* get_raw_producer() { return producer_.get(); }

private:
    std::unique_ptr<RdKafka::Producer> producer_;
    ExampleDeliveryReportCb delivery_report_cb_; // Экземпляр обратного вызова
    bool producer_valid_ = false; // Для отслеживания успешности создания продюсера
};

#endif // KAFKA_PRODUCER_HANDLER_H
