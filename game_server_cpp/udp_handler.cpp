#include "udp_handler.h"
#include <utility> // For std::move in some cases, though not strictly needed here

// RabbitMQ specific defines/helpers might be needed
// For example, for amqp_cstring_bytes
#include <amqp_framing.h>


// --- Constructor and Destructor ---
GameUDPHandler::GameUDPHandler(boost::asio::io_context& io_context, short port,
                               SessionManager* session_manager, TankPool* tank_pool) // Changed to pointers
    : socket_(io_context, udp::endpoint(udp::v4(), port)),
      session_manager_(session_manager), // Store pointers
      tank_pool_(tank_pool),             // Store pointers
      rabbitmq_conn_(nullptr),
      rabbitmq_connected_(false) {
    std::cout << "UDP Server initializing on port " << port << std::endl;
    if (setup_rabbitmq_connection()) {
        std::cout << "RabbitMQ connection successful." << std::endl;
    } else {
        std::cerr << "Failed to connect to RabbitMQ. Handler will operate without RabbitMQ." << std::endl;
    }
    start_receive();
}

GameUDPHandler::~GameUDPHandler() {
    std::cout << "UDP Handler shutting down." << std::endl;
    close_rabbitmq_connection();
}

// --- RabbitMQ Methods ---
bool GameUDPHandler::setup_rabbitmq_connection() {
    rabbitmq_conn_ = amqp_new_connection();
    if (!rabbitmq_conn_) {
        std::cerr << "Failed to create RabbitMQ connection object." << std::endl;
        return false;
    }

    amqp_socket_t *socket = amqp_tcp_socket_new(rabbitmq_conn_);
    if (!socket) {
        std::cerr << "Failed to create RabbitMQ TCP socket." << std::endl;
        amqp_destroy_connection(rabbitmq_conn_); // Clean up connection object
        rabbitmq_conn_ = nullptr;
        return false;
    }

    // Using "rabbitmq" as hostname, assuming it's resolvable (e.g., in Docker)
    int status = amqp_socket_open(socket, "rabbitmq", 5672);
    if (status) {
        std::cerr << "Failed to open RabbitMQ TCP socket: " << amqp_error_string2(status) << std::endl;
        // No need to destroy socket explicitly here, amqp_destroy_connection handles it
        amqp_destroy_connection(rabbitmq_conn_);
        rabbitmq_conn_ = nullptr;
        return false;
    }

    amqp_rpc_reply_t login_reply = amqp_login(rabbitmq_conn_, "/", 0, AMQP_DEFAULT_FRAME_SIZE, 0, AMQP_SASL_METHOD_PLAIN, "user", "password");
    if (login_reply.reply_type != AMQP_RESPONSE_NORMAL) {
        std::cerr << "RabbitMQ login failed: " << amqp_error_string2(login_reply.library_error) << std::endl;
        amqp_destroy_connection(rabbitmq_conn_);
        rabbitmq_conn_ = nullptr;
        return false;
    }

    amqp_channel_open(rabbitmq_conn_, 1);
    amqp_rpc_reply_t channel_reply = amqp_get_rpc_reply(rabbitmq_conn_);
    if (channel_reply.reply_type != AMQP_RESPONSE_NORMAL) {
        std::cerr << "Failed to open RabbitMQ channel: " << amqp_error_string2(channel_reply.library_error) << std::endl;
        amqp_destroy_connection(rabbitmq_conn_);
        rabbitmq_conn_ = nullptr;
        return false;
    }

    // Declare 'player_commands' queue
    // amqp_queue_declare(conn, channel, queue, passive, durable, exclusive, auto_delete, arguments)
    amqp_queue_declare_ok_t *r = amqp_queue_declare(rabbitmq_conn_, 1, amqp_cstring_bytes("player_commands"), 0, 0, 0, 0, amqp_empty_table);
    if (!r) {
        amqp_rpc_reply_t queue_declare_reply = amqp_get_rpc_reply(rabbitmq_conn_);
        std::cerr << "Failed to declare queue 'player_commands': " << amqp_error_string2(queue_declare_reply.library_error) << std::endl;
        // It's possible the queue already exists, which might not be a fatal error depending on flags.
        // For this setup, we'll treat failure to declare (even if exists) as an issue for simplicity of error check.
        // A more robust check would inspect the specific error.
        amqp_destroy_connection(rabbitmq_conn_);
        rabbitmq_conn_ = nullptr;
        return false;
    }
    // amqp_bytes_free(r->queue); // r is null on failure, so this is not safe here. amqp_destroy_connection will clean up.


    rabbitmq_connected_ = true;
    std::cout << "RabbitMQ connection established and 'player_commands' queue declared." << std::endl;
    return true;
}

void GameUDPHandler::publish_to_rabbitmq(const std::string& queue_name, const nlohmann::json& message_json) {
    if (!rabbitmq_connected_ || !rabbitmq_conn_) {
        std::cerr << "Cannot publish to RabbitMQ: Not connected." << std::endl;
        return;
    }

    std::string message_body = message_json.dump();
    amqp_bytes_t message_bytes;
    message_bytes.len = message_body.length();
    message_bytes.bytes = (void*)message_body.c_str();

    // amqp_basic_publish(conn, channel, exchange, routing_key, mandatory, immediate, properties, body)
    // For a direct queue, exchange is empty string (default) and routing_key is the queue name.
    int status = amqp_basic_publish(rabbitmq_conn_, 1, amqp_empty_bytes, amqp_cstring_bytes(queue_name.c_str()),
                                    0, 0, NULL, message_bytes);

    if (status) {
        std::cerr << "Failed to publish message to RabbitMQ queue '" << queue_name << "': " << amqp_error_string2(status) << std::endl;
    } else {
        std::cout << "Message published to RabbitMQ queue '" << queue_name << "': " << message_body << std::endl;
    }
}

void GameUDPHandler::close_rabbitmq_connection() {
    if (rabbitmq_conn_) {
        std::cout << "Closing RabbitMQ connection." << std::endl;
        amqp_channel_close(rabbitmq_conn_, 1, AMQP_REPLY_SUCCESS);
        amqp_connection_close(rabbitmq_conn_, AMQP_REPLY_SUCCESS);
        int status = amqp_destroy_connection(rabbitmq_conn_);
         if (status < 0) {
            std::cerr << "Error destroying RabbitMQ connection: " << amqp_error_string2(status) << std::endl;
        }
        rabbitmq_conn_ = nullptr; // Mark as destroyed
    }
    rabbitmq_connected_ = false;
}


// --- Core Network Logic ---
void GameUDPHandler::start_receive() {
    socket_.async_receive_from(
        boost::asio::buffer(recv_buffer_), sender_endpoint_,
        [this](const boost::system::error_code& error, std::size_t bytes_transferred) {
            handle_receive(error, bytes_transferred);
        });
}

void GameUDPHandler::handle_receive(const boost::system::error_code& error, std::size_t bytes_transferred) {
    if (!error) {
        std::string message_str(recv_buffer_.data(), bytes_transferred);
        // std::cout << "Received " << bytes_transferred << " bytes from " << sender_endpoint_.address().to_string() << ":" << sender_endpoint_.port() << std::endl;
        // std::cout << "Data: " << message_str << std::endl;

        process_message(message_str, sender_endpoint_);
        // Echo back the received message for now
        // send_message("ECHO: " + message_str, sender_endpoint_);
    } else {
        std::cerr << "Receive error: " << error.message() << std::endl;
    }
    // Listen for next message
    start_receive();
}

void GameUDPHandler::process_message(const std::string& message_str, const udp::endpoint& sender_endpoint) {
    // std::cout << "Processing message from " << sender_endpoint.address().to_string() << ":" << sender_endpoint.port() << ": " << message_str << std::endl;
    try {
        json parsed_message = json::parse(message_str);
        // std::cout << "Successfully parsed JSON: " << parsed_message.dump(2) << std::endl;

        if (!parsed_message.contains("player_id") || !parsed_message.contains("action")) {
            std::cerr << "Message missing 'player_id' or 'action'." << std::endl;
            send_message("{\"status\": \"error\", \"message\": \"Missing player_id or action\"}", sender_endpoint);
            return;
        }

        std::string action = parsed_message["action"].get<std::string>();
        // player_id is usually available in all messages, but some handlers might not need it directly from top-level msg if it's implicit

        if (action == "join_game") {
            handle_join_game(parsed_message, sender_endpoint);
        } else if (action == "move") {
            handle_move(parsed_message, sender_endpoint);
        } else if (action == "shoot") {
            handle_shoot(parsed_message, sender_endpoint);
        } else if (action == "leave_game") {
            handle_leave_game(parsed_message, sender_endpoint);
        } else {
            std::cerr << "Unknown action: " << action << std::endl;
            send_message("{\"status\": \"error\", \"message\": \"Unknown action: " + action + "\"}", sender_endpoint);
        }

    } catch (json::parse_error& e) {
        std::cerr << "JSON parsing error: " << e.what() << " for message: " << message_str << std::endl;
        // Optionally send an error back to the client
        send_message("{\"status\": \"error\", \"message\": \"Invalid JSON format\"}", sender_endpoint);
    }
}

void GameUDPHandler::send_message(const std::string& message, const udp::endpoint& target_endpoint) {
    socket_.async_send_to(
        boost::asio::buffer(message), target_endpoint,
        [this](const boost::system::error_code& error, std::size_t bytes_transferred) {
            handle_send(error, bytes_transferred);
        });
}

void GameUDPHandler::handle_send(const boost::system::error_code& error, std::size_t bytes_transferred) {
    if (!error) {
        // std::cout << "Sent " << bytes_transferred << " bytes to " /* << target_endpoint_ (not available in this callback directly) */ << std::endl;
    } else {
        std::cerr << "Send error: " << error.message() << std::endl;
    }
}

// --- Action Handlers ---
void GameUDPHandler::handle_join_game(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
    std::cout << "Handling join_game for player: " << player_id << " via UDP." << std::endl;

    if (!session_manager_ || !tank_pool_) {
        std::cerr << "UDP Handler: SessionManager or TankPool not initialized!" << std::endl;
        send_message("{\"status\": \"error\", \"message\": \"Server misconfiguration\"}", sender_endpoint);
        return;
    }

    auto existing_session = session_manager_->get_session_by_player_id(player_id);
    if (existing_session) {
        std::cout << "Player " << player_id << " already in session " << existing_session->get_id() << "." << std::endl;
        json response = {
            {"status", "error"},
            {"message", "already_in_session"},
            {"session_id", existing_session->get_id()}
        };
        send_message(response.dump(), sender_endpoint);
        return;
    }

    auto tank = tank_pool_->acquire_tank();
    if (!tank) {
        std::cerr << "Failed to acquire tank for player " << player_id << "." << std::endl;
        json response = {
            {"status", "join_failed"},
            {"message", "no_tanks_available"}
        };
        send_message(response.dump(), sender_endpoint);
        return;
    }

    // For UDP, we might want a specific session or create a new one.
    // Let's assume we try to add to a default session or create one if none suitable.
    // For simplicity, let's create a new session for each new UDP player for now.
    // A better approach would be to have a "lobby" or find available sessions.
    auto game_session = session_manager_->create_session();
    if (!game_session) {
        std::cerr << "Failed to create or get a game session for player " << player_id << "." << std::endl;
        tank_pool_->release_tank(tank->get_id()); // Release tank if session creation failed
        send_message("{\"status\": \"join_failed\", \"message\": \"server_error_creating_session\"}", sender_endpoint);
        return;
    }

    std::string udp_addr_str = sender_endpoint.address().to_string() + ":" + std::to_string(sender_endpoint.port());
    session_manager_->add_player_to_session(game_session->get_id(), player_id, udp_addr_str, tank, true /*is_udp_player*/);

    json response = {
        {"status", "joined"},
        {"session_id", game_session->get_id()},
        {"tank_id", tank->get_id()},
        {"initial_state", tank->get_state()}
    };
    send_message(response.dump(), sender_endpoint);
    std::cout << "Player " << player_id << " joined session " << game_session->get_id() << " with tank " << tank->get_id() << std::endl;
}

void GameUDPHandler::handle_move(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
    // std::cout << "Handling move for player: " << player_id << std::endl; // Too verbose for UDP

    if (!session_manager_) { return; }
    auto session = session_manager_->get_session_by_player_id(player_id);
    if (!session) { // No need to check session->has_player, get_session_by_player_id implies it
        // send_message("{\"status\": \"error\", \"message\": \"Player not in an active session\"}", sender_endpoint); // Can be too noisy for UDP
        return;
    }

    auto tank = session->get_tank_for_player(player_id);
    if (!tank) {
        // send_message("{\"status\": \"error\", \"message\": \"Player has no tank in session\"}", sender_endpoint);
        return;
    }

    if (!msg.contains("position")) {
        send_message("{\"status\": \"error\", \"message\": \"Move command missing position\"}", sender_endpoint);
        return;
    }

    json command_json = {
        {"player_id", player_id},
        {"command", "move"},
        {"details", {
            {"source", "udp_handler"},
            {"tank_id", tank_id},
            {"new_position", msg["position"]}
        }}
    };
    publish_to_rabbitmq("player_commands", command_json);
    // No direct response needed for move, state updates will come via game state broadcasts
}

void GameUDPHandler::handle_shoot(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
    // std::cout << "Handling shoot for player: " << player_id << std::endl; // Too verbose

    if (!session_manager_) { return; }
    auto session = session_manager_->get_session_by_player_id(player_id);
    if (!session) {
        // send_message("{\"status\": \"error\", \"message\": \"Player not in an active session\"}", sender_endpoint);
        return;
    }
    auto tank = session->get_tank_for_player(player_id);
    if (!tank) {
        // send_message("{\"status\": \"error\", \"message\": \"Player has no tank in session\"}", sender_endpoint);
        return;
    }

    json command_json = {
        {"player_id", player_id},
        {"command", "shoot"},
        {"details", {
            {"source", "udp_handler"},
            {"tank_id", tank->get_id()} // Use tank's actual ID
            // Future: add target, direction, etc.
        }}
    };
    publish_to_rabbitmq("player_commands", command_json);
    // No direct response needed for shoot
}

void GameUDPHandler::handle_leave_game(const json& msg, const udp::endpoint& sender_endpoint) {
    std::string player_id = msg["player_id"].get<std::string>();
    std::cout << "Handling leave_game for player: " << player_id << " via UDP." << std::endl;

    if (!session_manager_ || !tank_pool_) {
         std::cerr << "UDP Handler: SessionManager or TankPool not initialized for leave_game!" << std::endl;
        send_message("{\"status\": \"error\", \"message\": \"Server misconfiguration\"}", sender_endpoint);
        return;
    }

    // SessionManager::remove_player_from_any_session handles tank release and map cleanup
    if (session_manager_->remove_player_from_any_session(player_id)) {
        json response = {
            {"status", "left_game"},
            {"player_id", player_id}
        };
        send_message(response.dump(), sender_endpoint);
        std::cout << "Player " << player_id << " left the game (via UDP command)." << std::endl;
    } else {
        send_message("{\"status\": \"error\", \"message\": \"Player not found or already left\"}", sender_endpoint);
        std::cout << "Player " << player_id << " attempted to leave but was not found in any session." << std::endl;
    }
}
