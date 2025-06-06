import asyncio
import grpc
from concurrent import futures
import logging

# Assuming protos are in ./protos and generated files are in ./grpc_generated relative to this script's execution path
# Adjust sys.path if necessary, or structure as a proper package
# import sys # No longer needed for this
# import os # No longer needed for this
# Add the parent directory of 'auth_server' to sys.path to allow sibling imports if 'protos' is outside 'auth_server'
# For example, if 'protos' and 'auth_server' are siblings in a root directory.
# This also helps find 'grpc_generated' if it's a sub-package of 'auth_server'.
# sys.path.append(os.path.join(os.path.dirname(__file__), 'grpc_generated')) # Removed
# sys.path.append(os.path.dirname(os.path.abspath(__file__))) # Add auth_server itself for user_service # Removed

# Use fully qualified imports assuming 'auth_server' is the top-level package visible in PYTHONPATH
from auth_server.grpc_generated import auth_service_pb2
from auth_server.grpc_generated import auth_service_pb2_grpc
from auth_server.user_service import UserService
from passlib.hash import pbkdf2_sha256 # Moved import to top level

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AuthServiceServicer(auth_service_pb2_grpc.AuthServiceServicer):
    def __init__(self, user_svc_instance):
        self.user_service = user_svc_instance
        logging.info("AuthServiceServicer initialized.")

    async def AuthenticateUser(self, request, context):
        logging.info(f"AuthenticateUser called for username: {request.username}")
        authenticated, message = await self.user_service.authenticate_user(request.username, request.password)
        token = ""
        if authenticated:
            token = request.username # Using username as token for now
            logging.info(f"User {request.username} authenticated successfully. Token: {token}")
        else:
            logging.warning(f"Authentication failed for user {request.username}: {message}")

        return auth_service_pb2.AuthResponse(
            authenticated=authenticated,
            message=message,
            token=token
        )

    async def RegisterUser(self, request, context):
        logging.info(f"RegisterUser called for username: {request.username}")
        # For now, registration is not fully implemented with user_service,
        # so we return a mock success or "not implemented".
        # Let's try to use the user_service.create_user if it matches the required flow.
        # user_service.create_user is async and takes (username, password_hash)
        # We'd need to hash the password here. For simplicity, let's mock it as not implemented.

        # If you wanted to implement it:
        # from passlib.hash import pbkdf2_sha256 # Removed from here, moved to top
        password_hash = pbkdf2_sha256.hash(request.password) # pbkdf2_sha256 is now from module globals
        success, message = await self.user_service.create_user(request.username, password_hash)
        if success:
            logging.info(f"User {request.username} registered successfully.")
            return auth_service_pb2.AuthResponse(authenticated=False, message="Registration successful. Please login.", token="")
        else:
            logging.warning(f"Registration failed for user {request.username}: {message}")
            return auth_service_pb2.AuthResponse(authenticated=False, message=f"Registration failed: {message}", token="")

        # message = "Registration is not implemented yet on this server."
        # logging.info(message)
        # return auth_service_pb2.AuthResponse(
        #     authenticated=False,
        #     message=message,
        #     token=""
        # )

async def serve():
    # Initialize Redis client (and potentially other services user_service depends on)
    # Assuming user_service has an async initialize method or can be initialized beforehand.
    # For this example, let's assume UserService can be instantiated directly
    # and its Redis dependency is handled within its methods or upon its instantiation.

    # Check if initialize_redis_client is async or sync in user_service.py
    # It is synchronous.
    UserService.initialize_redis_client() # Call class method to setup Redis

    user_svc_instance = UserService() # Instantiate UserService

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_service_pb2_grpc.add_AuthServiceServicer_to_server(
        AuthServiceServicer(user_svc_instance), server
    )

    port = "50051"
    server.add_insecure_port(f'[::]:{port}')
    logging.info(f"gRPC Auth Server starting on port {port}...")
    await server.start()
    logging.info(f"gRPC Auth Server started successfully on port {port}.")
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logging.info("gRPC Auth Server stopping...")
        await server.stop(0)
        logging.info("gRPC Auth Server stopped.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
