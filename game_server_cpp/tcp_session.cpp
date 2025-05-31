#include "tcp_session.h"
#include <boost/algorithm/string.hpp> // For string splitting

GameTCPSession::GameTCPSession(tcp::socket socket,
                               SessionManager* sm, // Changed to pointer
                               TankPool* tp,       // Changed to pointer
                               amqp_connection_state_t rabbitmq_conn_state)
    : socket_(std::move(socket)),
      session_manager_(sm),   // Store pointer
      tank_pool_(tp),         // Store pointer
      rabbitmq_conn_state_(rabbitmq_conn_state),
      authenticated_(false) {
    std::cout << "TCP Session created for " << socket_.remote_endpoint().address().to_string() << ":" << socket_.remote_endpoint().port() << std::endl;
}

void GameTCPSession::start() {
    do_write("SERVER_ACK_CONNECTED\n"); // Send initial connection acknowledgment
    do_read(); // Start reading commands
}

void GameTCPSession::close_session(const std::string& reason) {
    if (socket_.is_open()) {
        std::cout << "Closing TCP session for player " << username_
                  << " (" << socket_.remote_endpoint().address().to_string() << ":" << socket_.remote_endpoint().port() << "). Reason: " << reason << std::endl;

        if (authenticated_ && !username_.empty()) {
            // Perform cleanup if the player was authenticated and in a session
            if (session_manager_) { // Check if session_manager_ is valid
                session_manager_->remove_player_from_any_session(username_);
                // remove_player_from_any_session should handle tank release via TankPool
                 std::cout << "Player " << username_ << " (and their tank) removed from session via SessionManager during close_session." << std::endl;
            } else {
                std::cerr << "TCP Session (" << username_ << "): SessionManager is null in close_session. Cannot remove player or release tank." << std::endl;
                 // Fallback or direct tank release if tank_pool_ is available and tank ID known
                if (tank_pool_ && !assigned_tank_id_.empty()) {
                    tank_pool_->release_tank(assigned_tank_id_);
                     std::cout << "Tank " << assigned_tank_id_ << " released directly via TankPool due to null SessionManager." << std::endl;
                }
            }
            authenticated_ = false; // Ensure no further authenticated actions
            username_.clear();
            current_session_id_.clear();
            assigned_tank_id_.clear();
        }

        boost::system::error_code ec;
        socket_.shutdown(tcp::socket::shutdown_both, ec);
        if (ec && ec != boost::system::errc::not_connected) { // not_connected can happen if client already closed
            std::cerr << "TCP socket shutdown error: " << ec.message() << std::endl;
        }
        socket_.close(ec);
        if (ec) {
            std::cerr << "TCP socket close error: " << ec.message() << std::endl;
        }
    }
    // The shared_ptr to this session will be destroyed once all handlers complete.
}


void GameTCPSession::do_read() {
    auto self(shared_from_this()); // Keep session alive
    boost::asio::async_read_until(socket_, read_buffer_, '\n',
        [this, self](const boost::system::error_code& error, std::size_t length) {
            handle_read(error, length);
        });
}

void GameTCPSession::handle_read(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        std::istream is(&read_buffer_);
        std::string line;
        std::getline(is, line); // Extracts the line including the delimiter, then removes it from buffer

        // Trim any trailing \r if present (common with telnet clients)
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }

        if (!line.empty()) {
            std::cout << "TCP Recv from " << (username_.empty() ? socket_.remote_endpoint().address().to_string() : username_) << ": " << line << std::endl;
            process_command(line);
        }
        do_read(); // Continue reading for the next command
    } else if (error == boost::asio::error::eof) {
        close_session("Client disconnected (EOF).");
    } else if (error == boost::asio::error::connection_reset) {
        close_session("Client connection reset.");
    } else if (error == boost::asio::error::operation_aborted) {
        std::cout << "TCP Read operation aborted for " << username_ << "." << std::endl; // Usually happens during shutdown
    }
    else {
        std::cerr << "TCP Read error for " << username_ << ": " << error.message() << std::endl;
        close_session("Read error.");
    }
}

void GameTCPSession::process_command(const std::string& line) {
    std::vector<std::string> parts;
    boost::split(parts, line, boost::is_any_of(" "), boost::token_compress_on);

    if (parts.empty() || parts[0].empty()) {
        return; // Empty command
    }

    std::string command_verb = parts[0];
    boost::to_upper(command_verb); // Convert command to uppercase for case-insensitive matching

    // Prepare args vector (excluding the command verb itself)
    std::vector<std::string> args_list;
    if (parts.size() > 1) {
        args_list.assign(parts.begin() + 1, parts.end());
    }

    if (!authenticated_ && command_verb != "LOGIN" && command_verb != "REGISTER" && command_verb != "HELP" && command_verb != "QUIT") {
        // Allow HELP and QUIT even if not authenticated.
        do_write("SERVER_ERROR UNAUTHORIZED Please LOGIN or REGISTER first to use command: " + command_verb + "\n");
        return;
    }

    if (command_verb == "LOGIN") {
        handle_login(args_list);
    } else if (command_verb == "REGISTER") {
        handle_register(args_list);
    } else if (command_verb == "MOVE") {
        handle_move(args_list);
    } else if (command_verb == "SHOOT") {
        handle_shoot(args_list);
    } else if (command_verb == "SAY") {
        handle_say(args_list);
    } else if (command_verb == "HELP") {
        handle_help(args_list);
    } else if (command_verb == "PLAYERS") {
        handle_players(args_list);
    } else if (command_verb == "QUIT") {
        handle_quit(args_list);
    }
    else {
        do_write("SERVER_ERROR UNKNOWN_COMMAND " + command_verb + "\n");
    }
}

void GameTCPSession::do_write(const std::string& msg) {
    // For simplicity, directly writing. A more robust server might queue messages.
    // Ensure socket is open before attempting to write
    if (!socket_.is_open()) {
        std::cerr << "TCP Write error: Socket is not open for player " << username_ << std::endl;
        return;
    }
    auto self(shared_from_this());
    boost::asio::async_write(socket_, boost::asio::buffer(msg.data(), msg.length()),
        [this, self, msg_content=msg](const boost::system::error_code& error, std::size_t length) {
            handle_write(error, length);
        });
}

void GameTCPSession::handle_write(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        // std::cout << "TCP Sent " << length << " bytes to " << username_ << std::endl;
    } else {
        std::cerr << "TCP Write error for " << username_ << ": " << error.message() << std::endl;
        // Don't necessarily close session on write error, client might still be readable
        // or it might be a temporary issue. However, repeated write errors would be an issue.
        // For now, we'll let read errors handle session closing.
    }
}

void GameTCPSession::publish_to_rabbitmq_internal(const std::string& queue_name, const nlohmann::json& message_json) {
    if (!rabbitmq_conn_state_) {
        std::cerr << "TCP Session (" << username_ << "): RabbitMQ connection state is not valid. Cannot publish." << std::endl;
        return;
    }

    std::string message_body = message_json.dump();
    amqp_bytes_t message_bytes;
    message_bytes.len = message_body.length();
    message_bytes.bytes = (void*)message_body.c_str();

    int status = amqp_basic_publish(rabbitmq_conn_state_, 1, amqp_empty_bytes, amqp_cstring_bytes(queue_name.c_str()),
                                    0, 0, NULL, message_bytes);
    if (status) {
        std::cerr << "TCP Session (" << username_ << "): Failed to publish message to RabbitMQ queue '" << queue_name << "': " << amqp_error_string2(status) << std::endl;
    } else {
        std::cout << "TCP Session (" << username_ << "): Message published to RabbitMQ queue '" << queue_name << "': " << message_body << std::endl;
    }
}

// --- Command Handler Implementations ---
void GameTCPSession::handle_login(const std::vector<std::string>& args) {
    if (args.size() < 2) { // Expects at least username and password
        do_write("SERVER_ERROR LOGIN_FAILED Invalid arguments. Usage: LOGIN <username> <password>\n");
        return;
    }
    std::string provided_username = args[0];
    std::string password = args[1];

    // Mock authentication:
    // In a real system, this would involve AuthClient/service
    if ((provided_username == "player1" && password == "pass1") || (provided_username == "player2" && password == "pass2") || (provided_username == "test" && password == "test")) {
        if (authenticated_ && username_ == provided_username) {
            do_write("SERVER_ERROR LOGIN_FAILED Already logged in as " + username_ + "\n");
            return;
        }
        if (authenticated_) { // Logged in as someone else? Unlikely with current flow but good check.
             do_write("SERVER_ERROR LOGIN_FAILED Already logged in as different user. Please QUIT first.\n");
            return;
        }


        username_ = provided_username;
        authenticated_ = true;

        std::cout << "Player " << username_ << " authenticated successfully via TCP." << std::endl;

        if (!tank_pool_ || !session_manager_) {
            std::cerr << "Login for " << username_ << " failed: TankPool or SessionManager not initialized." << std::endl;
            do_write("SERVER_ERROR LOGIN_FAILED Server configuration error.\n");
            authenticated_ = false; // Rollback
            username_.clear();
            return;
        }

        auto tank = tank_pool_->acquire_tank();
        if (tank) {
            assigned_tank_id_ = tank->get_id(); // Use getter

            // Attempt to add to an existing session or create a new one.
            // For simplicity, let's try to get a "default_tcp_session" or create one.
            // Or, SessionManager could have a method like "find_or_create_available_session()".
            // For now, let's use create_session() which makes a new one each time.
            auto game_session = session_manager_->create_session();
            if (!game_session) {
                 std::cerr << "Login for " << username_ << " failed: Could not create/get game session." << std::endl;
                tank_pool_->release_tank(assigned_tank_id_); // Release acquired tank
                assigned_tank_id_.clear();
                authenticated_ = false;
                username_.clear();
                do_write("SERVER_ERROR LOGIN_FAILED Server error creating session.\n");
                return;
            }
            current_session_id_ = game_session->get_id();

            std::string client_addr_info = socket_.remote_endpoint().address().to_string() + ":" + std::to_string(socket_.remote_endpoint().port());
            // Pass `false` for is_udp_player
            session_manager_->add_player_to_session(current_session_id_, username_, client_addr_info, tank, false);

            do_write("SERVER_RESPONSE LOGIN_SUCCESS Welcome " + username_ + ". Token: " + username_ + "\n");
            do_write("SERVER: Player " + username_ + " joined game session " + current_session_id_ + " with tank " + assigned_tank_id_ + ".\n");
            do_write("SERVER: Tank state: " + tank->get_state().dump() + "\n");
        } else {
            authenticated_ = false; // Rollback auth if no tank
            username_.clear();
            do_write("SERVER_ERROR LOGIN_FAILED No tanks available.\n");
            std::cerr << "Login failed for " << provided_username << ": No tanks available." << std::endl;
        }
    } else {
        do_write("SERVER_ERROR LOGIN_FAILED Invalid credentials for username: " + provided_username + "\n");
    }
}

void GameTCPSession::handle_register(const std::vector<std::string>& args) {
    if (args.size() < 2) {
        do_write("SERVER_ERROR REGISTER_FAILED Invalid arguments. Usage: REGISTER <username> <password>\n");
        return;
    }
    do_write("SERVER_ERROR REGISTER_FAILED Registration via game server is not supported yet.\n");
    std::cout << "Player attempted registration: " << args[0] << std::endl;
}

void GameTCPSession::handle_move(const std::vector<std::string>& args) {
    if (!authenticated_) { do_write("SERVER_ERROR UNAUTHORIZED\n"); return; }
    if (args.size() < 2) {
        do_write("SERVER_ERROR MOVE_FAILED Invalid arguments. Usage: MOVE <X> <Y>\n");
        return;
    }
    try {
        int x = std::stoi(args[0]);
        int y = std::stoi(args[1]);

        if (!session_manager_ || current_session_id_.empty() || assigned_tank_id_.empty()) {
             do_write("SERVER_ERROR MOVE_FAILED Player not fully in a game (no session or tank), or server misconfigured.\n");
            return;
        }
        // No need to get session or tank directly here, just use stored IDs for the Kafka message.
        // Tank movement itself is handled by the Tank object via Kafka, not directly manipulated here post-command.

        json command_json = {
            {"player_id", username_}, // username_ is our player_id in this context
            {"command", "move"},
            {"details", {
                {"source", "tcp_handler"},
                {"tank_id", assigned_tank_id_},
                {"new_position", {x, y}}
            }}
        };
        publish_to_rabbitmq_internal("player_commands", command_json);
        do_write("SERVER_ACK MOVE_COMMAND_SENT\n");
    } catch (const std::invalid_argument& ia) {
        do_write("SERVER_ERROR MOVE_FAILED Invalid coordinates (not numbers).\n");
    } catch (const std::out_of_range& oor) {
        do_write("SERVER_ERROR MOVE_FAILED Coordinate value out of range.\n");
    }
}

void GameTCPSession::handle_shoot(const std::vector<std::string>& args) {
    if (!authenticated_) { do_write("SERVER_ERROR UNAUTHORIZED\n"); return; }

    if (current_session_id_.empty() || assigned_tank_id_.empty()) {
        do_write("SERVER_ERROR SHOOT_FAILED Player not fully in a game (no session or tank).\n");
        return;
    }

    json command_json = {
            {"player_id", username_}, // username_ is our player_id
        {"command", "shoot"},
        {"details", {
            {"source", "tcp_handler"},
                {"tank_id", assigned_tank_id_} // Use the stored tank ID
            // Future: add target/direction from args if any
        }}
    };
    publish_to_rabbitmq_internal("player_commands", command_json);
    do_write("SERVER_ACK SHOOT_COMMAND_SENT\n");
}

void GameTCPSession::handle_say(const std::vector<std::string>& args) {
    if (!authenticated_) { do_write("SERVER_ERROR UNAUTHORIZED\n"); return; }
    if (args.empty()) {
        do_write("SERVER_ERROR SAY_FAILED Message missing. Usage: SAY <message ...>\n");
        return;
    }
    std::string message_text;
    for (size_t i = 0; i < args.size(); ++i) { // Corrected loop to include all parts of args
        message_text += args[i] + (i == args.size() - 1 ? "" : " ");
    }

    // For now, just acknowledge to self. Broadcast would be a separate feature.
    do_write("SERVER: You said: " + message_text + "\n");
    std::cout << username_ << " (session:" << current_session_id_ << ") says: " << message_text << std::endl;

    // Optionally, also send this to RabbitMQ for logging or other processing
    json say_command_json = {
        {"player_id", username_},
        {"command", "say_broadcast"}, // Different command type for server-side processing
        {"details", {
            {"source", "tcp_handler"},
            {"session_id", current_session_id_},
            {"text", message_text}
        }}
    };
    publish_to_rabbitmq_internal("game_chat_messages", say_command_json); // Example: different queue for chat
}

void GameTCPSession::handle_help(const std::vector<std::string>& args) {
    // No authentication check needed usually for HELP
    std::string help_msg = "SERVER: Available commands:\n";
    help_msg += "  LOGIN <username> <password>\n";
    help_msg += "  REGISTER <username> <password> (Currently not functional)\n";
    if (authenticated_) {
        help_msg += "  MOVE <x> <y>\n";
        help_msg += "  SHOOT\n";
        help_msg += "  SAY <message ...>\n";
        help_msg += "  PLAYERS\n";
    }
    help_msg += "  HELP\n";
    help_msg += "  QUIT\n";
    do_write(help_msg);
}

void GameTCPSession::handle_players(const std::vector<std::string>& args) {
    if (!authenticated_) { do_write("SERVER_ERROR UNAUTHORIZED\n"); return; }

    if (current_session_id_.empty() || !session_manager_) {
        do_write("SERVER_INFO You are not currently in a game session, or server misconfigured.\n");
        return;
    }

    auto game_session = session_manager_->get_session(current_session_id_);
    if (game_session) {
        const auto& players_map = game_session->get_players(); // Get the actual map
        if (players_map.empty()) {
            do_write("SERVER_INFO No players currently in your session '" + current_session_id_ + "'.\n");
        } else {
            std::string players_list_msg = "SERVER: Players in session '" + current_session_id_ + "':\n";
            for (const auto& pair : players_map) {
                players_list_msg += "  - " + pair.first; // pair.first is player_id (username)
                if (pair.first == username_) {
                    players_list_msg += " (You)";
                }
                // Could add tank ID: pair.second.tank->get_id() if needed
                players_list_msg += "\n";
            }
            do_write(players_list_msg);
        }
    } else {
        do_write("SERVER_ERROR Could not retrieve session information for session ID: " + current_session_id_ + "\n");
    }
}

void GameTCPSession::handle_quit(const std::vector<std::string>& args) {
    do_write("SERVER_RESPONSE GOODBYE Closing connection.\n");
    std::cout << "Player " << username_ << " initiated QUIT." << std::endl;

    // close_session() will handle the cleanup using SessionManager and TankPool
    close_session("Player quit command.");
}
