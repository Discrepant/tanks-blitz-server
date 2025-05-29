# tests/unit/test_auth_service.py
# This file contains unit tests for the user authentication service
# (`auth_server.user_service.py`) using pytest.
import pytest # Import pytest for writing and running tests
from unittest.mock import patch # Import patch from unittest.mock for mocking objects
# Import the functions to be tested and MOCK_USERS_DB from the user_service module
from auth_server.user_service import authenticate_user, MOCK_USERS_DB, register_user

# pytest marks asynchronous test functions with @pytest.mark.asyncio,
# but if pytest-asyncio is used, it's enough to just declare the function as async def.
# Assuming pytest-asyncio is configured.

async def test_authenticate_user_success():
    """
    Test successful user authentication.
    Checks that the `authenticate_user` function correctly authenticates
    an existing user with the correct password.
    """
    # Using test users that should be in MOCK_USERS_DB.
    # If MOCK_USERS_DB is initialized on import, these users are already there.
    # Otherwise, they need to be added to MOCK_USERS_DB before the test or a mock should be used.
    test_username = "player1"
    test_password = "password123" # Assumed password for player1
    is_auth, message = await authenticate_user(test_username, test_password)
    assert is_auth is True, "Authentication should be successful for correct credentials."
    # The message from authenticate_user is already in English based on previous subtasks.
    assert "authenticated successfully" in message, "Message should confirm successful authentication."

async def test_authenticate_user_wrong_password():
    """
    Test user authentication with an incorrect password.
    Checks that `authenticate_user` does not authenticate a user
    if an incorrect password is provided.
    """
    test_username = "player1" # Existing user
    wrong_password = "wrongpassword" # Incorrect password
    is_auth, message = await authenticate_user(test_username, wrong_password)
    assert is_auth is False, "Authentication should not succeed with an incorrect password."
    assert "Incorrect password" in message, "Message should indicate incorrect password."

async def test_authenticate_user_not_found():
    """
    Test authentication of a non-existent user.
    Checks that `authenticate_user` does not authenticate a user
    that is not in the database (MOCK_USERS_DB).
    """
    unknown_username = "unknownuser" # Non-existent user
    test_password = "password123"
    is_auth, message = await authenticate_user(unknown_username, test_password)
    assert is_auth is False, "Authentication should not succeed for a non-existent user."
    assert "User not found" in message, "Message should indicate user not found."

async def test_register_user_success_mock():
    """
    Test successful registration of a new user.
    The `register_user` function (as per recent updates) now returns a dictionary.
    This test verifies the success case.
    """
    # Mock MOCK_USERS_DB for this specific test to isolate it
    # and not affect other tests that might rely on the initial state of MOCK_USERS_DB.
    # `clear=True` clears the dictionary before applying the patch.
    with patch.dict('auth_server.user_service.MOCK_USERS_DB', {}, clear=True):
        new_username = "newbie"
        new_password = "newpassword"
        # register_user now returns a dict like {"status": "success", "message": "..."}
        response = await register_user(new_username, new_password)
        assert response.get("status") == "success", "New user registration should be successful."
        assert "User registered successfully" in response.get("message", ""), "Message should confirm successful registration."
        # Verify that the user was actually added to the (mocked) DB
        assert new_username in MOCK_USERS_DB
        assert MOCK_USERS_DB[new_username] == new_password

async def test_register_user_already_exists_mock():
    """
    Test attempt to register a user that already exists.
    Checks that `register_user` returns an error if the username
    is already present in the system.
    """
    existing_username = "player1_for_register_test" # Use a unique name for this test
    # Ensure the user exists in MOCK_USERS_DB for this test.
    # Use patch.dict to temporarily modify MOCK_USERS_DB.
    with patch.dict('auth_server.user_service.MOCK_USERS_DB', {existing_username: "password123"}, clear=True):
        response = await register_user(existing_username, "anypass")
        assert response.get("status") == "error", "Registration of an existing user should fail."
        assert "Username already exists" in response.get("message", ""), "Message should indicate that the user already exists."
