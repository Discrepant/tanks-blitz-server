#include "catch2/catch_all.hpp"
#include "../game_server_cpp/tcp_session.h" // Тестируемый класс
#include "../game_server_cpp/session_manager.h"
#include "../game_server_cpp/tank_pool.h"
#include "../game_server_cpp/kafka_producer_handler.h" // Для инициализации SM и TP
#include <boost/asio/io_context.hpp>
#include <grpcpp/create_channel.h> // Для создания канала gRPC

// Статические инициализаторы для зависимостей (Singleton)
static KafkaProducerHandler gtcp_test_kafka_producer("localhost:29092"); // Фиктивный брокер для SM/TP
static TankPool* gtcp_test_tank_pool = TankPool::get_instance(5, &gtcp_test_kafka_producer);
static SessionManager* gtcp_test_session_manager = SessionManager::get_instance(gtcp_test_tank_pool, &gtcp_test_kafka_producer);

// Фиктивное состояние соединения AMQP для конструктора GameTCPSession
// В реальном тесте, включающем публикацию в RabbitMQ, это должно быть действительное соединение.
// Для тестирования разбора команд и вызовов gRPC это может быть nullptr, если метод publish обрабатывает это.
static amqp_connection_state_t gtcp_dummy_rmq_conn_state = nullptr;
// Если GameTCPSession::publish_to_rabbitmq_internal строго проверяет это, вызовы могут просто логировать ошибки.

struct GameTCPSessionTestFixture {
    boost::asio::io_context test_io_context;
    std::shared_ptr<grpc::Channel> grpc_auth_channel;
    boost::asio::ip::tcp::socket test_socket; // Фиктивный сокет
    std::shared_ptr<GameTCPSession> session;

    std::vector<std::string> sent_messages_capture; // Перехват "отправленных" сообщений

    GameTCPSessionTestFixture() : test_socket(test_io_context) {
        REQUIRE(gtcp_test_tank_pool != nullptr);
        REQUIRE(gtcp_test_session_manager != nullptr);

        std::string grpc_server_address = "localhost:50051"; // Python Auth gRPC сервер
        grpc_auth_channel = grpc::CreateChannel(grpc_server_address, grpc::InsecureChannelCredentials());

        // Очистка существующих сессий/игроков из предыдущих тестов
        auto all_sessions = gtcp_test_session_manager->get_all_sessions();
        for (const auto& s : all_sessions) {
            gtcp_test_session_manager->remove_session(s->get_id(), "gtcp_fixture_setup_cleanup");
        }

        session = std::make_shared<GameTCPSession>(
            std::move(test_socket), // Сокет перемещен, осторожно при повторном использовании test_socket
            gtcp_test_session_manager,
            gtcp_test_tank_pool,
            gtcp_dummy_rmq_conn_state,
            grpc_auth_channel
        );
        // Для тестирования вывода send_message потребуется рефакторинг GameTCPSession
        // для внедрения мок-отправителя или разрешения перехвата вывода.
        // Пока что мы вызываем process_command и проверяем наблюдаемые побочные эффекты или отсутствие сбоев.
    }

    ~GameTCPSessionTestFixture() {
        // Сессия может быть закрыта тестами команды QUIT.
        // if (session && session->socket().is_open()) { // socket() является приватным
        //    session->close_session("fixture_teardown");
        // }
    }

    // Вспомогательная функция, теперь часть фикстуры
    void perform_login(const std::string& user = "player1", const std::string& pass = "password123") {
        session->process_command("LOGIN " + user + " " + pass);
        // Предполагаем, что вход успешен для последующих тестов.
        // Здесь был бы хорош геттер session->is_authenticated().
    }
};

TEST_CASE_METHOD(GameTCPSessionTestFixture, "GameTCPSession::process_command Tests", "[game_tcp_session]") {

    INFO("Убедитесь, что Python gRPC Auth Server (auth_server/auth_grpc_server.py) запущен на localhost:50051 для тестов LOGIN.");

    SECTION("Process 'LOGIN' command - Successful") { // Обработка команды 'LOGIN' - Успешно
        // Предполагается, что пользователь "player1" с паролем "password123" действителен в Python gRPC Auth сервисе.
        REQUIRE_NOTHROW(session->process_command("LOGIN player1 password123"));
        // Ожидается: Несколько сообщений отправлено через send_message, подтверждающих вход, присоединение к игре, состояние танка.
        // Сложно проверить фактическое отправленное содержимое без перехвата send_message.
        // Проверка внутреннего состояния:
        // REQUIRE(session->is_authenticated()); // Нужен геттер для этих внутренних состояний
        // REQUIRE(session->get_username() == "player1");
        // Это потребует сделать username_ и authenticated_ публичными или добавить геттеры.
        // Пока что в основном тестируется отсутствие сбоев и путь взаимодействия с gRPC.
        // Если вход успешен, должен быть создан игрок и сессия.
        auto game_session = gtcp_test_session_manager->get_session_by_player_id("player1");
        REQUIRE(game_session != nullptr); // Проверяем, что игрок был добавлен в сессию
        REQUIRE(game_session->get_tank_for_player("player1") != nullptr); // Проверяем, что танк был назначен
        gtcp_test_session_manager->remove_player_from_any_session("player1"); // Очистка
    }

    SECTION("Process 'LOGIN' command - Failed (Wrong Password)") { // Обработка команды 'LOGIN' - Неудачно (Неверный пароль)
        REQUIRE_NOTHROW(session->process_command("LOGIN player1 wrongpass"));
        // Ожидается: Отправлено сообщение LOGIN_FAILED.
        // REQUIRE_FALSE(session->is_authenticated());
        auto game_session = gtcp_test_session_manager->get_session_by_player_id("player1");
        REQUIRE(game_session == nullptr); // Игрок не должен быть в сессии
    }

    SECTION("Commands before authentication") { // Команды до аутентификации
        REQUIRE_NOTHROW(session->process_command("MOVE 10 20"));
        // Ожидается: Отправлено сообщение UNAUTHORIZED.
        REQUIRE_NOTHROW(session->process_command("SHOOT"));
        // Ожидается: Отправлено сообщение UNAUTHORIZED.
        REQUIRE_NOTHROW(session->process_command("PLAYERS"));
        // Ожидается: Отправлено сообщение UNAUTHORIZED.
    }

    SECTION("Process 'MOVE' command - Authenticated") { // Обработка команды 'MOVE' - Аутентифицирован
        perform_login();
        // Нам нужно получить tank_id, который был назначен этому игроку во время входа
        auto game_session = gtcp_test_session_manager->get_session_by_player_id("player1");
        REQUIRE(game_session != nullptr);
        auto tank = game_session->get_tank_for_player("player1");
        REQUIRE(tank != nullptr);
        // tank->move({{"x",0},{"y",0}}); // Убедимся в известной начальной позиции, если позже проверяем эффект сообщения RMQ

        REQUIRE_NOTHROW(session->process_command("MOVE 15 25"));
        // Ожидается: COMMAND_RECEIVED MOVE, и сообщение опубликовано в RabbitMQ.
        // Состояние танка не изменяется напрямую GameTCPSession.
        // REQUIRE(tank->get_state()["position"]["x"] != 15); // Это верно, потребитель изменяет его.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'SHOOT' command - Authenticated") { // Обработка команды 'SHOOT' - Аутентифицирован
        perform_login();
        REQUIRE_NOTHROW(session->process_command("SHOOT"));
        // Ожидается: COMMAND_RECEIVED SHOOT, и сообщение опубликовано в RabbitMQ.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'SAY' command - Authenticated") { // Обработка команды 'SAY' - Аутентифицирован
        perform_login();
        REQUIRE_NOTHROW(session->process_command("SAY Hello there General Kenobi"));
        // Ожидается: "You said: ..." и сообщение опубликовано в очередь чата RabbitMQ.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'HELP' command") { // Обработка команды 'HELP'
        REQUIRE_NOTHROW(session->process_command("HELP")); // Тест неаутентифицированной помощи
        perform_login();
        REQUIRE_NOTHROW(session->process_command("HELP")); // Тест аутентифицированной помощи
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }

    SECTION("Process 'PLAYERS' command - Authenticated") { // Обработка команды 'PLAYERS' - Аутентифицирован
        perform_login("player_list_test", "pass1"); // Используем уникального игрока для этого теста
        REQUIRE_NOTHROW(session->process_command("PLAYERS"));
        // Ожидается: Список игроков в текущей сессии.
        gtcp_test_session_manager->remove_player_from_any_session("player_list_test");
    }

    SECTION("Process 'QUIT' command") { // Обработка команды 'QUIT'
        perform_login("player_quit_test", "pass1");
        REQUIRE_NOTHROW(session->process_command("QUIT"));
        // Ожидается: Сообщение GOODBYE. Сессия закрыта. Игрок удален из SessionManager.
        // Проверяем, был ли удален игрок
        REQUIRE(gtcp_test_session_manager->get_session_by_player_id("player_quit_test") == nullptr);
        // Сокет в shared_ptr сессии будет закрыт.
    }

    SECTION("Invalid command format / Unknown command") { // Неверный формат команды / Неизвестная команда
        perform_login(); // Некоторые команды требуют аутентификации, чтобы достичь стадии неизвестной команды
        REQUIRE_NOTHROW(session->process_command("FLAPDOODLE 1 2 3"));
        // Ожидается: Сообщение UNKNOWN_COMMAND.
        REQUIRE_NOTHROW(session->process_command("MOVE too many args here and there"));
        // Ожидается: MOVE_FAILED (или специфичная ошибка для количества аргументов). Текущая реализация может взять первые 2.
        // Текущий GameTCPSession::handle_move берет все аргументы после "MOVE" и пытается stoi(args[0]), stoi(args[1]).
        // Этот тест проверит, что он не падает.
        gtcp_test_session_manager->remove_player_from_any_session("player1");
    }
}
