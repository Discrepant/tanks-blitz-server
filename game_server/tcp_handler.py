import asyncio
import json  # Added import
import logging  # Added import
import time # Added import
from .game_logic import GameRoom, Player
from core.message_broker_clients import publish_rabbitmq_message, RABBITMQ_QUEUE_PLAYER_COMMANDS  # Убедитесь, что пути импорта верны
logger = logging.getLogger(__name__)


async def handle_game_client(reader, writer, game_room):
    addr = writer.get_extra_info('peername')
    player = None
    try:
        while True:
            data = await reader.readuntil(b'\n')
            message_str = data.decode().strip()
            if not message_str:
                logger.warning(f"Empty command string received from {addr}")
                writer.write("EMPTY_COMMAND\n".encode())
                await writer.drain()
                continue

            parts = message_str.split()
            if not parts:
                continue

            cmd = parts[0].upper()
            if cmd == 'LOGIN' and len(parts) == 3:
                username, password = parts[1], parts[2]
                # Call game_room.authenticate_player
                authenticated, auth_message, session_token = await game_room.authenticate_player(username, password)
                
                if authenticated:
                    # Create Player instance
                    # Assuming Player is imported correctly (e.g., from .models or .game_logic)
                    player_obj = Player(writer=writer, name=username, session_token=session_token)
                    # Add player object to game_room
                    await game_room.add_player(player_obj) 
                    player = player_obj # Assign to the handler's player variable
                    
                    # Send success response
                    writer.write(f"LOGIN_SUCCESS {auth_message} Token: {session_token if session_token else 'N/A'}\n".encode())
                    await writer.drain()
                    logger.info(f"Player {username} logged in from {addr}. Token: {session_token if session_token else 'N/A'}")
                else:
                    # Send failure response
                    writer.write(f"LOGIN_FAILURE {auth_message}\n".encode())
                    await writer.drain()
                    logger.info(f"Login failed for {username} from {addr}. Message: {auth_message}. Returning.")
                    return  # Terminate handler for this client
            elif cmd == 'REGISTER' and len(parts) == 3:
                writer.write("REGISTER_FAILURE Registration via game server is not yet supported.\n".encode())
                await writer.drain()
                logger.info(f"REGISTER_FAILURE sent to {addr}. Returning.")
                return
            elif cmd == 'MOVE' or cmd == 'SHOOT':
                if not player:
                    writer.write("UNAUTHORIZED You must login first\n".encode())
                    await writer.drain()
                    continue

                if cmd == 'MOVE':
                    if len(parts) < 3:
                        writer.write("MOVE_ERROR Missing coordinates\n".encode())
                        await writer.drain()
                        continue
                    try:
                        x = int(parts[1])
                        y = int(parts[2])
                        command_data = {
                            "player_id": player.name,
                            "command": "move",
                            "details": {"new_position": [x, y]}
                        }
                        await publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                    except ValueError:
                        writer.write("MOVE_ERROR Invalid coordinates\n".encode())
                        await writer.drain()
                        logger.error(f"Invalid coordinates for MOVE command from {player.name}: {parts[1:]}")
                        continue
                elif cmd == 'SHOOT':
                    command_data = {
                        "player_id": player.name,
                        "command": "shoot",
                        "details": {"source": "tcp_handler"}
                    }
                    await publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
            else:
                logger.warning(f"Unknown command '{cmd}' from {player.name if player else addr}. Full message: '{message_str}'")
                writer.write("UNKNOWN_COMMAND\n".encode())
                await writer.drain()

            logger.info(f"DEBUG: Player {player.name if player else addr} attempting to send response: {cmd.strip()}")
            writer.write(f"COMMAND_RECEIVED {cmd}\n".encode())
            await writer.drain()
            logger.info(f"DEBUG: Player {player.name if player else addr} response sent and drained.")

    except ConnectionResetError:
        logger.info(f"DEBUG: ConnectionResetError for {player.name if player else addr} ({addr}). Exiting loop.")
    except asyncio.IncompleteReadError:
        logger.info(f"Client {player.name if player else addr} ({addr}) closed connection (IncompleteReadError).")
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
            await game_room.remove_player(player)
        logger.info(f"Connection from {addr} closed (player not fully added or already removed).")
        if writer and not writer.is_closing():
            try:
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"Error during writer close for {addr}: {e_close}")