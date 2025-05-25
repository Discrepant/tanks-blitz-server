# This file makes the auth_server directory a Python package.
# It can be left empty or can contain package-level initializations.

from .main import main as auth_main
from .tcp_handler import handle_auth_client
from .user_service import authenticate_user, register_user
