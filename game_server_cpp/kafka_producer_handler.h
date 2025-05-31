#ifndef KAFKA_PRODUCER_HANDLER_H
#define KAFKA_PRODUCER_HANDLER_H

#include <librdkafka/rdkafkacpp.h>
#include <string>
#include <nlohmann/json.hpp>
#include <iostream>
#include <memory> // For std::unique_ptr

class ExampleDeliveryReportCb : public RdKafka::DeliveryReportCb {
public:
    void dr_cb(RdKafka::Message &message) override;
};

class KafkaProducerHandler {
public:
    KafkaProducerHandler(const std::string& brokers);
    ~KafkaProducerHandler();

    bool is_valid() const { return producer_ != nullptr && producer_valid_; }
    void send_message(const std::string& topic_name, const nlohmann::json& message_json);
    // RdKafka::Producer* get_producer() { return producer_.get(); } // Might not be needed if this class handles all sends

private:
    std::unique_ptr<RdKafka::Producer> producer_;
    std::unique_ptr<ExampleDeliveryReportCb> dr_cb_;
    bool producer_valid_ = false; // To track if producer creation was successful
};

#endif // KAFKA_PRODUCER_HANDLER_H
