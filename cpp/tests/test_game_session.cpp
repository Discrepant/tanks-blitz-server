#include "catch2/catch_all.hpp"
#include "../game_server_cpp/game_session.h"
#include "../game_server_cpp/tank.h" // For creating Tank instances
#include "../game_server_cpp/kafka_producer_handler.h" // For Tank constructor

// Dummy KafkaProducerHandler for constructing Tanks in tests.
// Operations on this handler won't actually send to Kafka if broker isn't up.
static KafkaProducerHandler gs_test_kafka_producer("localhost:9099");

TEST_CASE("GameSession Class Tests", "[game_session]") {

    SECTION("GameSession Initialization") {
        GameSession session("session_init_01");
        REQUIRE(session.get_id() == "session_init_01");
        REQUIRE(session.get_players_count() == 0);
        REQUIRE(session.is_empty() == true);
        REQUIRE(session.get_tanks_state().is_array());
        REQUIRE(session.get_tanks_state().empty());
        REQUIRE(session.get_all_player_udp_addresses().empty());
        // Check default game state info (example)
        REQUIRE(session.get_game_state_info()["map_name"] == "default_arena");
    }

    SECTION("GameSession Player Management") {
        GameSession session("session_pm_01");
        auto tank1 = std::make_shared<Tank>("tank_gs_01", &gs_test_kafka_producer);
        auto tank2 = std::make_shared<Tank>("tank_gs_02", &gs_test_kafka_producer);

        // Add player 1 (UDP)
        REQUIRE(session.add_player("player1", "192.168.0.1:1234", tank1, true));
        REQUIRE(session.get_players_count() == 1);
        REQUIRE_FALSE(session.is_empty());
        REQUIRE(session.has_player("player1"));
        REQUIRE_FALSE(session.has_player("player_nonexistent"));
        REQUIRE(session.get_tank_for_player("player1") == tank1);
        REQUIRE(session.get_player_data("player1").udp_address == "192.168.0.1:1234");
        REQUIRE(session.get_player_data("player1").tcp_username.empty());


        // Add player 2 (TCP)
        REQUIRE(session.add_player("player2", "tcp_user_2", tank2, false));
        REQUIRE(session.get_players_count() == 2);
        REQUIRE(session.has_player("player2"));
        REQUIRE(session.get_tank_for_player("player2") == tank2);
        REQUIRE(session.get_player_data("player2").tcp_username == "tcp_user_2");
        REQUIRE(session.get_player_data("player2").udp_address.empty());

        // Try adding existing player ID again
        auto tank_dup = std::make_shared<Tank>("tank_gs_dup", &gs_test_kafka_producer);
        REQUIRE_FALSE(session.add_player("player1", "1.2.3.4:5000", tank_dup, true));
        REQUIRE(session.get_players_count() == 2); // Count should not change

        // Try adding player with null tank
        REQUIRE_FALSE(session.add_player("player_null_tank", "2.3.4.5:6000", nullptr, true));
        REQUIRE(session.get_players_count() == 2);


        // Remove player 1
        REQUIRE(session.remove_player("player1"));
        REQUIRE(session.get_players_count() == 1);
        REQUIRE_FALSE(session.has_player("player1"));
        REQUIRE(session.get_tank_for_player("player1") == nullptr);

        // Remove non-existent player
        REQUIRE_FALSE(session.remove_player("player_nonexistent"));
        REQUIRE(session.get_players_count() == 1);

        // Remove player 2
        REQUIRE(session.remove_player("player2"));
        REQUIRE(session.get_players_count() == 0);
        REQUIRE(session.is_empty());
        REQUIRE_FALSE(session.has_player("player2"));
    }

    SECTION("GameSession Get Tanks State") {
        GameSession session("session_tanks_01");
        REQUIRE(session.get_tanks_state().is_array());
        REQUIRE(session.get_tanks_state().empty());

        auto tank1 = std::make_shared<Tank>("tank_gs_s1", &gs_test_kafka_producer, {{"x",1},{"y",1}}, 100);
        tank1->set_active(true);
        session.add_player("playerA", "addrA", tank1);

        auto tank2 = std::make_shared<Tank>("tank_gs_s2", &gs_test_kafka_producer, {{"x",2},{"y",2}}, 90);
        tank2->set_active(true);
        session.add_player("playerB", "addrB", tank2);

        nlohmann::json states = session.get_tanks_state();
        REQUIRE(states.is_array());
        REQUIRE(states.size() == 2);

        bool found_tank1 = false;
        bool found_tank2 = false;
        for (const auto& state : states) {
            if (state["id"] == "tank_gs_s1") {
                found_tank1 = true;
                REQUIRE(state["position"]["x"] == 1);
                REQUIRE(state["health"] == 100);
            } else if (state["id"] == "tank_gs_s2") {
                found_tank2 = true;
                REQUIRE(state["position"]["y"] == 2);
                REQUIRE(state["health"] == 90);
            }
        }
        REQUIRE(found_tank1);
        REQUIRE(found_tank2);

        session.remove_player("playerA");
        states = session.get_tanks_state();
        REQUIRE(states.size() == 1);
        REQUIRE(states[0]["id"] == "tank_gs_s2");
    }

    SECTION("GameSession Get All Player UDP Addresses") {
        GameSession session("session_udp_addr_01");
        REQUIRE(session.get_all_player_udp_addresses().empty());

        auto tank1 = std::make_shared<Tank>("t_udp1", &gs_test_kafka_producer);
        session.add_player("p_udp1", "10.0.0.1:1111", tank1, true); // is_udp_player = true

        auto tank2 = std::make_shared<Tank>("t_tcp1", &gs_test_kafka_producer);
        session.add_player("p_tcp1", "tcp_user_name", tank2, false); // is_udp_player = false

        auto tank3 = std::make_shared<Tank>("t_udp2", &gs_test_kafka_producer);
        session.add_player("p_udp2", "10.0.0.2:2222", tank3, true);

        std::vector<std::string> addresses = session.get_all_player_udp_addresses();
        REQUIRE(addresses.size() == 2);
        // Order is not guaranteed by std::map iteration, so check for presence
        REQUIRE(std::find(addresses.begin(), addresses.end(), "10.0.0.1:1111") != addresses.end());
        REQUIRE(std::find(addresses.begin(), addresses.end(), "10.0.0.2:2222") != addresses.end());

        session.remove_player("p_udp1");
        addresses = session.get_all_player_udp_addresses();
        REQUIRE(addresses.size() == 1);
        REQUIRE(addresses[0] == "10.0.0.2:2222");
    }

    SECTION("Get Player Data for non-existent player") {
        GameSession session("session_getdata_01");
        PlayerInSessionData data = session.get_player_data("non_existent_player");
        REQUIRE(data.tank == nullptr); // Tank should be null for a non-existent player
        REQUIRE(data.udp_address.empty());
        REQUIRE(data.tcp_username.empty());
    }
}
