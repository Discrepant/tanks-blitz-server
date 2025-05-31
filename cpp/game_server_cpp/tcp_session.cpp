#include "tcp_session.h"
#include "session_manager.h" // For SessionManager methods
#include "tank_pool.h"       // For TankPool methods
#include "tank.h"            // For Tank methods
#include <boost/algorithm/string.hpp> // For string splitting (e.g. boost::split)
#include <chrono>             // For gRPC deadlines

// Define static const members if any (e.g. queue names)
const std::string GameTCPSession::RMQ_PLAYER_COMMANDS_QUEUE = "player_commands";
const std::string GameTCPSession::RMQ_CHAT_MESSAGES_QUEUE = "game_chat_messages";


GameTCPSession::GameTCPSession(tcp::socket socket,
                               SessionManager* sm,
                               TankPool* tp,
                               amqp_connection_state_t rabbitmq_conn_state,
                               std::shared_ptr<grpc::Channel> grpc_auth_channel)
    : socket_(std::move(socket)),
      session_manager_(sm),
      tank_pool_(tp),
      rmq_conn_state_(rabbitmq_conn_state),
      authenticated_(false) {

    if (!session_manager_ || !tank_pool_) {
        std::cerr << "GameTCPSession FATAL: SessionManager or TankPool is null." << std::endl;
        // This session is likely unusable, could throw or set an error state.
    }
    if (grpc_auth_channel) {
        auth_grpc_stub_ = auth::AuthService::NewStub(grpc_auth_channel);
        // std::cout << "GameTCPSession: Auth gRPC Stub initialized." << std::endl;
    } else {
        std::cerr << "GameTCPSession FATAL: grpc_auth_channel is null. Authentication will fail." << std::endl;
    }
    // std::cout << "GameTCPSession created for " << socket_.remote_endpoint().address().to_string() << std::endl;
}

void GameTCPSession::start() {
    // std::cout << "GameTCPSession started for " << socket_.remote_endpoint().address().to_string() << std::endl;
    send_message("SERVER_ACK_CONNECTED Welcome to TankGame! Please LOGIN or REGISTER.\n");
    do_read();
}

void GameTCPSession::close_session(const std::string& reason) {
    if (socket_.is_open()) {
        std::cout << "GameTCPSession: Closing session for player '" << username_
                  << "' (" << socket_.remote_endpoint().address().to_string()
                  << "). Reason: " << reason << std::endl;

        if (authenticated_ && !username_.empty() && session_manager_) {
            // SessionManager::remove_player_from_any_session handles tank release.
            session_manager_->remove_player_from_any_session(username_);
        }

        boost::system::error_code ec;
        socket_.shutdown(tcp::socket::shutdown_both, ec); // Graceful shutdown
        socket_.close(ec); // Close socket
    }
    // Clear sensitive data
    authenticated_ = false;
    username_.clear();
    current_session_id_.clear();
    assigned_tank_id_.clear();
}

void GameTCPSession::do_read() {
    if (!socket_.is_open()) return; // Don't read if socket is closed

    auto self(shared_from_this()); // Keep session alive during async operation
    boost::asio::async_read_until(socket_, read_buffer_, '\n',
        [this, self](const boost::system::error_code& error, std::size_t length) {
            handle_read(error, length);
        });
}

void GameTCPSession::handle_read(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        std::istream is(&read_buffer_);
        std::string line;
        std::getline(is, line);

        if (!line.empty() && line.back() == '\r') { // Handle telnet's \r\n
            line.pop_back();
        }

        if (!line.empty()) {
            // std::cout << "TCP Recv from " << (username_.empty() ? socket_.remote_endpoint().address().to_string() : username_) << ": " << line << std::endl;
            process_command(line);
        }

        if (socket_.is_open()) { // If process_command didn't close the session
            do_read(); // Continue reading for the next command
        }
    } else if (error == boost::asio::error::eof) {
        close_session("Client disconnected (EOF).");
    } else if (error == boost::asio::error::connection_reset) {
        close_session("Client connection reset.");
    } else if (error == boost::asio::error::operation_aborted) {
        std::cout << "GameTCPSession: Read operation aborted for " << username_ << "." << std::endl;
    } else {
        std::cerr << "GameTCPSession: Read error for " << username_ << ": " << error.message() << std::endl;
        close_session("Read error.");
    }
}

void GameTCPSession::send_message(const std::string& msg) {
    if (!socket_.is_open()){
         std::cerr << "GameTCPSession: Attempted to send message on closed socket to " << username_ << std::endl;
        return;
    }

    bool write_in_progress = !write_msgs_queue_.empty();
    write_msgs_queue_.push_back(msg);
    if (!write_in_progress) {
        do_write();
    }
}

void GameTCPSession::do_write() {
    if (!socket_.is_open() || write_msgs_queue_.empty()) {
        return;
    }
    auto self(shared_from_this());
    boost::asio::async_write(socket_,
        boost::asio::buffer(write_msgs_queue_.front().data(), write_msgs_queue_.front().length()),
        [this, self](const boost::system::error_code& error, std::size_t length) {
            handle_write(error, length);
        });
}

void GameTCPSession::handle_write(const boost::system::error_code& error, std::size_t length) {
    if (!error) {
        // std::cout << "TCP Sent " << length << " bytes to " << username_ << std::endl;
        { // Scope for lock if accessing queue from multiple threads (though ASIO handlers are serialized)
            if (!write_msgs_queue_.empty()) {
                 write_msgs_queue_.pop_front();
            }
        }
        if (!write_msgs_queue_.empty()) {
            do_write(); // Write next message in queue
        }
    } else {
        std::cerr << "GameTCPSession: Write error for " << username_ << ": " << error.message() << std::endl;
        close_session("Write error.");
    }
}


void GameTCPSession::process_command(const std::string& line) {
    std::vector<std::string> parts;
    boost::split(parts, line, boost::is_any_of(" "), boost::token_compress_on);

    if (parts.empty() || parts[0].empty()) return;

    std::string command_verb = parts[0];
    boost::to_upper(command_verb);
    std::vector<std::string> args_list;
    if (parts.size() > 1) {
        args_list.assign(parts.begin() + 1, parts.end());
    }

    if (!authenticated_ && command_verb != "LOGIN" && command_verb != "REGISTER" && command_verb != "HELP" && command_verb != "QUIT") {
        send_message("SERVER_ERROR UNAUTHORIZED Please LOGIN or REGISTER first to use command: " + command_verb + "\n");
        return;
    }

    if (command_verb == "LOGIN") handle_login(args_list);
    else if (command_verb == "REGISTER") handle_register(args_list);
    else if (command_verb == "MOVE") handle_move(args_list);
    else if (command_verb == "SHOOT") handle_shoot(args_list);
    else if (command_verb == "SAY") handle_say(args_list);
    else if (command_verb == "HELP") handle_help(args_list);
    else if (command_verb == "PLAYERS") handle_players(args_list);
    else if (command_verb == "QUIT") handle_quit(args_list);
    else send_message("SERVER_ERROR UNKNOWN_COMMAND " + command_verb + "\n");
}

// --- Command Handlers ---
void GameTCPSession::handle_login(const std::vector<std::string>& args) {
    if (args.size() < 2) {
        send_message("SERVER_ERROR LOGIN_FAILED Invalid arguments. Usage: LOGIN <username> <password>\n");
        return;
    }
    std::string provided_username = args[0];
    std::string password = args[1];

    if (!auth_grpc_stub_) {
        send_message("SERVER_ERROR LOGIN_FAILED Auth service not available.\n");
        return;
    }
    if (authenticated_) {
        send_message("SERVER_ERROR LOGIN_FAILED Already logged in as " + username_ + ".\n");
        return;
    }

    auth::AuthRequest grpc_request;
    grpc_request.set_username(provided_username);
    grpc_request.set_password(password);
    auth::AuthResponse grpc_response;
    grpc::ClientContext context;
    context.set_deadline(std::chrono::system_clock::now() + std::chrono::milliseconds(1000)); // 1s timeout

    grpc::Status status = auth_grpc_stub_->AuthenticateUser(&context, grpc_request, &grpc_response);

    if (status.ok() && grpc_response.authenticated()) {
        username_ = provided_username;
        authenticated_ = true;

        if (!tank_pool_ || !session_manager_) {
            send_message("SERVER_ERROR LOGIN_SUCCESSFUL_BUT_GAME_UNAVAILABLE Server error.\n");
            authenticated_ = false; username_.clear(); // Rollback
            return;
        }
        auto tank = tank_pool_->acquire_tank();
        if (tank) {
            assigned_tank_id_ = tank->get_id();
            // Use find_or_create_session_for_player for better session management
            auto game_session = session_manager_->find_or_create_session_for_player(
                username_,
                socket_.remote_endpoint().address().to_string() + ":" + std::to_string(socket_.remote_endpoint().port()),
                tank,
                false /*is_udp_player=false*/
            );

            if (game_session) {
                current_session_id_ = game_session->get_id();
                send_message("SERVER_RESPONSE LOGIN_SUCCESS " + grpc_response.message() + " Token: " + grpc_response.token() + "\n");
                send_message("SERVER: Player " + username_ + " joined game session " + current_session_id_ + " with tank " + assigned_tank_id_ + ".\n");
                send_message("SERVER: Tank state: " + tank->get_state().dump() + "\n");
            } else {
                send_message("SERVER_ERROR LOGIN_FAILURE Could not join/create game session.\n");
                tank_pool_->release_tank(assigned_tank_id_); // Release acquired tank
                assigned_tank_id_.clear();
                authenticated_ = false; username_.clear(); // Rollback
            }
        } else { // No tank available
            send_message("SERVER_ERROR LOGIN_FAILURE No tanks available.\n");
            authenticated_ = false; username_.clear(); // Rollback
        }
    } else { // gRPC error or auth failed from service
        std::string error_msg = status.ok() ? grpc_response.message() : ("Auth service error (" + std::to_string(status.error_code()) + "): " + status.error_message());
        send_message("SERVER_ERROR LOGIN_FAILED " + error_msg + "\n");
    }
}

void GameTCPSession::handle_register(const std::vector<std::string>& args) {
    send_message("SERVER_ERROR REGISTER_FAILED Registration via game server is not supported yet.\n");
}

void GameTCPSession::handle_move(const std::vector<std::string>& args) {
    if (!authenticated_) { send_message("SERVER_ERROR UNAUTHORIZED\n"); return; }
    if (args.size() < 2) {
        send_message("SERVER_ERROR MOVE_FAILED Invalid arguments. Usage: MOVE <X> <Y>\n"); return;
    }
    if (current_session_id_.empty() || assigned_tank_id_.empty() || !session_manager_) {
        send_message("SERVER_ERROR MOVE_FAILED Not in a game or server error.\n"); return;
    }
    try {
        // Assuming X and Y are the first two arguments for move
        json new_position_json = {{"x", std::stoi(args[0])}, {"y", std::stoi(args[1])}};
        json command_json = {
            {"player_id", username_}, {"command", "move"},
            {"details", {{"source", "tcp_handler"}, {"tank_id", assigned_tank_id_}, {"new_position", new_position_json}}}
        };
        publish_to_rabbitmq_internal(RMQ_PLAYER_COMMANDS_QUEUE, command_json);
        send_message("SERVER_ACK MOVE_COMMAND_SENT\n");
    } catch (const std::exception& e) {
        send_message("SERVER_ERROR MOVE_FAILED Invalid coordinates: " + std::string(e.what()) + "\n");
    }
}

void GameTCPSession::handle_shoot(const std::vector<std::string>& args) {
    if (!authenticated_) { send_message("SERVER_ERROR UNAUTHORIZED\n"); return; }
    if (current_session_id_.empty() || assigned_tank_id_.empty() || !session_manager_) {
        send_message("SERVER_ERROR SHOOT_FAILED Not in a game or server error.\n"); return;
    }
    json command_json = {
        {"player_id", username_}, {"command", "shoot"},
        {"details", {{"source", "tcp_handler"}, {"tank_id", assigned_tank_id_}}}
    };
    publish_to_rabbitmq_internal(RMQ_PLAYER_COMMANDS_QUEUE, command_json);
    send_message("SERVER_ACK SHOOT_COMMAND_SENT\n");
}

void GameTCPSession::handle_say(const std::vector<std::string>& args) {
    if (!authenticated_) { send_message("SERVER_ERROR UNAUTHORIZED\n"); return; }
    if (args.empty()) {
        send_message("SERVER_ERROR SAY_FAILED Message missing. Usage: SAY <message ...>\n"); return;
    }
    std::string message_text;
    for (size_t i = 0; i < args.size(); ++i) {
        message_text += args[i] + (i == args.size() - 1 ? "" : " ");
    }
    send_message("SERVER: You said: " + message_text + "\n"); // Echo back for now
    json chat_json = {
        {"player_id", username_}, {"command", "say_broadcast"}, // Or specific chat command
        {"details", {{"source", "tcp_handler"}, {"session_id", current_session_id_}, {"text", message_text}}}
    };
    publish_to_rabbitmq_internal(RMQ_CHAT_MESSAGES_QUEUE, chat_json); // Use a different queue for chat
}

void GameTCPSession::handle_help(const std::vector<std::string>& args) {
    std::string help_msg = "SERVER: Available commands:\n";
    help_msg += "  LOGIN <username> <password>\n";
    help_msg += "  REGISTER <username> <password> (Not functional)\n";
    if (authenticated_) {
        help_msg += "  MOVE <x> <y>\n  SHOOT\n  SAY <message ...>\n  PLAYERS\n";
    }
    help_msg += "  HELP\n  QUIT\n";
    send_message(help_msg);
}

void GameTCPSession::handle_players(const std::vector<std::string>& args) {
    if (!authenticated_ || !session_manager_) { send_message("SERVER_ERROR UNAUTHORIZED or server error.\n"); return; }
    if (current_session_id_.empty()) {
        send_message("SERVER_INFO You are not currently in a game session.\n"); return;
    }
    auto game_session = session_manager_->get_session(current_session_id_);
    if (game_session) {
        const auto& players_map = game_session->get_players();
        if (players_map.empty()) {
            send_message("SERVER_INFO No players currently in your session '" + current_session_id_ + "'.\n");
        } else {
            std::string list_msg = "SERVER: Players in session '" + current_session_id_ + "':\n";
            for (const auto& pair : players_map) {
                list_msg += "  - " + pair.first + (pair.first == username_ ? " (You)" : "") + "\n";
            }
            send_message(list_msg);
        }
    } else {
        send_message("SERVER_ERROR Could not retrieve session info for ID: " + current_session_id_ + "\n");
    }
}

void GameTCPSession::handle_quit(const std::vector<std::string>& args) {
    send_message("SERVER_RESPONSE GOODBYE Closing connection.\n");
    // std::cout << "GameTCPSession: Player " << username_ << " initiated QUIT." << std::endl;
    close_session("Player quit command.");
}

void GameTCPSession::publish_to_rabbitmq_internal(const std::string& queue_name, const nlohmann::json& message_json) {
    if (!rmq_conn_state_) {
        std::cerr << "GameTCPSession (" << username_ << "): RabbitMQ connection state is null. Cannot publish." << std::endl;
        return;
    }
    std::string message_body = message_json.dump();
    amqp_bytes_t message_bytes;
    message_bytes.len = message_body.length();
    message_bytes.bytes = (void*)message_body.c_str();
    amqp_basic_properties_t props;
    props._flags = AMQP_BASIC_DELIVERY_MODE_FLAG;
    props.delivery_mode = 2; // Persistent

    int status = amqp_basic_publish(rmq_conn_state_, 1, amqp_empty_bytes, amqp_cstring_bytes(queue_name.c_str()),
                                    0, 0, &props, message_bytes);
    if (status) {
        std::cerr << "GameTCPSession (" << username_ << "): Failed to publish to RabbitMQ queue '" << queue_name
                  << "': " << amqp_error_string2(status) << std::endl;
    }
    // else { std::cout << "GameTCPSession (" << username_ << "): Message published to RabbitMQ queue '" << queue_name << "'" << std::endl;} // Verbose
}
