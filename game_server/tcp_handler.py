# game_server/tcp_handler.py
import asyncio
import json
import logging

# Убедитесь, что пути импорта соответствуют вашей структуре проекта
from .game_logic import GameRoom, Player
from core.message_broker_clients import publish_rabbitmq_message, RABBITMQ_QUEUE_PLAYER_COMMANDS

logger = logging.getLogger(__name__)


async def handle_game_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, game_room: GameRoom):
    addr = writer.get_extra_info('peername')
    logger.info(f"New game connection from {addr}")
    player = None

    try:
        intro_data = await reader.readuntil(b"\n")
        intro_message = intro_data.decode().strip()
        logger.info(f"Received for auth/register from {addr}: {intro_message}")

        parts = intro_message.split()
        command = parts[0].upper() if parts else ""

        if command == 'LOGIN' and len(parts) == 3:
            _, username, password = parts
            authenticated, auth_message, session_token = await game_room.authenticate_player(username, password)
            if authenticated:
                player = Player(writer, username, session_token)
                await game_room.add_player(player)
                writer.write(f"LOGIN_SUCCESS {auth_message} Token: {session_token}\n".encode())
                await writer.drain()
                logger.info(f"Player {player.name} successfully logged in from {addr}.")
            else:
                writer.write(f"LOGIN_FAILURE {auth_message}\n".encode())
                await writer.drain()
                logger.warning(f"Login failed for {username} from {addr}: {auth_message}")
                return
        elif command == 'REGISTER' and len(parts) == 3:
            writer.write("REGISTER_FAILURE Registration via game server is not yet supported.\n".encode())
            await writer.drain()
            logger.info(f"Registration attempt failed for {addr} (not supported).")
            return
        else:
            writer.write("INVALID_COMMAND Expected: LOGIN username password or REGISTER username password\n".encode())
            await writer.drain()
            logger.warning(f"Invalid initial command from {addr}: {intro_message}")
            return

        if not player or not player.writer:
            logger.error(f"Player object not created or writer missing after auth for {addr}. Player: {player}")
            if writer and not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            return

        logger.info(f"Player {player.name} authenticated. Entering command processing loop.")

        while True:
            if player.writer.is_closing():
                logger.info(f"Writer for player {player.name} is closing. Exiting command loop.")
                break
            try:
                data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=300.0)
                message_str = data.decode().strip()

                if not message_str:
                    logger.info(
                        f"Received empty message string from {player.name}. Sending EMPTY_COMMAND response and continuing.")
                    writer.write(b"EMPTY_COMMAND\n")
                    await writer.drain()
                    continue

                logger.info(f"Received from {player.name} ({addr}): '{message_str}'")

                parts = message_str.split()
                cmd = parts[0].upper() if parts else ""
                command_data = None
                response_message = "UNKNOWN_COMMAND\n"

                if cmd == "SHOOT":
                    command_data = {
                        "player_id": player.name,
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
                elif not cmd:
                    logger.warning(f"Empty command parsed for {player.name} (after split).")
                    response_message = "EMPTY_COMMAND\n"
                else:
                    logger.warning(f"Unknown command '{cmd}' from {player.name}. Full message: '{message_str}'")

                if command_data:
                    try:
                        publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                        logger.info(
                            f"Published command '{command_data['command']}' for player {player.name} to RabbitMQ.")
                        response_message = "COMMAND_ACKNOWLEDGED\n"
                    except Exception as e_pub:
                        logger.error(f"Failed to publish command for player {player.name} to RabbitMQ: {e_pub}",
                                     exc_info=True)
                        response_message = "ERROR_PROCESSING_COMMAND\n"

                if not writer.is_closing():
                    writer.write(response_message.encode())
                    await writer.drain()
                else:
                    logger.warning(
                        f"Writer for {player.name} was closing before sending response: {response_message.strip()}")
                    break

            except ConnectionResetError:
                logger.info(f"ConnectionResetError for {player.name} ({addr}). Exiting command loop.")
                break
            except asyncio.IncompleteReadError:
                logger.info(
                    f"IncompleteReadError for {player.name} ({addr}). Client closed connection. Exiting command loop.")
                break
            except asyncio.TimeoutError:
                logger.info(f"Timeout waiting for message from {player.name} ({addr}).")
                try:
                    if not writer.is_closing():
                        writer.write("SERVER: You have been disconnected due to inactivity.\n".encode())
                        await writer.drain()
                except Exception as e_send:
                    logger.error(f"Failed to send inactivity message to {player.name}: {e_send}")
                break
            except Exception as e:
                logger.error(f"Error processing command from {player.name} ({addr}): {e}", exc_info=True)
                try:
                    if not writer.is_closing():
                        writer.write(f"SERVER_ERROR: An error occurred: {type(e).__name__}\n".encode())
                        await writer.drain()
                except Exception as e_send:
                    logger.error(f"Failed to send server error message to {player.name}: {e_send}")
                break

    except Exception as e:
        logger.critical(f"Critical error in handle_game_client for {addr}: {e}", exc_info=True)
        if writer and not writer.is_closing():
            try:
                writer.write(f"CRITICAL_ERROR {type(e).__name__}\n".encode())
                await writer.drain()
            except Exception as we:
                logger.error(f"Failed to send critical error message to client {addr}: {we}")
    finally:
        if player:
            logger.info(f"Player {player.name} ({addr}) disconnecting.")
            try:
                if asyncio.iscoroutinefunction(game_room.remove_player):
                    await game_room.remove_player(player)
                else:
                    game_room.remove_player(player)
                logger.info(f"Player {player.name} removed from game room.")
            except Exception as e_remove:
                logger.error(f"Error removing player {player.name} from game room: {e_remove}", exc_info=True)
        else:
            logger.info(f"Connection from {addr} closed (player was not fully initialized or already removed).")

        if writer and not writer.is_closing():
            try:
                logger.info(f"Closing writer for {addr}.")
                writer.close()
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"Error during writer close for {addr}: {e_close}")
        else:
            logger.info(f"Writer for {addr} already closed or None.")
