#ifndef KAFKA_PRODUCER_HANDLER_H
#define KAFKA_PRODUCER_HANDLER_H

#include <librdkafka/rdkafkacpp.h>
#include <string>
#include <nlohmann/json.hpp>
#include <iostream>
#include <memory> // For std::unique_ptr
#include <vector> // Not directly used in this header but good for cpp file if needed

// Delivery report callback class
class ExampleDeliveryReportCb : public RdKafka::DeliveryReportCb {
public:
    void dr_cb(RdKafka::Message &message) override;
};

class KafkaProducerHandler {
public:
    KafkaProducerHandler(const std::string& brokers);
    ~KafkaProducerHandler();

    // Deleted copy constructor and assignment operator
    KafkaProducerHandler(const KafkaProducerHandler&) = delete;
    KafkaProducerHandler& operator=(const KafkaProducerHandler&) = delete;

    bool is_valid() const { return producer_ != nullptr && producer_valid_; } // Added producer_valid_ check
    void send_message(const std::string& topic_name, const nlohmann::json& message_json);
    RdKafka::Producer* get_raw_producer() { return producer_.get(); }

private:
    std::unique_ptr<RdKafka::Producer> producer_;
    ExampleDeliveryReportCb delivery_report_cb_; // Instance of the callback
    bool producer_valid_ = false; // To track if producer creation was successful
};

#endif // KAFKA_PRODUCER_HANDLER_H
