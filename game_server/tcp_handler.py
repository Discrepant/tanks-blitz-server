import asyncio
import json # Added import
import logging # Added import
from .game_logic import GameRoom, Player
from core.message_broker_clients import publish_rabbitmq_message, RABBITMQ_QUEUE_PLAYER_COMMANDS # Added import

logger = logging.getLogger(__name__) # Added logger instance

async def handle_game_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, game_room: GameRoom):
    addr = writer.get_extra_info('peername')
    logger.info(f"New game connection from {addr}") # Changed print to logger.info
    player = None # Инициализируем player как None

    try:
        # Первый шаг - аутентификация или регистрация через игровой сервер
        # В реальном приложении это может быть сложнее, например, ожидание токена
        intro_data = await reader.readuntil(b"\n")
        intro_message = intro_data.decode().strip()
        logger.info(f"Received for auth/register from {addr}: {intro_message}") # Corrected indentation

        parts = intro_message.split()
        command = parts[0].upper()

        if command == 'LOGIN' and len(parts) == 3:
            _, username, password = parts
        # Assuming game_room.authenticate_player and add_player still handle session/tank assignment
            authenticated, auth_message, session_token = await game_room.authenticate_player(username, password)
            if authenticated:
                player = Player(writer, username, session_token) # player.name is username
                await game_room.add_player(player) # Associates player with game_room (and implicitly session/tank)
                writer.write(f"LOGIN_SUCCESS {auth_message} Token: {session_token}\n".encode())
                await writer.drain()
            else:
                writer.write(f"LOGIN_FAILURE {auth_message}\n".encode())
                await writer.drain()
                return
        elif command == 'REGISTER' and len(parts) == 3:
            # Placeholder for registration logic
            writer.write("REGISTER_FAILURE Registration via game server is not yet supported.\n".encode())
            await writer.drain()
            return
        else:
            writer.write("INVALID_COMMAND Expected: LOGIN username password or REGISTER username password\n".encode())
            await writer.drain()
            return

        if not player or not player.writer:
            logger.error(f"Error: Player object not created or writer missing for {addr}")
            return

        # Main command processing loop
        while True:
            if player.writer.is_closing():
                break
            try:
                data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=300.0)
                message_str = data.decode().strip()
                if not message_str:
                    logger.info(f"Received empty message from {player.name}, connection might be closing.")
                    break

                logger.info(f"Received from {player.name} ({addr}): '{message_str}'")

                parts = message_str.split()
            cmd = parts[0].upper() if parts else ""
            command_data = None
            response_message = "UNKNOWN_COMMAND\n" # Default response

            if cmd == "SHOOT":
                command_data = {
                    "player_id": player.name, # Using player.name as player_id
                    "command": "shoot",
                    "details": {"source": "tcp_handler"}
                }
                logger.debug(f"Prepared 'shoot' command for {player.name}")
            elif cmd == "MOVE" and len(parts) == 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                    command_data = {
                        "player_id": player.name,
                        "command": "move",
                        "details": {"new_position": [x, y], "source": "tcp_handler"}
                    }
                    logger.debug(f"Prepared 'move' command for {player.name} to [{x},{y}]")
                except ValueError:
                    logger.warning(f"Invalid MOVE parameters from {player.name}: {parts[1:]}")
                    response_message = "BAD_COMMAND_FORMAT Invalid MOVE parameters. Expected MOVE X Y (integers).\n"
            elif not cmd: # Empty command after stripping
                 logger.warning(f"Empty command string received from {player.name}")
                 response_message = "EMPTY_COMMAND\n"
            else:
                logger.warning(f"Unknown command '{cmd}' from {player.name}. Full message: '{message_str}'")
                # response_message is already "UNKNOWN_COMMAND\n"

            if command_data:
                try:
                    publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                    logger.info(f"Published command '{command_data['command']}' for player {player.name} to RabbitMQ.")
                    response_message = "COMMAND_ACKNOWLEDGED\n"
                except Exception as e:
                    logger.error(f"Failed to publish command for player {player.name} to RabbitMQ: {e}", exc_info=True)
                    response_message = "ERROR_PROCESSING_COMMAND\n"
            
            writer.write(response_message.encode())
            await writer.drain()

            except asyncio.TimeoutError:
            logger.info(f"Timeout waiting for message from {player.name} ({addr}).")
            # player.send_message is part of GameRoom logic, directly use writer here or adapt send_message
            try:
                writer.write("SERVER: You have been disconnected due to inactivity.\n".encode())
                await writer.drain()
            except Exception as e_send:
                 logger.error(f"Failed to send inactivity message to {player.name}: {e_send}")
                break
            except asyncio.IncompleteReadError:
            logger.info(f"Client {player.name} ({addr}) closed connection (IncompleteReadError).")
                break
            except ConnectionResetError:
            logger.info(f"Connection reset by client {player.name} ({addr}).")
                break
            except Exception as e:
            logger.error(f"Error processing command from {player.name} ({addr}): {e}", exc_info=True)
            try:
                writer.write(f"SERVER_ERROR: An error occurred: {type(e).__name__}\n".encode())
                await writer.drain()
            except Exception as e_send:
                 logger.error(f"Failed to send server error message to {player.name}: {e_send}")
            break # Break on general error to avoid error loops

    except Exception as e: # Catch-all for errors outside the loop (e.g., during auth)
        logger.critical(f"Critical error in handle_game_client for {addr}: {e}", exc_info=True)
        if writer and not writer.is_closing():
            try:
                writer.write(f"CRITICAL_ERROR {type(e).__name__}\n".encode())
                await writer.drain()
            except Exception as we:
                logger.error(f"Failed to send critical error message to client {addr}: {we}")
    finally:
        if player:
            # game_room.remove_player might do more than just remove, e.g., broadcast to others.
            # For now, assume it's necessary for cleanup.
            await game_room.remove_player(player)
            logger.info(f"Player {player.name} ({addr}) disconnected and removed from game room.")
        else:
            logger.info(f"Connection from {addr} closed (player not fully added or already removed).")

        if writer and not writer.is_closing():
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"Error during writer close for {addr}: {e_close}")
