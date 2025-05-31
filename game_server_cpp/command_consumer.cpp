#include "command_consumer.h"
#include <iostream>
#include <chrono> // For std::chrono::milliseconds
#include <vector> // For amqp_bytes_to_string helper

// Define static const members
const std::string PlayerCommandConsumer::PLAYER_COMMANDS_QUEUE_NAME = "player_commands";

// Helper function to convert amqp_bytes_t to std::string
std::string amqp_bytes_to_string(const amqp_bytes_t& bytes) {
    return std::string(static_cast<char*>(bytes.bytes), bytes.len);
}

PlayerCommandConsumer::PlayerCommandConsumer(SessionManager* sm,
                                             TankPool* tp,
                                             const std::string& host,
                                             int port,
                                             const std::string& user,
                                             const std::string& password,
                                             const std::string& vhost)
    : session_manager_(sm),
      tank_pool_(tp),
      rabbitmq_host_(host),
      rabbitmq_port_(port),
      rabbitmq_user_(user),
      rabbitmq_password_(password),
      rabbitmq_vhost_(vhost),
      conn_state_(nullptr) { // Initialize conn_state_ to nullptr
    if (!session_manager_ || !tank_pool_) {
        // This is a critical issue, should ideally throw or mark object as invalid
        std::cerr << "PlayerCommandConsumer FATAL: SessionManager or TankPool is null." << std::endl;
    }
    std::cout << "PlayerCommandConsumer created for " << rabbitmq_host_ << ":" << rabbitmq_port_ << std::endl;
}

PlayerCommandConsumer::~PlayerCommandConsumer() {
    std::cout << "PlayerCommandConsumer destructor called." << std::endl;
    stop(); // Ensure thread is stopped and joined
    // Disconnect is called within consume_loop or by stop if thread wasn't running
    if (conn_state_) { // Final check if disconnect wasn't called
        std::cerr << "PlayerCommandConsumer Warning: Connection seems to be still up in destructor, forcing disconnect." << std::endl;
        disconnect();
    }
}

void PlayerCommandConsumer::start() {
    if (running_.load()) {
        std::cout << "PlayerCommandConsumer already running." << std::endl;
        return;
    }
    if (!session_manager_ || !tank_pool_){
        std::cerr << "PlayerCommandConsumer cannot start: SessionManager or TankPool is null." << std::endl;
        return;
    }
    running_.store(true);
    consumer_thread_ = std::thread(&PlayerCommandConsumer::consume_loop, this);
    std::cout << "PlayerCommandConsumer started." << std::endl;
}

void PlayerCommandConsumer::stop() {
    std::cout << "PlayerCommandConsumer stopping..." << std::endl;
    running_.store(false);
    if (consumer_thread_.joinable()) {
        try {
            consumer_thread_.join();
            std::cout << "PlayerCommandConsumer thread joined." << std::endl;
        } catch (const std::system_error& e) {
            std::cerr << "Error joining consumer thread: " << e.what() << " (" << e.code() << ")" << std::endl;
        }
    }
    // Disconnect should be handled by the loop itself when running_ is false,
    // or by destructor as a final measure.
}

bool PlayerCommandConsumer::connect() {
    conn_state_ = amqp_new_connection();
    if (!conn_state_) {
        std::cerr << "Consumer: Failed to create new AMQP connection state." << std::endl;
        return false;
    }

    // The amqp_socket_t is managed internally by amqp_connection_state_t after amqp_socket_open
    amqp_socket_t* current_socket = amqp_tcp_socket_new(conn_state_);
    if (!current_socket) {
        std::cerr << "Consumer: Failed to create TCP socket." << std::endl;
        amqp_destroy_connection(conn_state_);
        conn_state_ = nullptr;
        return false;
    }

    int status = amqp_socket_open(current_socket, rabbitmq_host_.c_str(), rabbitmq_port_);
    if (status != AMQP_STATUS_OK) {
        std::cerr << "Consumer: Failed to open TCP socket: " << amqp_error_string2(status) << std::endl;
        amqp_destroy_connection(conn_state_); // This also frees the socket if associated
        conn_state_ = nullptr;
        return false;
    }

    amqp_rpc_reply_t login_reply = amqp_login(conn_state_, rabbitmq_vhost_.c_str(), 0, AMQP_DEFAULT_FRAME_SIZE, 0, AMQP_SASL_METHOD_PLAIN, rabbitmq_user_.c_str(), rabbitmq_password_.c_str());
    if (login_reply.reply_type != AMQP_RESPONSE_NORMAL) {
        std::cerr << "Consumer: AMQP login failed: " << amqp_error_string2(login_reply.library_error) << std::endl;
        amqp_destroy_connection(conn_state_);
        conn_state_ = nullptr;
        return false;
    }

    if (amqp_channel_open(conn_state_, 1) == nullptr) {
         amqp_rpc_reply_t rpc_reply = amqp_get_rpc_reply(conn_state_);
        std::cerr << "Consumer: Failed to open AMQP channel: " << amqp_error_string2(rpc_reply.library_error) << std::endl;
        amqp_destroy_connection(conn_state_);
        conn_state_ = nullptr;
        return false;
    }

    // Declare queue as durable, just in case. Client should also declare it.
    amqp_queue_declare_ok_t *declare_ok = amqp_queue_declare(conn_state_, 1, amqp_cstring_bytes(PLAYER_COMMANDS_QUEUE_NAME.c_str()), 0, 1, 0, 0, amqp_empty_table);
    if (!declare_ok) {
        amqp_rpc_reply_t rpc_reply = amqp_get_rpc_reply(conn_state_);
        std::cerr << "Consumer: Failed to declare queue '" << PLAYER_COMMANDS_QUEUE_NAME << "': " << amqp_error_string2(rpc_reply.library_error) << std::endl;
        // This might not be fatal if queue already exists with compatible properties.
        // For robustness, could check specific error. For now, continue.
    }

    // Set QoS: prefetch_count = 1 (process one message at a time)
    amqp_basic_qos(conn_state_, 1, 0, 1, 0);
    amqp_rpc_reply_t qos_reply = amqp_get_rpc_reply(conn_state_);
    if (qos_reply.reply_type != AMQP_RESPONSE_NORMAL) {
         std::cerr << "Consumer: Failed to set QoS: "  << amqp_error_string2(qos_reply.library_error) << std::endl;
        // Non-fatal, but good to know.
    }


    if (amqp_basic_consume(conn_state_, 1, amqp_cstring_bytes(PLAYER_COMMANDS_QUEUE_NAME.c_str()), amqp_empty_bytes, 0, 0, 0, amqp_empty_table) == nullptr) {
        amqp_rpc_reply_t rpc_reply = amqp_get_rpc_reply(conn_state_);
        std::cerr << "Consumer: Failed to start consuming from queue '" << PLAYER_COMMANDS_QUEUE_NAME << "': " << amqp_error_string2(rpc_reply.library_error) << std::endl;
        amqp_destroy_connection(conn_state_);
        conn_state_ = nullptr;
        return false;
    }

    std::cout << "Consumer: Successfully connected to RabbitMQ and started consuming from " << PLAYER_COMMANDS_QUEUE_NAME << std::endl;
    return true;
}

void PlayerCommandConsumer::disconnect() {
    if (conn_state_) {
        std::cout << "Consumer: Disconnecting from RabbitMQ..." << std::endl;
        // Closing channel
        amqp_rpc_reply_t channel_close_reply = amqp_channel_close(conn_state_, 1, AMQP_REPLY_SUCCESS);
        if (channel_close_reply.reply_type != AMQP_RESPONSE_NORMAL) {
            // std::cerr << "Consumer: Error closing channel: " << amqp_error_string2(channel_close_reply.library_error) << std::endl;
        }
        // Closing connection
        amqp_rpc_reply_t conn_close_reply = amqp_connection_close(conn_state_, AMQP_REPLY_SUCCESS);
         if (conn_close_reply.reply_type != AMQP_RESPONSE_NORMAL) {
            // std::cerr << "Consumer: Error closing connection: " << amqp_error_string2(conn_close_reply.library_error) << std::endl;
        }
        // Destroying connection state
        int status = amqp_destroy_connection(conn_state_);
        if (status < 0) {
            // std::cerr << "Consumer: Error destroying connection state: " << amqp_error_string2(status) << std::endl;
        }
        conn_state_ = nullptr;
        std::cout << "Consumer: Disconnected." << std::endl;
    }
}

void PlayerCommandConsumer::consume_loop() {
    std::cout << "Consumer: Consume loop started." << std::endl;
    while (running_.load()) {
        if (!conn_state_ && !connect()) { // Attempt to connect if not connected
            std::cerr << "Consumer: Failed to connect. Retrying in 5 seconds..." << std::endl;
            std::this_thread::sleep_for(std::chrono::seconds(5));
            continue;
        }

        bool connection_ok = true;
        while (running_.load() && connection_ok) {
            amqp_envelope_t envelope;
            amqp_maybe_release_buffers(conn_state_); // Release buffers from previous message processing

            // Poll for a message with a timeout (e.g., 1 second) to allow checking running_ flag
            struct timeval timeout;
            timeout.tv_sec = 1;
            timeout.tv_usec = 0;

            amqp_rpc_reply_t res = amqp_consume_message(conn_state_, &envelope, &timeout, 0);

            if (res.reply_type == AMQP_RESPONSE_NORMAL) {
                // std::cout << "Consumer: Received message, delivery tag " << envelope.delivery_tag << std::endl;
                process_message_body(envelope.message.body);

                // Acknowledge the message
                int ack_status = amqp_basic_ack(conn_state_, 1, envelope.delivery_tag, 0);
                if (ack_status != AMQP_STATUS_OK) {
                     std::cerr << "Consumer: Failed to ACK message, delivery tag " << envelope.delivery_tag << ". Error: " << amqp_error_string2(ack_status) << std::endl;
                     // This could lead to message re-delivery.
                }
                amqp_destroy_envelope(&envelope);
            } else if (res.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
                if (res.library_error == AMQP_STATUS_TIMEOUT) {
                    // Timeout is normal, just continue polling if running
                    continue;
                } else if (res.library_error == AMQP_STATUS_UNEXPECTED_STATE ||
                           res.library_error == AMQP_STATUS_CONNECTION_CLOSED ||
                           res.library_error == AMQP_STATUS_SOCKET_ERROR) {
                    std::cerr << "Consumer: Connection lost or error: " << amqp_error_string2(res.library_error) << ". Attempting to reconnect." << std::endl;
                    connection_ok = false; // Break inner loop to reconnect
                } else {
                    std::cerr << "Consumer: Library exception during consume: " << amqp_error_string2(res.library_error) << std::endl;
                    // Decide if this is fatal or if we should try to reconnect
                    connection_ok = false;
                }
            } else if (res.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
                 std::cerr << "Consumer: Server exception during consume. Class: " << res.reply.id // AMQP_BASIC_ACK_METHOD for example
                          << " Method: " << res.reply.decoded // Decoded reply
                          << std::endl;
                 // Potentially fatal, or specific handling based on class/method ID.
                 // For now, treat as connection issue.
                 connection_ok = false;
            }
        } // end inner while(connection_ok)

        disconnect(); // Disconnect before trying to reconnect in the outer loop
        if (running_.load() && !connection_ok) { // If we broke due to error and still running
             std::cout << "Consumer: Will attempt to reconnect in 5 seconds..." << std::endl;
             std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }
    // Ensure disconnected if loop exits because running_ is false
    disconnect();
    std::cout << "Consumer: Consume loop finished." << std::endl;
}

void PlayerCommandConsumer::process_message_body(const amqp_bytes_t& body) {
    std::string message_str = amqp_bytes_to_string(body);
    // std::cout << "Consumer processing message: " << message_str << std::endl;

    if (!session_manager_ || !tank_pool_) {
        std::cerr << "Consumer: SessionManager or TankPool is null. Cannot process message." << std::endl;
        return;
    }

    try {
        nlohmann::json msg_json = nlohmann::json::parse(message_str);

        if (!msg_json.contains("player_id") || !msg_json.contains("command") || !msg_json.contains("details")) {
            std::cerr << "Consumer: Message missing required fields (player_id, command, details). Body: " << message_str << std::endl;
            return;
        }

        std::string player_id = msg_json["player_id"].get<std::string>();
        std::string command = msg_json["command"].get<std::string>();
        nlohmann::json details = msg_json["details"];

        // std::cout << "Consumer: Parsed command '" << command << "' for player '" << player_id << "'" << std::endl;

        auto session = session_manager_->get_session_by_player_id(player_id);
        if (!session) {
            // std::cerr << "Consumer: No active session found for player_id: " << player_id << ". Command '" << command << "' dropped." << std::endl;
            return;
        }

        // PlayerInSessionData player_data = session->get_player_data(player_id); // This might return a copy with null tank if player not found
        // A more direct way:
        auto tank = session->get_tank_for_player(player_id);

        if (!tank) {
            // std::cerr << "Consumer: No tank found for player_id: " << player_id << " in session " << session->get_id() << ". Command '" << command << "' dropped." << std::endl;
            return;
        }

        // Ensure tank is active before processing commands that imply activity
        if (!tank->is_active() && (command == "move" || command == "shoot")) {
            // std::cout << "Consumer: Tank " << tank->get_id() << " for player " << player_id << " is inactive. Command '" << command << "' ignored." << std::endl;
            return;
        }


        if (command == "move") {
            if (details.contains("new_position")) {
                tank->move(details["new_position"]);
                // std::cout << "Consumer: Processed 'move' for tank " << tank->get_id() << std::endl;
            } else {
                std::cerr << "Consumer: 'move' command for player " << player_id << " missing 'new_position' in details." << std::endl;
            }
        } else if (command == "shoot") {
            tank->shoot();
            // std::cout << "Consumer: Processed 'shoot' for tank " << tank->get_id() << std::endl;
        }
        // Add other command processing here, e.g., "take_damage" if it were to come from RabbitMQ
        // else if (command == "say_broadcast") { ... } // Example for chat messages if they pass through here
        else {
            std::cerr << "Consumer: Unknown command '" << command << "' for player " << player_id << "." << std::endl;
        }

    } catch (const nlohmann::json::parse_error& e) {
        std::cerr << "Consumer: JSON parsing error: " << e.what() << ". Message body: " << message_str << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Consumer: Error processing message: " << e.what() << ". Message body: " << message_str << std::endl;
    }
}
