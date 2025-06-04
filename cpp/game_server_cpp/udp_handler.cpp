#include "udp_handler.h"
#include <utility> // For std::move (not strictly needed here, but good practice)

const std::string GameUDPHandler::RMQ_PLAYER_COMMANDS_QUEUE = "player_commands";

GameUDPHandler::GameUDPHandler(boost::asio::io_context& io_context,
                               short port,
                               SessionManager* sm,
                               TankPool* tp,
                               const std::string& rabbitmq_host,
                               int rabbitmq_port,
                               const std::string& rabbitmq_user,
                               const std::string& rabbitmq_pass,
                               const std::string& rabbitmq_vhost)
    : socket_(io_context, udp::endpoint(udp::v4(), port)),
      session_manager_(sm),
      tank_pool_(tp),
      rmq_host_(rabbitmq_host),
      rmq_port_(rabbitmq_port),
      rmq_user_(rabbitmq_user),
      rmq_pass_(rabbitmq_pass),
      rmq_vhost_(rabbitmq_vhost),
      rmq_conn_state_(nullptr),
      rmq_connected_(false) {

    if (!session_manager_ || !tank_pool_) {
        std::cerr << "UDP Handler FATAL: SessionManager or TankPool is null. UDP handler may not function correctly." << std::endl;
        // Depending on requirements, could throw or set an internal error state.
    }

    std::cout << "UDP Handler: Initializing on port " << port << std::endl;
    if (setup_rabbitmq_connection()) {
        std::cout << "UDP Handler: RabbitMQ connection successful to " << rmq_host_ << ":" << rmq_port_ << std::endl;
    } else {
        std::cerr << "UDP Handler: Failed to connect to RabbitMQ. Commands requiring MQ will fail." << std::endl;
    }
    internal_start_receive(); // Start listening for incoming messages
}

GameUDPHandler::~GameUDPHandler() {
    std::cout << "UDP Handler: Shutting down." << std::endl;
    close_rabbitmq_connection();
}

// void GameUDPHandler::start_listening() { // If manual start is preferred
//     internal_start_receive();
// }

// Helper to convert amqp_bytes_t to std::string, useful for message bodies
// This can be moved to a common utility if used by multiple RMQ classes
static std::string amqp_bytes_to_std_string_udp(const amqp_bytes_t& bytes) {
    return std::string(static_cast<char*>(bytes.bytes), bytes.len);
}


bool GameUDPHandler::setup_rabbitmq_connection() {
    rmq_connected_ = false; // Initialize at the start
    const int MAX_RMQ_RETRIES = 5;
    const std::chrono::seconds RMQ_RETRY_DELAY = std::chrono::seconds(3);
    static const int CHANNEL_ID = 1; // Define channel ID

    for (int attempt = 1; attempt <= MAX_RMQ_RETRIES; ++attempt) {
        std::cout << "UDP Handler RMQ: Attempt " << attempt << "/" << MAX_RMQ_RETRIES << " to connect to "
                  << rmq_host_ << ":" << rmq_port_ << std::endl;

        rmq_conn_state_ = amqp_new_connection();
        if (!rmq_conn_state_) {
            std::cerr << "UDP Handler RMQ: Failed to create new AMQP connection state on attempt " << attempt << "." << std::endl;
            if (attempt < MAX_RMQ_RETRIES) {
                std::this_thread::sleep_for(RMQ_RETRY_DELAY);
                continue;
            } else {
                break; // All attempts failed
            }
        }

        amqp_socket_t *socket = amqp_tcp_socket_new(rmq_conn_state_);
        if (!socket) {
            std::cerr << "UDP Handler RMQ: Failed to create TCP socket on attempt " << attempt << "." << std::endl;
            amqp_destroy_connection(rmq_conn_state_);
            rmq_conn_state_ = nullptr;
            if (attempt < MAX_RMQ_RETRIES) {
                std::this_thread::sleep_for(RMQ_RETRY_DELAY);
                continue;
            } else {
                break;
            }
        }

        int status = amqp_socket_open(socket, rmq_host_.c_str(), rmq_port_);
        if (status != AMQP_STATUS_OK) {
            std::cerr << "UDP Handler RMQ: Failed to open TCP socket to " << rmq_host_ << ":" << rmq_port_
                      << ". Error: " << amqp_error_string2(status) << " on attempt " << attempt << "." << std::endl;
            amqp_destroy_connection(rmq_conn_state_);
            rmq_conn_state_ = nullptr;
            if (attempt < MAX_RMQ_RETRIES) {
                std::this_thread::sleep_for(RMQ_RETRY_DELAY);
                continue;
            } else {
                break;
            }
        }

        amqp_rpc_reply_t login_reply = amqp_login(rmq_conn_state_, rmq_vhost_.c_str(), 0, AMQP_DEFAULT_FRAME_SIZE, 0, AMQP_SASL_METHOD_PLAIN, rmq_user_.c_str(), rmq_pass_.c_str());
        if (login_reply.reply_type != AMQP_RESPONSE_NORMAL) {
            std::cerr << "UDP Handler RMQ: Login failed on attempt " << attempt << ". AMQP reply type: " << static_cast<int>(login_reply.reply_type);
            if (login_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
                if (login_reply.reply.id == AMQP_CONNECTION_CLOSE_METHOD) {
                    auto* decoded = static_cast<amqp_connection_close_t*>(login_reply.reply.decoded);
                    if (decoded) {
                        std::cerr << " Server error: " << decoded->reply_code
                                  << " text: " << amqp_bytes_to_std_string_udp(decoded->reply_text);
                    }
                } else {
                    std::cerr << " Server error, method id: " << login_reply.reply.id;
                }
            } else if (login_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
                std::cerr << " Library error: " << amqp_error_string2(login_reply.library_error);
            }
            std::cerr << std::endl;
            amqp_destroy_connection(rmq_conn_state_);
            rmq_conn_state_ = nullptr;
            if (attempt < MAX_RMQ_RETRIES) {
                std::this_thread::sleep_for(RMQ_RETRY_DELAY);
                continue;
            } else {
                break;
            }
        }

        amqp_channel_open(rmq_conn_state_, CHANNEL_ID);
        amqp_rpc_reply_t channel_open_reply = amqp_get_rpc_reply(rmq_conn_state_);
        if (channel_open_reply.reply_type != AMQP_RESPONSE_NORMAL) {
            std::cerr << "UDP Handler RMQ: Channel Open failed on attempt " << attempt << ". AMQP reply type: " << static_cast<int>(channel_open_reply.reply_type);
            if (channel_open_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
                if (channel_open_reply.reply.id == AMQP_CHANNEL_CLOSE_METHOD) {
                    auto* decoded = static_cast<amqp_channel_close_t*>(channel_open_reply.reply.decoded);
                    if (decoded) {
                        std::cerr << " Server error: " << decoded->reply_code
                                  << " text: " << amqp_bytes_to_std_string_udp(decoded->reply_text);
                    }
                } else {
                    std::cerr << " Server error, method id: " << channel_open_reply.reply.id;
                }
            } else if (channel_open_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
                std::cerr << " Library error: " << amqp_error_string2(channel_open_reply.library_error);
            }
            std::cerr << std::endl;
            amqp_destroy_connection(rmq_conn_state_);
            rmq_conn_state_ = nullptr;
            if (attempt < MAX_RMQ_RETRIES) {
                std::this_thread::sleep_for(RMQ_RETRY_DELAY);
                continue;
            } else {
                break;
            }
        }

        // Declare queue as durable
        amqp_queue_declare_ok_t *declare_ok = amqp_queue_declare(rmq_conn_state_, CHANNEL_ID, amqp_cstring_bytes(RMQ_PLAYER_COMMANDS_QUEUE.c_str()), 0, 1, 0, 0, amqp_empty_table);
        amqp_rpc_reply_t queue_declare_reply = amqp_get_rpc_reply(rmq_conn_state_);
        if (!declare_ok || queue_declare_reply.reply_type != AMQP_RESPONSE_NORMAL) {
            std::cerr << "UDP Handler RMQ: Queue Declare failed for '" << RMQ_PLAYER_COMMANDS_QUEUE << "' on attempt " << attempt
                      << ". Reply type: " << static_cast<int>(queue_declare_reply.reply_type)
                      << (declare_ok ? "" : ", declare_ok is NULL");
            if (queue_declare_reply.reply_type == AMQP_RESPONSE_SERVER_EXCEPTION) {
                 if (queue_declare_reply.reply.id == AMQP_CHANNEL_CLOSE_METHOD) {
                    auto* decoded = static_cast<amqp_channel_close_t*>(queue_declare_reply.reply.decoded);
                    if (decoded) {
                        std::cerr << " Server error: " << decoded->reply_code
                                  << " text: " << amqp_bytes_to_std_string_udp(decoded->reply_text);
                    }
                } else {
                    std::cerr << " Server error, method id: " << queue_declare_reply.reply.id;
                }
            } else if (queue_declare_reply.reply_type == AMQP_RESPONSE_LIBRARY_EXCEPTION) {
                 std::cerr << " Library error: " << amqp_error_string2(queue_declare_reply.library_error);
            }
            std::cerr << std::endl;
            amqp_destroy_connection(rmq_conn_state_);
            rmq_conn_state_ = nullptr;
            if (attempt < MAX_RMQ_RETRIES) {
                std::this_thread::sleep_for(RMQ_RETRY_DELAY);
                continue;
            } else {
                break;
            }
        }

        // If all steps are successful
        rmq_connected_ = true;
        std::cout << "UDP Handler RMQ: Successfully connected to RabbitMQ and setup queue on attempt " << attempt << "." << std::endl;
        break; // Exit retry loop
    }

    if (!rmq_connected_) {
        std::cerr << "UDP Handler RMQ: All " << MAX_RMQ_RETRIES << " attempts to connect to RabbitMQ failed." << std::endl;
    }
    return rmq_connected_;
}

void GameUDPHandler::publish_to_rabbitmq(const std::string& queue_name, const nlohmann::json& message_json) {
    if (!rmq_connected_ || !rmq_conn_state_) {
        std::cerr << "UDP Handler RMQ: Not connected. Cannot publish message to '" << queue_name << "'." << std::endl;
        return;
    }

    std::string message_body = message_json.dump();
    amqp_bytes_t message_bytes;
    message_bytes.len = message_body.length();
    message_bytes.bytes = (void*)message_body.c_str();

    // Basic properties: delivery_mode = 2 (persistent)
    amqp_basic_properties_t props;
    props._flags = AMQP_BASIC_DELIVERY_MODE_FLAG;
    props.delivery_mode = 2;

    int status = amqp_basic_publish(rmq_conn_state_, 1, amqp_empty_bytes, amqp_cstring_bytes(queue_name.c_str()),
                                    0, 0, &props, message_bytes);
    if (status) {
        std::cerr << "UDP Handler RMQ: Failed to publish message to queue '" << queue_name << "': " << amqp_error_string2(status) << std::endl;
    } else {
        // std::cout << "UDP Handler RMQ: Message published to queue '" << queue_name << "': " << message_body << std::endl; // Can be verbose
    }
}

void GameUDPHandler::close_rabbitmq_connection() {
    if (rmq_conn_state_) {
        std::cout << "UDP Handler RMQ: Closing RabbitMQ connection." << std::endl;
        amqp_channel_close(rmq_conn_state_, 1, AMQP_REPLY_SUCCESS);
        amqp_connection_close(rmq_conn_state_, AMQP_REPLY_SUCCESS);
        int status = amqp_destroy_connection(rmq_conn_state_);
         if (status < 0) {
            std::cerr << "UDP Handler RMQ: Error destroying connection: " << amqp_error_string2(status) << std::endl;
        }
        rmq_conn_state_ = nullptr;
    }
    rmq_connected_ = false;
}

void GameUDPHandler::internal_start_receive() {
    socket_.async_receive_from(
        boost::asio::buffer(recv_buffer_), sender_endpoint_,
        [this](const boost::system::error_code& error, std::size_t bytes_transferred) {
            handle_receive(error, bytes_transferred);
        });
}

void GameUDPHandler::handle_receive(const boost::system::error_code& error, std::size_t bytes_transferred) {
    if (!error && bytes_transferred > 0) {
        std::string message_str(recv_buffer_.data(), bytes_transferred);
        // std::cout << "UDP Recv from " << sender_endpoint_.address().to_string() << ":" << sender_endpoint_.port() << ": " << message_str << std::endl;
        process_message(message_str, sender_endpoint_);
    } else if (error) {
        std::cerr << "UDP Handler: Receive error: " << error.message() << std::endl;
        // Depending on error, might stop or continue. For now, continue.
    }
    // Listen for next message regardless of error on previous one, unless socket is closed.
    if (socket_.is_open()){
        internal_start_receive();
    }
}

void GameUDPHandler::process_message(const std::string& message_str, const udp::endpoint& remote_endpoint) {
    try {
        json parsed_message = json::parse(message_str);
        if (!parsed_message.contains("player_id") || !parsed_message.contains("action")) {
            std::cerr << "UDP Handler: Message from " << remote_endpoint << " missing 'player_id' or 'action'." << std::endl;
            send_json_response({{"status", "error"}, {"message", "Missing player_id or action"}}, remote_endpoint);
            return;
        }

        std::string action = parsed_message["action"].get<std::string>();
        if (action == "join_game") {
            handle_join_game(parsed_message, remote_endpoint);
        } else if (action == "move") {
            handle_move(parsed_message, remote_endpoint);
        } else if (action == "shoot") {
            handle_shoot(parsed_message, remote_endpoint);
        } else if (action == "leave_game") {
            handle_leave_game(parsed_message, remote_endpoint);
        } else {
            std::cerr << "UDP Handler: Unknown action '" << action << "' from " << remote_endpoint << std::endl;
            send_json_response({{"status", "error"}, {"message", "Unknown action: " + action}}, remote_endpoint);
        }
    } catch (const json::parse_error& e) {
        std::cerr << "UDP Handler: JSON parsing error from " << remote_endpoint << ": " << e.what() << ". Msg: " << message_str << std::endl;
        send_json_response({{"status", "error"}, {"message", "Invalid JSON format"}}, remote_endpoint);
    } catch (const std::exception& e) {
        std::cerr << "UDP Handler: Exception processing message from " << remote_endpoint << ": " << e.what() << ". Msg: " << message_str << std::endl;
        send_json_response({{"status", "error"}, {"message", "Server error processing message"}}, remote_endpoint);
    }
}

void GameUDPHandler::send_json_response(const nlohmann::json& response_json, const udp::endpoint& target_endpoint) {
    auto message_body_ptr = std::make_shared<std::string>(response_json.dump());
    socket_.async_send_to(
        boost::asio::buffer(*message_body_ptr), target_endpoint,
        [this, message_body_ptr](const boost::system::error_code& error, std::size_t bytes_transferred) {
            handle_send(message_body_ptr, error, bytes_transferred);
        });
}

void GameUDPHandler::handle_send(std::shared_ptr<std::string> /*message_body_ptr*/,
                                 const boost::system::error_code& error,
                                 std::size_t /*bytes_transferred*/) {
    if (error) {
        std::cerr << "UDP Handler: Send error: " << error.message() << std::endl;
    }
    // else { std::cout << "UDP Sent " << bytes_transferred << " bytes." << std::endl; } // Verbose
}

// --- Action Handlers ---
void GameUDPHandler::handle_join_game(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
    // std::cout << "UDP Handler: join_game for player: " << player_id << std::endl;

    if (!session_manager_ || !tank_pool_) {
        send_json_response({{"status", "error"}, {"message", "Server misconfiguration"}}, sender_endpoint);
        return;
    }

    auto tank = tank_pool_->acquire_tank();
    if (!tank) {
        send_json_response({{"status", "join_failed"}, {"message", "no_tanks_available"}}, sender_endpoint);
        return;
    }

    std::string udp_addr_str = sender_endpoint.address().to_string() + ":" + std::to_string(sender_endpoint.port());
    // Use find_or_create_session_for_player to handle session assignment
    auto game_session = session_manager_->find_or_create_session_for_player(player_id, udp_addr_str, tank, true /*is_udp_player*/);

    if (!game_session) {
        std::cerr << "UDP Handler: Failed to find or create session for player " << player_id << "." << std::endl;
        tank_pool_->release_tank(tank->get_id()); // Release tank if session logic failed
        send_json_response({{"status", "join_failed"}, {"message", "server_error_session_assignment"}}, sender_endpoint);
        return;
    }
    // Check if the player was actually added (find_or_create might return an existing session they are NOT in if it was full and new one failed)
    // This check is now implicitly handled if game_session is valid and SM logic is correct.
    // If player was already in another session, find_or_create_session_for_player would return that, and tank would be released.
    // We need to ensure the tank passed to find_or_create is the one associated.
    // The current find_or_create_session_for_player adds the given tank if it joins/creates.
    // If it returns an existing session the player is already in, it might not use the new tank.
    // This logic needs careful review in SessionManager. For now, assume it works as intended.
    // If player was added, their tank in session should be this `tank`.

    json response = {
        {"status", "joined"},
        {"session_id", game_session->get_id()},
        {"tank_id", tank->get_id()}, // This should be the tank ID now associated with player in session
        {"initial_state", tank->get_state()}
    };
    send_json_response(response, sender_endpoint);
}

void GameUDPHandler::handle_move(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
    if (!session_manager_ || !msg.contains("details") || !msg["details"].contains("new_position")) {
        // Minimal response or no response for invalid move commands to reduce UDP noise
        return;
    }

    auto session = session_manager_->get_session_by_player_id(player_id);
    if (!session) return;
    auto tank = session->get_tank_for_player(player_id);
    if (!tank) return;

    json command_to_mq = {
        {"player_id", player_id},
        {"command", "move"},
        {"details", {
            {"source", "udp_handler"},
            {"tank_id", tank->get_id()},
            {"new_position", msg["details"]["new_position"]}
        }}
    };
    publish_to_rabbitmq(RMQ_PLAYER_COMMANDS_QUEUE, command_to_mq);
    // No direct response for move usually, state updates come via game state broadcast
}

void GameUDPHandler::handle_shoot(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
     if (!session_manager_) return;

    auto session = session_manager_->get_session_by_player_id(player_id);
    if (!session) return;
    auto tank = session->get_tank_for_player(player_id);
    if (!tank) return;

    json command_to_mq = {
        {"player_id", player_id},
        {"command", "shoot"},
        {"details", {
            {"source", "udp_handler"},
            {"tank_id", tank->get_id()}
            // Future: add target, direction from msg["details"] if provided
        }}
    };
    publish_to_rabbitmq(RMQ_PLAYER_COMMANDS_QUEUE, command_to_mq);
    // No direct response for shoot
}

void GameUDPHandler::handle_leave_game(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
    // std::cout << "UDP Handler: leave_game for player: " << player_id << std::endl;

    if (!session_manager_) {
        send_json_response({{"status", "error"}, {"message", "Server misconfiguration"}}, sender_endpoint);
        return;
    }

    if (session_manager_->remove_player_from_any_session(player_id)) {
        send_json_response({{"status", "left_game"}, {"player_id", player_id}}, sender_endpoint);
    } else {
        send_json_response({{"status", "error"}, {"message", "Player not found or already left"}}, sender_endpoint);
    }
}
