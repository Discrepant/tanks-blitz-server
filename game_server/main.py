# game_server/main.py
import sys # Ensure sys is imported first if using sys.stderr
# print(f"[GAME_SERVER_MAIN_ULTRA_DEBUG] Process started. sys imported.", flush=True, file=sys.stderr) # Keep this commented for cleaner logs

import asyncio
import logging
import socket
import os
import tempfile # For setup_file_logging
import functools # For functools.partial in TCP server setup
import time # For any time-related operations if needed (though not directly in restored logic)
import threading # For potential metrics/consumer threads (though they are commented out)

# Local module imports for full functionality
from .udp_handler import GameUDPProtocol
from .tcp_handler import handle_game_client
from .game_logic import GameRoom
from .auth_client import AuthClient
from .session_manager import SessionManager
from .tank_pool import TankPool
from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE # Metrics might be used by commented out code
from prometheus_client import start_http_server # For commented out metrics server

# Global logger for this module, configured in __main__
# Note: logging.getLogger(__name__) should be called AFTER logging.basicConfig
# For now, we define it here, and basicConfig in __main__ will configure the root logger
# which this logger will inherit from.
logger = logging.getLogger(__name__)

INTEGRATION_TEST_LOG_FILE = os.path.join(tempfile.gettempdir(), "game_server_integration_test.log")

def setup_file_logging():
    """Sets up file logging for integration tests or general application logging."""
    try:
        # Clear previous log file with error handling
        try:
            if os.path.exists(INTEGRATION_TEST_LOG_FILE):
                os.remove(INTEGRATION_TEST_LOG_FILE)
        except (FileNotFoundError, PermissionError) as e:
            logger.warning(f"Could not remove old log file {INTEGRATION_TEST_LOG_FILE}: {e}")

        file_handler = logging.FileHandler(INTEGRATION_TEST_LOG_FILE)
        file_handler.setLevel(logging.DEBUG) # Capture all debug messages in the file
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s')
        file_handler.setFormatter(formatter)

        # Add handler to the root logger to capture logs from all modules
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        # Ensure root logger's level is also DEBUG if we want file_handler to process DEBUG messages
        if root_logger.getEffectiveLevel() > logging.DEBUG: # pragma: no cover (depends on initial config)
             root_logger.setLevel(logging.DEBUG)

        logger.info(f"File logging set up to {INTEGRATION_TEST_LOG_FILE}. Current root logger level: {logging.getLevelName(root_logger.getEffectiveLevel())}")
    except Exception as e:
        # Fallback to print if logger itself or file handling fails critically during setup
        sys.stderr.write(f"[GameServerMain] CRITICAL ERROR setting up file logging to {INTEGRATION_TEST_LOG_FILE}: {e}\n")
        # Also log via logging system if it's partially working
        logging.critical(f"CRITICAL ERROR setting up file logging to {INTEGRATION_TEST_LOG_FILE}: {e}", exc_info=True)

# Placeholder for metric functions (commented out, but structure preserved)
# def update_metrics():
#     pass
# def metrics_updater_loop():
#     pass
# def start_metrics_server():
#     pass

async def start_game_server(session_manager: SessionManager, tank_pool: TankPool):
    """
    Основная асинхронная функция для запуска UDP и TCP серверов игры.
    Настраивает обработчики, игровую комнату и клиент аутентификации.
    """
    loop = asyncio.get_running_loop()

    # UDP Server Setup
    udp_host = os.getenv('GAME_SERVER_UDP_HOST', '0.0.0.0') # Usually 0.0.0.0 for server
    udp_port_str = os.getenv("GAME_SERVER_UDP_PORT", "29998")
    try:
        udp_port = int(udp_port_str)
        logger.info(f"Game UDP server configured for {udp_host}:{udp_port} (from GAME_SERVER_UDP_PORT or default).")
    except ValueError:
        default_udp_port = 29998
        logger.warning(f"Invalid value for GAME_SERVER_UDP_PORT ('{udp_port_str}'). Using default UDP port {default_udp_port}.")
        udp_port = default_udp_port

    transport_udp = None # Initialize to ensure it's defined for finally block
    protocol_udp = None # Initialize protocol_udp as well

    max_retries = 5
    retry_delay = 2  # seconds
    udp_sock = None # Initialize udp_sock outside the try block for access in except/finally if needed

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries}: Creating and configuring UDP socket for {udp_host}:{udp_port}...")
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logger.info(f"Attempt {attempt + 1}/{max_retries}: SO_REUSEADDR set for UDP socket.")

            if sys.platform == "win32": # pragma: no cover
                try:
                    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    logger.info(f"Attempt {attempt + 1}/{max_retries}: Successfully set SO_EXCLUSIVEADDRUSE for UDP socket on Windows.")
                except OSError as e_exclusive:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries}: Failed to set SO_EXCLUSIVEADDRUSE for UDP socket on Windows: {e_exclusive}. Proceeding without it.")
            
            logger.info(f"Attempt {attempt + 1}/{max_retries}: Binding UDP socket to {udp_host}:{udp_port}...")
            udp_sock.bind((udp_host, udp_port))
            logger.info(f"Attempt {attempt + 1}/{max_retries}: UDP socket bound successfully to {udp_host}:{udp_port}.")

            logger.info(f"Attempt {attempt + 1}/{max_retries}: Creating datagram endpoint...")
            transport_udp, protocol_udp = await loop.create_datagram_endpoint(
                lambda: GameUDPProtocol(session_manager=session_manager, tank_pool=tank_pool),
                sock=udp_sock  # Use the pre-configured and bound socket
            )
            logger.info(f"Game UDP server started successfully on attempt {attempt + 1}/{max_retries}, listening on {transport_udp.get_extra_info('sockname')}.")
            break  # Exit loop on success

        except OSError as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to start UDP server on {udp_host}:{udp_port}: {e}")
            if udp_sock:
                udp_sock.close()
                logger.debug(f"Attempt {attempt + 1}/{max_retries}: Closed UDP socket after error.")
            
            if attempt == max_retries - 1:
                logger.critical(f"All {max_retries} attempts to start UDP server on {udp_host}:{udp_port} failed. Last error: {e}", exc_info=True)
                raise  # Re-raise the last exception
            else:
                logger.info(f"Retrying UDP server setup for {udp_host}:{udp_port} in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
        except Exception as e_general: # Catch any other unexpected error during setup
            logger.critical(f"Unexpected error during UDP setup attempt {attempt + 1}/{max_retries} for {udp_host}:{udp_port}: {e_general}", exc_info=True)
            if udp_sock:
                udp_sock.close() # Ensure socket is closed on other exceptions too
            raise # Re-raise to stop server startup

    if not transport_udp: # This check is more of a safeguard
        logger.critical(f"UDP server setup failed for {udp_host}:{udp_port} after all retries. Transport is None.") # pragma: no cover
        raise RuntimeError(f"UDP server could not be initialized for {udp_host}:{udp_port}.") # pragma: no cover

    # TCP Server and AuthClient Setup
    game_tcp_host = os.getenv('GAME_SERVER_TCP_HOST', '0.0.0.0')
    game_tcp_port_str = os.getenv('GAME_SERVER_TCP_PORT', '8889')
    try:
        game_tcp_port = int(game_tcp_port_str)
        logger.info(f"Game TCP server configured for {game_tcp_host}:{game_tcp_port} (from GAME_SERVER_TCP_PORT or default).")
    except ValueError:
        default_tcp_port = 8889
        logger.warning(f"Invalid value for GAME_SERVER_TCP_PORT ('{game_tcp_port_str}'). Using default TCP port {default_tcp_port}.")
        game_tcp_port = default_tcp_port

    auth_server_host = os.getenv('AUTH_SERVER_HOST', 'localhost')
    auth_server_port_str = os.getenv('AUTH_SERVER_PORT', "8888")
    try:
        auth_server_port = int(auth_server_port_str)
    except ValueError:
        default_auth_port = 8888
        logger.warning(f"Invalid value for AUTH_SERVER_PORT ('{auth_server_port_str}'). Using default Auth Server port {default_auth_port}.")
        auth_server_port = default_auth_port

    logger.info(f"AuthClient will connect to Auth Server at {auth_server_host}:{auth_server_port}.")

    tcp_server = None # Initialize to ensure it's defined for finally block
    try:
        logger.debug("Initializing AuthClient...")
        auth_client = AuthClient(auth_server_host=auth_server_host, auth_server_port=auth_server_port)
        logger.debug("AuthClient initialized.")

        logger.debug("Initializing GameRoom...")
        game_room = GameRoom(auth_client=auth_client)
        logger.debug("GameRoom initialized.")

        tcp_server_handler = functools.partial(handle_game_client, game_room=game_room)
        logger.debug(f"Attempting to start TCP server on {game_tcp_host}:{game_tcp_port}...")

        tcp_server = await asyncio.start_server(
            tcp_server_handler,
            game_tcp_host,
            game_tcp_port
        )
        logger.info(f"Game TCP server started successfully on {game_tcp_host}:{game_tcp_port}.")

    except OSError as e: # Catch OSError specifically for TCP server binding
        logger.critical(f"Could not start Game TCP server on {game_tcp_host}:{game_tcp_port}: {e}", exc_info=True)
        # This error will propagate to asyncio.run and be handled in __main__
        raise # Re-raise to stop server startup if TCP fails
    except Exception as e_setup: # Catch other setup errors (e.g. AuthClient, GameRoom init)
        logger.critical(f"Critical error during server setup (TCP/Auth/GameRoom): {e_setup}", exc_info=True)
        # This error will propagate to asyncio.run and be handled in __main__
        raise # Re-raise

    try:
        logger.info("Game server fully initialized. Waiting for termination signal...")
        await asyncio.Event().wait()
    finally:
        logger.info("Stopping game server components...")
        if tcp_server:
            tcp_server.close()
            await tcp_server.wait_closed()
            logger.info("Game TCP server stopped.")
        if transport_udp: # Use the specific variable name for UDP transport
            transport_udp.close()
            logger.info("Game UDP server stopped.")

if __name__ == '__main__':
    # Setup basic logging first
    # The format includes module name, function name, and line number for detailed debugging.
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(), # Default to INFO if not set
        format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
        stream=sys.stderr # Log to stderr by default
    )

    # Now that basicConfig is done, the module-level logger is configured.
    # Any print statements for ULTRA_DEBUG can be removed or kept for initial process start indication.
    # sys.stdout.write("[GAME_SERVER_MAIN_ULTRA_DEBUG] Process started. sys imported.\n") # Example of direct write
    # sys.stderr.write("Test stderr message\n") # For testing stderr capture

    # Optionally, set up file logging (useful for tests or persistent logs)
    # setup_file_logging() # Can be enabled if file logging is desired by default

    logger.info("Initializing game server application...")

    logger.debug("Initializing SessionManager...")
    session_manager = SessionManager()
    logger.debug("SessionManager initialized.")

    logger.debug("Initializing TankPool...")
    tank_pool = TankPool(pool_size=int(os.getenv("TANK_POOL_SIZE", 50)))
    logger.debug("TankPool initialized.")

    # Placeholder for starting metrics server (currently commented out)
    # try:
    #     logger.info("Attempting to start metrics server...")
    #     start_metrics_server() # This function would need to be defined or uncommented
    # except Exception as e_metrics:
    #     logger.error(f"Failed to start metrics server: {e_metrics}", exc_info=True)

    # Placeholder for starting RabbitMQ consumers (currently commented out)
    # try:
    #     logger.info("Attempting to start RabbitMQ consumers...")
    #     # ... (consumer starting logic) ...
    # except Exception as e_consumers:
    #     logger.error(f"Failed to start RabbitMQ consumers: {e_consumers}", exc_info=True)

    main_event_loop = None
    try:
        logger.info("Attempting to run main server logic: start_game_server.")
        # For Python 3.7+ asyncio.run is preferred
        main_event_loop = asyncio.get_event_loop() # Get loop for policies if needed before run
        if sys.platform == "win32" and sys.version_info >= (3, 8): # pragma: no cover
             # Required for Windows if ProactorEventLoop is default and UDP endpoints are used with it.
             # SelectorEventLoop is generally more compatible for some UDP/subprocess uses on Windows.
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
             logger.info("Windows OS detected: Applied WindowsSelectorEventLoopPolicy for asyncio.")

        asyncio.run(start_game_server(session_manager=session_manager, tank_pool=tank_pool))
    except KeyboardInterrupt:
        logger.info("Server shutdown requested via KeyboardInterrupt.")
        sys.stderr.write("Server shutdown requested via KeyboardInterrupt.\n")
    except OSError as e:
        logger.critical(f"CRITICAL: Failed to start server due to OSError (e.g., port binding issue): {e}", exc_info=True)
        sys.stderr.write(f"CRITICAL OSERROR: {e}\n")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"CRITICAL: Unhandled error in main execution block: {e}", exc_info=True)
        sys.stderr.write(f"CRITICAL ERROR: {e}\n")
        sys.exit(1)
    finally:
        logger.info("Game server application shutting down or has failed to start.")
        # Any other final cleanup if necessary

    # This print should ideally not be reached if server runs indefinitely via asyncio.Event().wait()
    # unless Event is set or an error occurs that bypasses sys.exit.
    logger.info("Game server application main block finished.")