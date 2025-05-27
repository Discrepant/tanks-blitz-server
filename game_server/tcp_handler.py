# game_server/tcp_handler.py
import asyncio
import json
import logging
from .game_logic import GameRoom, Player  # Убедитесь, что пути импорта верны
from core.message_broker_clients import publish_rabbitmq_message, \
    RABBITMQ_QUEUE_PLAYER_COMMANDS  # Убедитесь, что пути импорта верны

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
                logger.info(f"DEBUG: LOGIN_SUCCESS sent to {addr}. Player: {player.name if player else 'None'}")
            else:
                writer.write(f"LOGIN_FAILURE {auth_message}\n".encode())
                await writer.drain()
                logger.info(f"DEBUG: LOGIN_FAILURE sent to {addr}. Returning.")
                return
        elif command == 'REGISTER' and len(parts) == 3:
            writer.write("REGISTER_FAILURE Registration via game server is not yet supported.\n".encode())
            await writer.drain()
            logger.info(f"DEBUG: REGISTER_FAILURE sent to {addr}. Returning.")
            return
        else:
            writer.write("INVALID_COMMAND Expected: LOGIN username password or REGISTER username password\n".encode())
            await writer.drain()
            logger.info(f"DEBUG: INVALID_COMMAND (auth) sent to {addr}. Returning.")
            return

        logger.info(f"DEBUG: Authentication block passed. Player is {player.name if player else 'None'}.")

        if not player or not player.writer:
            logger.error(
                f"DEBUG: Player object not valid or writer missing for {addr}. Player: {player}, Player.writer: {player.writer if player else 'N/A'}. Returning.")
            if writer and not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            return

        logger.info(f"DEBUG: Player {player.name} authenticated. Entering command loop.")

        while True:
            logger.info(f"DEBUG: Top of command loop for {player.name}.")
            if player.writer.is_closing():
                logger.info(f"DEBUG: Player {player.name} writer is closing. Exiting loop.")
                break
            try:
                logger.info(f"DEBUG: Player {player.name} waiting for command...")
                data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=300.0)
                message_str = data.decode().strip()
                logger.info(f"DEBUG: Received from {player.name}: '{message_str}' (raw data: {data!r})")

                if not message_str:
                    logger.info(
                        f"DEBUG: Received empty message string from {player.name}, sending EMPTY_COMMAND response and continuing.")
                    writer.write(b"EMPTY_COMMAND\n")
                    await writer.drain()
                    continue

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
                    logger.info(f"DEBUG: Prepared 'shoot' command for {player.name}")
                elif cmd == "MOVE" and len(parts) == 3:
                    try:
                        x, y = int(parts[1]), int(parts[2])
                        command_data = {
                            "player_id": player.name,
                            "command": "move",
                            "details": {"new_position": [x, y], "source": "tcp_handler"}
                        }
                        logger.info(f"DEBUG: Prepared 'move' command for {player.name} to [{x},{y}]")
                    except ValueError:
                        logger.warning(f"DEBUG: Invalid MOVE parameters from {player.name}: {parts[1:]}")
                        response_message = "BAD_COMMAND_FORMAT Invalid MOVE parameters. Expected MOVE X Y (integers).\n"
                elif not cmd:
                    logger.warning(f"DEBUG: Empty command parsed for {player.name}")
                    response_message = "EMPTY_COMMAND\n"
                else:
                    logger.warning(f"DEBUG: Unknown command '{cmd}' from {player.name}. Full message: '{message_str}'")

                if command_data:
                    try:
                        publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                        logger.info(
                            f"DEBUG: Published command '{command_data['command']}' for player {player.name} to RabbitMQ.")
                        response_message = "COMMAND_ACKNOWLEDGED\n"
                    except Exception as e_pub:
                        logger.error(f"DEBUG: Failed to publish command for player {player.name} to RabbitMQ: {e_pub}",
                                     exc_info=True)
                        response_message = "ERROR_PROCESSING_COMMAND\n"

                logger.info(f"DEBUG: Player {player.name} attempting to send response: {response_message.strip()}")
                writer.write(response_message.encode())
                await writer.drain()
                logger.info(f"DEBUG: Player {player.name} response sent and drained.")

            except ConnectionResetError:
                logger.info(f"DEBUG: ConnectionResetError for {player.name} ({addr}). Exiting loop.")
                break
            except asyncio.IncompleteReadError:
                logger.info(f"DEBUG: IncompleteReadError for {player.name} ({addr}). Exiting loop.")
                break
            except asyncio.TimeoutError:
                logger.info(f"DEBUG: Timeout waiting for message from {player.name} ({addr}).")
                try:
                    if not writer.is_closing():
                        writer.write("SERVER: You have been disconnected due to inactivity.\n".encode())
                        await writer.drain()
                except Exception as e_send:
                    logger.error(f"DEBUG: Failed to send inactivity message to {player.name}: {e_send}")
                break
            except Exception as e:
                logger.error(f"DEBUG: Error processing command from {player.name} ({addr}): {e}", exc_info=True)
                try:
                    if not writer.is_closing():
                        writer.write(f"SERVER_ERROR: An error occurred: {type(e).__name__}\n".encode())
                        await writer.drain()
                except Exception as e_send:
                    logger.error(f"DEBUG: Failed to send server error message to {player.name}: {e_send}")
                break

    except Exception as e:
        logger.critical(f"DEBUG: Critical error in handle_game_client for {addr}: {e}", exc_info=True)
        if writer and not writer.is_closing():
            try:
                writer.write(f"CRITICAL_ERROR {type(e).__name__}\n".encode())
                await writer.drain()
            except Exception as we:
                logger.error(f"DEBUG: Failed to send critical error message to client {addr}: {we}")
    finally:
        if player:
            if asyncio.iscoroutinefunction(game_room.remove_player):
                await game_room.remove_player(player)
            else:
                game_room.remove_player(player)
            logger.info(f"DEBUG: Player {player.name} ({addr}) disconnected and removed from game room.")
        else:
            logger.info(f"DEBUG: Connection from {addr} closed (player not fully added or already removed).")

        if writer and not writer.is_closing():
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"DEBUG: Error during writer close for {addr}: {e_close}")
