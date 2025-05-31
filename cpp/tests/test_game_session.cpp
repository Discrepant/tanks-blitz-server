#include "catch2/catch_all.hpp"
#include "../game_server_cpp/game_session.h"
#include "../game_server_cpp/tank.h" // For creating Tank instances
#include "../game_server_cpp/kafka_producer_handler.h" // For Tank constructor

// Dummy KafkaProducerHandler for constructing Tanks in tests.
// Operations on this handler won't actually send to Kafka if broker isn't up.
static KafkaProducerHandler gs_test_kafka_producer_session("localhost:9099"); // Unique name for this test file's static

TEST_CASE("GameSession Recreated Class Tests", "[game_session_recreated]") {

    SECTION("GameSession Initialization") {
        GameSession session("session_init_rc_01");
        REQUIRE(session.get_id() == "session_init_rc_01");
        REQUIRE(session.get_players_count() == 0);
        REQUIRE(session.is_empty() == true);
        REQUIRE(session.get_tanks_state().is_array());
        REQUIRE(session.get_tanks_state().empty());
        REQUIRE(session.get_all_player_udp_addresses().empty());
        // Check default game info (example)
        REQUIRE(session.get_game_info()["map_name"] == "default_arena");
        REQUIRE(session.get_game_info()["status"] == "pending_players");
    }

    SECTION("GameSession Player Management") {
        GameSession session("session_pm_rc_01");
        auto tank1 = std::make_shared<Tank>("tank_gs_rc_01", &gs_test_kafka_producer_session);
        auto tank2 = std::make_shared<Tank>("tank_gs_rc_02", &gs_test_kafka_producer_session);

        // Add player 1 (UDP)
        REQUIRE(session.add_player("player1_rc", "192.168.0.1:1234", tank1, true));
        REQUIRE(session.get_players_count() == 1);
        REQUIRE_FALSE(session.is_empty());
        REQUIRE(session.has_player("player1_rc"));
        REQUIRE_FALSE(session.has_player("player_nonexistent_rc"));
        REQUIRE(session.get_tank_for_player("player1_rc") == tank1);
        PlayerInSessionData p1_data = session.get_player_data("player1_rc");
        REQUIRE(p1_data.address_info == "192.168.0.1:1234");
        REQUIRE(p1_data.is_udp_player == true);
        REQUIRE(p1_data.tank == tank1);


        // Add player 2 (TCP)
        REQUIRE(session.add_player("player2_rc", "tcp_user_rc_2", tank2, false));
        REQUIRE(session.get_players_count() == 2);
        REQUIRE(session.has_player("player2_rc"));
        REQUIRE(session.get_tank_for_player("player2_rc") == tank2);
        PlayerInSessionData p2_data = session.get_player_data("player2_rc");
        REQUIRE(p2_data.address_info == "tcp_user_rc_2");
        REQUIRE(p2_data.is_udp_player == false);

        // Try adding existing player ID again
        auto tank_dup = std::make_shared<Tank>("tank_gs_rc_dup", &gs_test_kafka_producer_session);
        REQUIRE_FALSE(session.add_player("player1_rc", "1.2.3.4:5000", tank_dup, true));
        REQUIRE(session.get_players_count() == 2); // Count should not change

        // Try adding player with null tank
        REQUIRE_FALSE(session.add_player("player_null_tank_rc", "2.3.4.5:6000", nullptr, true));
        REQUIRE(session.get_players_count() == 2);


        // Remove player 1
        REQUIRE(session.remove_player("player1_rc"));
        REQUIRE(session.get_players_count() == 1);
        REQUIRE_FALSE(session.has_player("player1_rc"));
        REQUIRE(session.get_tank_for_player("player1_rc") == nullptr);

        // Remove non-existent player
        REQUIRE_FALSE(session.remove_player("player_nonexistent_rc"));
        REQUIRE(session.get_players_count() == 1);

        // Remove player 2
        REQUIRE(session.remove_player("player2_rc"));
        REQUIRE(session.get_players_count() == 0);
        REQUIRE(session.is_empty());
        REQUIRE_FALSE(session.has_player("player2_rc"));
    }

    SECTION("GameSession Get Tanks State") {
        GameSession session("session_tanks_rc_01");
        REQUIRE(session.get_tanks_state().is_array());
        REQUIRE(session.get_tanks_state().empty());

        auto tank1_rc = std::make_shared<Tank>("tank_gs_rc_s1", &gs_test_kafka_producer_session, {{"x",1},{"y",1}}, 100);
        tank1_rc->set_active(true);
        session.add_player("playerA_rc", "addrA_rc", tank1_rc, true);

        auto tank2_rc = std::make_shared<Tank>("tank_gs_rc_s2", &gs_test_kafka_producer_session, {{"x",2},{"y",2}}, 90);
        tank2_rc->set_active(true);
        session.add_player("playerB_rc", "addrB_rc", tank2_rc, true);

        nlohmann::json states = session.get_tanks_state();
        REQUIRE(states.is_array());
        REQUIRE(states.size() == 2);

        bool found_tank1 = false;
        bool found_tank2 = false;
        for (const auto& state : states) {
            if (state["id"] == "tank_gs_rc_s1") {
                found_tank1 = true;
                REQUIRE(state["position"]["x"] == 1);
                REQUIRE(state["health"] == 100);
            } else if (state["id"] == "tank_gs_rc_s2") {
                found_tank2 = true;
                REQUIRE(state["position"]["y"] == 2);
                REQUIRE(state["health"] == 90);
            }
        }
        REQUIRE(found_tank1);
        REQUIRE(found_tank2);

        session.remove_player("playerA_rc");
        states = session.get_tanks_state();
        REQUIRE(states.size() == 1);
        REQUIRE(states[0]["id"] == "tank_gs_rc_s2");
    }

    SECTION("GameSession Get All Player UDP Addresses") {
        GameSession session("session_udp_addr_rc_01");
        REQUIRE(session.get_all_player_udp_addresses().empty());

        auto tank_u1 = std::make_shared<Tank>("t_rc_udp1", &gs_test_kafka_producer_session);
        session.add_player("p_rc_udp1", "10.0.0.1:1111", tank_u1, true);

        auto tank_t1 = std::make_shared<Tank>("t_rc_tcp1", &gs_test_kafka_producer_session);
        session.add_player("p_rc_tcp1", "tcp_user_name_rc", tank_t1, false);

        auto tank_u2 = std::make_shared<Tank>("t_rc_udp2", &gs_test_kafka_producer_session);
        session.add_player("p_rc_udp2", "10.0.0.2:2222", tank_u2, true);

        std::vector<std::string> addresses = session.get_all_player_udp_addresses();
        REQUIRE(addresses.size() == 2);
        REQUIRE(std::find(addresses.begin(), addresses.end(), "10.0.0.1:1111") != addresses.end());
        REQUIRE(std::find(addresses.begin(), addresses.end(), "10.0.0.2:2222") != addresses.end());

        session.remove_player("p_rc_udp1");
        addresses = session.get_all_player_udp_addresses();
        REQUIRE(addresses.size() == 1);
        REQUIRE(addresses[0] == "10.0.0.2:2222"); // Assuming order is preserved or only one left
    }

    SECTION("Get Player Data for non-existent player") {
        GameSession session("session_getdata_rc_01");
        PlayerInSessionData data = session.get_player_data("non_existent_player_rc");
        REQUIRE(data.tank == nullptr);
        REQUIRE(data.address_info.empty());
        REQUIRE(data.is_udp_player == false); // Default for struct
    }
}
