#include "kafka_producer_handler.h"

void ExampleDeliveryReportCb::dr_cb(RdKafka::Message &message) {
    if (message.err()) {
        std::cerr << "% Message delivery failed: " << message.errstr() << std::endl;
    } else {
        // std::cout << "% Message delivered to topic " << message.topic_name()
        //           << " [" << message.partition() << "] at offset "
        //           << message.offset() << std::endl;
    }
}

KafkaProducerHandler::KafkaProducerHandler(const std::string& brokers) {
    std::string errstr;
    dr_cb_ = std::make_unique<ExampleDeliveryReportCb>();

    RdKafka::Conf *conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);
    if (!conf) {
        std::cerr << "Failed to create RdKafka Conf object" << std::endl;
        return;
    }

    // Set bootstrap servers
    if (conf->set("bootstrap.servers", brokers, errstr) != RdKafka::Conf::CONF_OK) {
        std::cerr << "Failed to set bootstrap.servers: " << errstr << std::endl;
        delete conf;
        return;
    }

    // Set delivery report callback
    if (conf->set("dr_cb", dr_cb_.get(), errstr) != RdKafka::Conf::CONF_OK) {
        std::cerr << "Failed to set delivery report callback: " << errstr << std::endl;
        delete conf;
        return;
    }

    // Optional: Increase queue buffering max messages if high throughput is expected.
    // conf->set("queue.buffering.max.messages", "1000000", errstr);
    // Optional: Set linger.ms to allow messages to batch.
    // conf->set("linger.ms", "5", errstr);


    producer_.reset(RdKafka::Producer::create(conf, errstr));
    delete conf; // Configuration object is copied by Producer::create, so we can delete it.

    if (!producer_) {
        std::cerr << "Failed to create Kafka producer: " << errstr << std::endl;
    } else {
        std::cout << "Kafka producer created successfully for brokers: " << brokers << std::endl;
        producer_valid_ = true;
    }
}

KafkaProducerHandler::~KafkaProducerHandler() {
    if (producer_) {
        std::cout << "Flushing Kafka producer..." << std::endl;
        // producer_->flush(10 * 1000 /* wait for max 10 seconds */); // Disabled due to potential long block
        // RdKafka::Topic *topic = nullptr; // Not needed for producer flush
        int flush_timeout_ms = 5000; // 5 seconds
        RdKafka::ErrorCode err = producer_->flush(flush_timeout_ms);
        if (err != RdKafka::ERR_NO_ERROR) {
            std::cerr << "Failed to flush Kafka producer: " << RdKafka::err2str(err) << std::endl;
        } else {
            std::cout << "Kafka producer flushed." << std::endl;
        }
        // The producer_ unique_ptr will handle deletion.
        // dr_cb_ unique_ptr will handle deletion.
    }
    std::cout << "KafkaProducerHandler destroyed." << std::endl;
}

void KafkaProducerHandler::send_message(const std::string& topic_name, const nlohmann::json& message_json) {
    if (!is_valid()) {
        std::cerr << "Kafka producer is not valid. Cannot send message." << std::endl;
        return;
    }

    std::string message_str = message_json.dump();
    RdKafka::ErrorCode err = producer_->produce(
        topic_name,
        RdKafka::Topic::PARTITION_UA, // Unassigned partition
        RdKafka::Producer::RK_MSG_COPY, // Make a copy of the payload
        const_cast<char *>(message_str.c_str()), message_str.length(),
        nullptr, // No key
        0,       // Timestamp (0 = current time)
        nullptr, // No msg_opaque
        nullptr  // No per-message delivery report callback (using global one)
    );

    if (err != RdKafka::ERR_NO_ERROR) {
        std::cerr << "Failed to produce message to Kafka topic " << topic_name << ": " << RdKafka::err2str(err) << std::endl;
    } else {
        // std::cout << "Enqueued message (" << message_str.length() << " bytes) for topic " << topic_name << std::endl;
    }

    // Poll for delivery reports (and other events)
    // This is important to trigger the delivery report callback.
    // Can be called periodically elsewhere or after a batch of produce calls.
    producer_->poll(0);
}
