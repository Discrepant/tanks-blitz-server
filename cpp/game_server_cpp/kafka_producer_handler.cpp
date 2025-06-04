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

#include <thread> // For std::this_thread::sleep_for
#include <chrono> // For std::chrono::seconds

KafkaProducerHandler::KafkaProducerHandler(const std::string& brokers)
 : producer_valid_(false) { // Initialize producer_valid_
    std::string errstr; // General error string

    const int MAX_KAFKA_RETRIES = 5;
    const std::chrono::seconds KAFKA_RETRY_DELAY = std::chrono::seconds(3);

    for (int attempt = 1; attempt <= MAX_KAFKA_RETRIES; ++attempt) {
        std::cout << "KafkaProducerHandler: Attempt " << attempt << "/" << MAX_KAFKA_RETRIES
                  << " to connect to Kafka brokers: " << brokers << std::endl;

        RdKafka::Conf *conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);
        if (!conf) {
            std::cerr << "Kafka FATAL: Failed to create RdKafka Conf object on attempt " << attempt << std::endl;
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
                continue;
            } else {
                std::cerr << "KafkaProducerHandler: All " << MAX_KAFKA_RETRIES << " attempts to create RdKafka Conf failed." << std::endl;
                producer_valid_ = false; // Ensure it's false
                break; // Exit loop
            }
        }

        // Set bootstrap servers (critical)
        if (conf->set("bootstrap.servers", brokers, errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka FATAL: Failed to set bootstrap.servers to " << brokers << ": " << errstr << " on attempt " << attempt << std::endl;
            delete conf;
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
                continue;
            } else {
                producer_valid_ = false;
                break;
            }
        }

        // Set delivery report callback (critical)
        if (conf->set("dr_cb", &delivery_report_cb_, errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka FATAL: Failed to set delivery report callback: " << errstr << " on attempt " << attempt << std::endl;
            delete conf;
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
                continue;
            } else {
                producer_valid_ = false;
                break;
            }
        }

        // Recommended configurations for reliability (non-critical for loop continuation, warnings are fine)
        if (conf->set("acks", "all", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Failed to set acks=all: " << errstr << " on attempt " << attempt << std::endl;
        }
        // librdkafka has internal retries; these are producer-level config for those.
        // The loop here is for initial connection/producer creation.
        if (conf->set("message.send.max.retries", "3", errstr) != RdKafka::Conf::CONF_OK) {
             std::cerr << "Kafka Warning: Failed to set message.send.max.retries=3: " << errstr << " on attempt " << attempt << std::endl;
        }
        if (conf->set("retry.backoff.ms", "100", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Failed to set retry.backoff.ms=100: " << errstr << " on attempt " << attempt << std::endl;
        }
        if (conf->set("linger.ms", "10", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Failed to set linger.ms=10: " << errstr << " on attempt " << attempt << std::endl;
        }
        if (conf->set("enable.idempotence", "true", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Failed to enable idempotence (requires broker >= 0.11 and acks=all): " << errstr << " on attempt " << attempt << std::endl;
        }

        RdKafka::Producer *raw_producer = RdKafka::Producer::create(conf, errstr);

        if (!raw_producer) {
            std::cerr << "Kafka FATAL: Failed to create Kafka producer on attempt " << attempt << ": " << errstr << std::endl;
            delete conf; // Producer::create did not take ownership of conf on failure
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
            } else {
                producer_valid_ = false; // All attempts failed
            }
        } else {
            producer_.reset(raw_producer); // Manage with unique_ptr, Producer took ownership of conf
            producer_valid_ = true;
            std::cout << "KafkaProducerHandler: Kafka producer created successfully on attempt " << attempt << " for brokers: " << brokers << std::endl;
            break; // Success, exit loop
        }
    } // End of retry loop

    if (!producer_valid_) {
        std::cerr << "KafkaProducerHandler: All " << MAX_KAFKA_RETRIES << " attempts to create Kafka producer failed for brokers: " << brokers << "." << std::endl;
    }
    // Constructor finishes, producer_valid_ reflects the outcome.
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
        0ll,                             // Timestamp (0 for current time or let broker decide)
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
