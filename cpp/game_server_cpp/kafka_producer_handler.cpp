#include "kafka_producer_handler.h"
#include <vector> // Для потенциальных сообщений об ошибках

void ExampleDeliveryReportCb::dr_cb(RdKafka::Message &message) {
    if (message.err()) {
        std::cerr << "% Kafka Message delivery failed: " << message.errstr() // % Ошибка доставки сообщения Kafka
                  << " to topic " << message.topic_name()
                  << " [" << message.partition() << "]" << std::endl;
    } else {
        // Опционально: Логирование успешных доставок для отладки, может быть очень подробным
        // std::cout << "% Kafka Message delivered to topic " << message.topic_name() // % Сообщение Kafka доставлено в топик
        //           << " [" << message.partition() << "] at offset "
        //           << message.offset() << std::endl;
    }
}

#include <thread> // Для std::this_thread::sleep_for
#include <chrono> // Для std::chrono::seconds

KafkaProducerHandler::KafkaProducerHandler(const std::string& brokers)
 : producer_valid_(false) { // Инициализируем producer_valid_
    std::string errstr; // Общая строка для ошибок

    const int MAX_KAFKA_RETRIES = 5;
    const std::chrono::seconds KAFKA_RETRY_DELAY = std::chrono::seconds(3);

    for (int attempt = 1; attempt <= MAX_KAFKA_RETRIES; ++attempt) {
        std::cout << "KafkaProducerHandler: Попытка " << attempt << "/" << MAX_KAFKA_RETRIES
                  << " подключения к брокерам Kafka: " << brokers << std::endl;

        RdKafka::Conf *conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);
        if (!conf) {
            std::cerr << "Kafka FATAL: Не удалось создать объект RdKafka Conf при попытке " << attempt << std::endl;
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
                continue;
            } else {
                std::cerr << "KafkaProducerHandler: Все " << MAX_KAFKA_RETRIES << " попыток создать RdKafka Conf провалились." << std::endl;
                producer_valid_ = false; // Убедимся, что false
                break; // Выход из цикла
            }
        }

        // Установка bootstrap servers (критично)
        if (conf->set("bootstrap.servers", brokers, errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka FATAL: Не удалось установить bootstrap.servers на " << brokers << ": " << errstr << " при попытке " << attempt << std::endl;
            delete conf;
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
                continue;
            } else {
                producer_valid_ = false;
                break;
            }
        }

        // Установка обратного вызова для отчета о доставке (критично)
        if (conf->set("dr_cb", &delivery_report_cb_, errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka FATAL: Не удалось установить обратный вызов для отчета о доставке: " << errstr << " при попытке " << attempt << std::endl;
            delete conf;
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
                continue;
            } else {
                producer_valid_ = false;
                break;
            }
        }

        // Рекомендуемые конфигурации для надежности (не критично для продолжения цикла, предупреждения допустимы)
        if (conf->set("acks", "all", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Не удалось установить acks=all: " << errstr << " при попытке " << attempt << std::endl;
        }
        // librdkafka имеет внутренние повторные попытки; это конфигурации на уровне продюсера для них.
        // Цикл здесь предназначен для начального подключения/создания продюсера.
        if (conf->set("message.send.max.retries", "3", errstr) != RdKafka::Conf::CONF_OK) {
             std::cerr << "Kafka Warning: Не удалось установить message.send.max.retries=3: " << errstr << " при попытке " << attempt << std::endl;
        }
        if (conf->set("retry.backoff.ms", "100", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Не удалось установить retry.backoff.ms=100: " << errstr << " при попытке " << attempt << std::endl;
        }
        if (conf->set("linger.ms", "10", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Не удалось установить linger.ms=10: " << errstr << " при попытке " << attempt << std::endl;
        }
        if (conf->set("enable.idempotence", "true", errstr) != RdKafka::Conf::CONF_OK) {
            std::cerr << "Kafka Warning: Не удалось включить идемпотентность (требуется брокер >= 0.11 и acks=all): " << errstr << " при попытке " << attempt << std::endl;
        }

        RdKafka::Producer *raw_producer = RdKafka::Producer::create(conf, errstr);

        if (!raw_producer) {
            std::cerr << "Kafka FATAL: Не удалось создать продюсер Kafka при попытке " << attempt << ": " << errstr << std::endl;
            delete conf; // Producer::create не получил владение conf при ошибке
            if (attempt < MAX_KAFKA_RETRIES) {
                std::this_thread::sleep_for(KAFKA_RETRY_DELAY);
            } else {
                producer_valid_ = false; // Все попытки не удались
            }
        } else {
            producer_.reset(raw_producer); // Управляем с помощью unique_ptr, Producer получил владение conf
            producer_valid_ = true;
            std::cout << "KafkaProducerHandler: Продюсер Kafka успешно создан при попытке " << attempt << " для брокеров: " << brokers << std::endl;
            break; // Успех, выход из цикла
        }
    } // Конец цикла повторных попыток

    if (!producer_valid_) {
        std::cerr << "KafkaProducerHandler: Все " << MAX_KAFKA_RETRIES << " попыток создать продюсер Kafka для брокеров: " << brokers << " провалились." << std::endl;
    }
    // Конструктор завершается, producer_valid_ отражает результат.
}

KafkaProducerHandler::~KafkaProducerHandler() {
    std::cout << "KafkaProducerHandler: Destructor called." << std::endl;
    if (producer_ && producer_valid_) { // Также проверяем producer_valid_
        std::cout << "KafkaProducerHandler: Flushing producer (" << producer_->name() << ")..." << std::endl;
        RdKafka::ErrorCode flush_err = producer_->flush(10000); // Таймаут 10 секунд
        if (flush_err != RdKafka::ERR_NO_ERROR) {
            std::cerr << "KafkaProducerHandler: Не удалось очистить буфер продюсера: " << RdKafka::err2str(flush_err) << std::endl;
        } else {
            std::cout << "KafkaProducerHandler: Буфер продюсера успешно очищен." << std::endl;
        }
    }
    // unique_ptr producer_ автоматически удалит управляемый объект.
    std::cout << "KafkaProducerHandler: Destroyed." << std::endl;
}

void KafkaProducerHandler::send_message(const std::string& topic_name, const nlohmann::json& message_json) {
    if (!is_valid()) { // is_valid() проверяет producer_ и producer_valid_
        std::cerr << "KafkaProducerHandler: Продюсер недействителен. Невозможно отправить сообщение в топик '" << topic_name << "'." << std::endl;
        return;
    }

    std::string message_str = message_json.dump();
    RdKafka::ErrorCode err = producer_->produce(
        topic_name,
        RdKafka::Topic::PARTITION_UA,    // Неназначенный раздел, librdkafka выберет один на основе ключа или round-robin
        RdKafka::Producer::RK_MSG_COPY,  // Создать копию полезной нагрузки
        const_cast<char *>(message_str.c_str()), // Полезная нагрузка
        message_str.length(),            // Длина полезной нагрузки
        nullptr,                         // Без ключа
        0,                               // Длина ключа (если ключ предоставлен)
        0ll,                             // Временная метка (0 для текущего времени или пусть брокер решает)
        nullptr                          // Непрозрачное значение для отчета о доставке
    );

    if (err != RdKafka::ERR_NO_ERROR) {
        std::cerr << "KafkaProducerHandler: Не удалось отправить сообщение в топик Kafka '" << topic_name
                  << "': " << RdKafka::err2str(err) << std::endl;
    } else {
        // Сообщение успешно поставлено в очередь (отчет о доставке подтвердит фактическую доставку)
        // std::cout << "KafkaProducerHandler: Enqueued message (" << message_str.length()
        //           << " bytes) for topic " << topic_name << std::endl;
    }

    // Опрос для обслуживания обратных вызовов доставки. Это крайне важно.
    // Может вызываться периодически в фоновом потоке или после пачки вызовов produce.
    // Вызов здесь после каждого produce может повлиять на производительность при высокой пропускной способности,
    // но обеспечивает более быстрые отчеты о доставке для более простых приложений.
    producer_->poll(0);
}
