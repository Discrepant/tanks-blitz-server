#include "kafka_producer_handler.h"
#include <vector> // For error messages potentially

void ExampleDeliveryReportCb::dr_cb(RdKafka::Message &message) {
    if (message.err()) {
        std::cerr << "% Kafka Message delivery failed: " << message.errstr()
                  << " to topic " << message.topic_name()
                  << " [" << message.partition() << "]" << std::endl;
    } else {
        // Optional: Log successful deliveries for debugging, can be very verbose
        // std::cout << "% Kafka Message delivered to topic " << message.topic_name()
        //           << " [" << message.partition() << "] at offset "
        //           << message.offset() << std::endl;
    }
}

KafkaProducerHandler::KafkaProducerHandler(const std::string& brokers)
 : producer_valid_(false) { // Initialize producer_valid_
    std::string errstr;
    RdKafka::Conf *conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);

    if (!conf) {
        std::cerr << "Kafka FATAL: Failed to create RdKafka Conf object" << std::endl;
        return;
    }

    // Set bootstrap servers
    if (conf->set("bootstrap.servers", brokers, errstr) != RdKafka::Conf::CONF_OK) {
        std::cerr << "Kafka FATAL: Failed to set bootstrap.servers to " << brokers << ": " << errstr << std::endl;
        delete conf;
        return;
    }

    // Set delivery report callback
    if (conf->set("dr_cb", &delivery_report_cb_, errstr) != RdKafka::Conf::CONF_OK) {
        std::cerr << "Kafka FATAL: Failed to set delivery report callback: " << errstr << std::endl;
        delete conf;
        return;
    }

    // Recommended configurations for reliability
    if (conf->set("acks", "all", errstr) != RdKafka::Conf::CONF_OK) {
        std::cerr << "Kafka Warning: Failed to set acks=all: " << errstr << std::endl;
    }
    if (conf->set("retries", "3", errstr) != RdKafka::Conf::CONF_OK) { // Number of retries
        std::cerr << "Kafka Warning: Failed to set retries=3: " << errstr << std::endl;
    }
    if (conf->set("message.send.max.retries", "3", errstr) != RdKafka::Conf::CONF_OK) { // Alias for retries
         std::cerr << "Kafka Warning: Failed to set message.send.max.retries=3: " << errstr << std::endl;
    }
    if (conf->set("retry.backoff.ms", "100", errstr) != RdKafka::Conf::CONF_OK) { // Backoff between retries
        std::cerr << "Kafka Warning: Failed to set retry.backoff.ms=100: " << errstr << std::endl;
    }
    if (conf->set("linger.ms", "10", errstr) != RdKafka::Conf::CONF_OK) { // Batching: time to wait for more messages
        std::cerr << "Kafka Warning: Failed to set linger.ms=10: " << errstr << std::endl;
    }
     // Optional: idempotence for producer to avoid duplicates on retries (requires broker >= 0.11.0.0)
    if (conf->set("enable.idempotence", "true", errstr) != RdKafka::Conf::CONF_OK) {
        std::cerr << "Kafka Warning: Failed to enable idempotence (requires broker >= 0.11 and acks=all): " << errstr << std::endl;
    }


    RdKafka::Producer *raw_producer = RdKafka::Producer::create(conf, errstr);
    delete conf; // Conf object is copied by Producer::create

    if (!raw_producer) {
        std::cerr << "Kafka FATAL: Failed to create Kafka producer: " << errstr << std::endl;
    } else {
        producer_.reset(raw_producer); // Manage with unique_ptr
        producer_valid_ = true;
        std::cout << "KafkaProducerHandler: Kafka producer created successfully for brokers: " << brokers << std::endl;
    }
}

KafkaProducerHandler::~KafkaProducerHandler() {
    std::cout << "KafkaProducerHandler: Destructor called." << std::endl;
    if (producer_ && producer_valid_) { // Check producer_valid_ as well
        std::cout << "KafkaProducerHandler: Flushing producer (" << producer_->name() << ")..." << std::endl;
        RdKafka::ErrorCode flush_err = producer_->flush(10000); // Timeout 10 seconds
        if (flush_err != RdKafka::ERR_NO_ERROR) {
            std::cerr << "KafkaProducerHandler: Failed to flush producer: " << RdKafka::err2str(flush_err) << std::endl;
        } else {
            std::cout << "KafkaProducerHandler: Producer flushed successfully." << std::endl;
        }
    }
    // producer_ unique_ptr will automatically delete the managed object.
    std::cout << "KafkaProducerHandler: Destroyed." << std::endl;
}

void KafkaProducerHandler::send_message(const std::string& topic_name, const nlohmann::json& message_json) {
    if (!is_valid()) { // is_valid() checks producer_ and producer_valid_
        std::cerr << "KafkaProducerHandler: Producer is not valid. Cannot send message to topic '" << topic_name << "'." << std::endl;
        return;
    }

    std::string message_str = message_json.dump();
    RdKafka::ErrorCode err = producer_->produce(
        topic_name,
        RdKafka::Topic::PARTITION_UA,    // Unassigned partition, librdkafka will pick one based on key or round-robin
        RdKafka::Producer::RK_MSG_COPY,  // Make a copy of the payload
        const_cast<char *>(message_str.c_str()), // Payload
        message_str.length(),            // Payload length
        nullptr,                         // No key
        0,                               // Key length (if key was provided)
        nullptr                          // Opaque value for delivery report
    );

    if (err != RdKafka::ERR_NO_ERROR) {
        std::cerr << "KafkaProducerHandler: Failed to produce message to Kafka topic '" << topic_name
                  << "': " << RdKafka::err2str(err) << std::endl;
    } else {
        // Message successfully enqueued (delivery report will confirm actual delivery)
        // std::cout << "KafkaProducerHandler: Enqueued message (" << message_str.length()
        //           << " bytes) for topic " << topic_name << std::endl;
    }

    // Poll to serve delivery callbacks. This is crucial.
    // Can be called periodically in a background thread, or after a batch of produce calls.
    // Calling it here after each produce might impact performance for high throughput,
    // but ensures quicker delivery reports for simpler applications.
    producer_->poll(0);
}
