#include "catch2/catch_all.hpp"
#include "../auth_server_cpp/auth_tcp_session.h" // Assuming this is the correct path
#include <boost/asio/io_context.hpp>
#include <grpcpp/create_channel.h> // For creating a real channel for testing

// Note: These tests are more like integration tests for process_json_request
// as they will attempt to connect to a real gRPC server expected at "localhost:50051".
// Ensure the Python gRPC Auth server (auth_server/auth_grpc_server.py) is running before these tests.

struct AuthTcpSessionTestFixture {
    boost::asio::io_context test_io_context; // Mock io_context
    std::shared_ptr<grpc::Channel> grpc_channel;
    boost::asio::ip::tcp::socket test_socket; // Mock socket for constructor
    std::shared_ptr<AuthTcpSession> session;

    AuthTcpSessionTestFixture() : test_socket(test_io_context) {
        std::string grpc_server_address = "localhost:50051";
        grpc_channel = grpc::CreateChannel(grpc_server_address, grpc::InsecureChannelCredentials());

        // Create a dummy socket. It won't actually be used for sending/receiving in these direct calls to process_json_request.
        // However, AuthTcpSession methods like send_response internally use socket_.async_write.
        // To truly test send_response, we'd need a connected socket or a mock.
        // For now, we focus on process_json_request's logic before it calls send_response.
        // If send_response is called, it might log errors if socket is not open/connected.

        // We need a way to capture what send_response would send.
        // One approach: modify AuthTcpSession to allow injecting a testable "sender" lambda/functor.
        // For this iteration, we'll call process_json_request and rely on gRPC call success/failure.
        // The actual content sent back to client is harder to capture without refactoring AuthTcpSession.

        // Create a dummy server endpoint for the socket to be "open" conceptually, though not connected.
        // boost::system::error_code ec;
        // tcp::acceptor acceptor(test_io_context, tcp::endpoint(tcp::v4(), 0)); // ephemeral port
        // acceptor.async_accept(test_socket, [](const boost::system::error_code&){});
        // test_io_context.run_one(); // Run once to complete accept
        // test_io_context.reset();

        // Simpler: just create the session. send_response might fail or log if socket not connected.
        session = std::make_shared<AuthTcpSession>(std::move(test_socket), grpc_channel);
    }

    ~AuthTcpSessionTestFixture() {
        // session->close_session("test_fixture_teardown"); // This would try to use the socket
        // test_io_context.run(); // To complete any async operations if session was started.
    }
};

TEST_CASE_METHOD(AuthTcpSessionTestFixture, "AuthTcpSession::process_json_request Tests", "[auth_tcp_session]") {

    INFO("Ensure Python gRPC Auth Server (auth_server/auth_grpc_server.py) is running on localhost:50051 for these tests.");

    SECTION("Valid Login Request - Successful Auth") {
        // Assumes user "testuser" with password "testpass" exists in Redis and gRPC server can auth it.
        // Or, if gRPC server has mock logic, e.g. "player1"/"pass1"
        nlohmann::json login_req = {
            {"action", "login"},
            {"username", "player1"},
            {"password", "pass1"}
        };
        // process_json_request calls send_response internally. We don't capture output here.
        // We check that it doesn't crash and that gRPC call (if it happens) is attempted.
        // If gRPC server is running, this should proceed. If not, gRPC error path will be taken.
        REQUIRE_NOTHROW(session->process_json_request(login_req.dump()));
        // To verify output, AuthTcpSession::send_response would need mocking/interception.
        // For now, this test mainly ensures the path executes and gRPC call is made.
        // Expected (if gRPC server responds with success):
        // send_response called with: {"status":"success","message":"User player1 authenticated.","token":"player1"}
    }

    SECTION("Valid Login Request - Failed Auth (Wrong Password)") {
        nlohmann::json login_req = {
            {"action", "login"},
            {"username", "player1"},
            {"password", "wrongpass"}
        };
        REQUIRE_NOTHROW(session->process_json_request(login_req.dump()));
        // Expected (if gRPC server responds with failure):
        // send_response called with: {"status":"failure","message":"Invalid credentials.","token":""}
    }

    SECTION("Valid Login Request - User Not Found") {
        nlohmann::json login_req = {
            {"action", "login"},
            {"username", "nosuchuser"},
            {"password", "anypass"}
        };
        REQUIRE_NOTHROW(session->process_json_request(login_req.dump()));
        // Expected (if gRPC server responds with failure):
        // send_response called with: {"status":"failure","message":"User not found.","token":""}
    }


    SECTION("Valid Register Request (Not Implemented by Python Server)") {
        nlohmann::json reg_req = {
            {"action", "register"},
            {"username", "newuser"},
            {"password", "newpass"}
        };
        REQUIRE_NOTHROW(session->process_json_request(reg_req.dump()));
        // Expected (based on Python gRPC server's RegisterUser):
        // send_response called with: {"status":"failure","message":"Registration is not implemented yet on this server.","token":""}
    }

    SECTION("Unknown Action") {
        nlohmann::json unknown_action_req = {
            {"action", "fly_to_moon"},
            {"username", "test"},
            {"password", "test"}
        };
        REQUIRE_NOTHROW(session->process_json_request(unknown_action_req.dump()));
        // Expected: send_response called with: {"status":"error","message":"Unknown action: fly_to_moon"}
    }

    SECTION("Missing Fields in JSON Request") {
        nlohmann::json missing_fields_req = {
            {"action", "login"},
            {"username", "test"}
            // password missing
        };
        REQUIRE_NOTHROW(session->process_json_request(missing_fields_req.dump()));
        // Expected: send_response called with: {"status":"error","message":"Request missing required fields..."}
    }

    SECTION("Invalid JSON String") {
        std::string invalid_json_str = "{action: login, username: test ..."; // Malformed
        REQUIRE_NOTHROW(session->process_json_request(invalid_json_str));
        // Expected: send_response called with: {"status":"error","message":"Invalid JSON request: ..."}
    }

    SECTION("gRPC Server Not Available") {
        // This test assumes the gRPC server at "localhost:50051" is NOT running.
        // Or, we can point to a known non-existent address.
        std::shared_ptr<grpc::Channel> dead_channel = grpc::CreateChannel(
            "localhost:1", grpc::InsecureChannelCredentials()
        );
        // Need to create a new session with this dead channel.
        // This highlights a limitation of the fixture if we can't easily swap the channel.
        // For now, this section is more of a manual test instruction.
        // If the main fixture's channel points to a non-running server, this path will be tested by other tests.

        // To properly test this in isolation:
        // boost::asio::ip::tcp::socket new_socket(test_io_context);
        // AuthTcpSession session_with_dead_channel(std::move(new_socket), dead_channel);
        // nlohmann::json login_req = { ... };
        // REQUIRE_NOTHROW(session_with_dead_channel.process_json_request(login_req.dump()));
        // Expected: send_response with gRPC connection error message.
        WARN("Test for 'gRPC Server Not Available' relies on gRPC server at localhost:50051 NOT running, or requires specific setup to use a dead_channel.");
    }
}
