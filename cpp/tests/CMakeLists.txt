cmake_minimum_required(VERSION 3.28)
cmake_policy(SET CMP0167 NEW)

if(DEFINED VCPKG_TARGET_TRIPLET AND VCPKG_TARGET_TRIPLET)
    set(MY_USING_VCPKG TRUE)
    message(STATUS "Tests: MY_USING_VCPKG set to TRUE (VCPKG_TARGET_TRIPLET is '${VCPKG_TARGET_TRIPLET}')")
else()
    set(MY_USING_VCPKG FALSE)
    message(STATUS "Tests: MY_USING_VCPKG set to FALSE (VCPKG_TARGET_TRIPLET is not defined or empty)")
endif()

project(GameLogicTests CXX)

set(RabbitMQ_LINK_TARGET "") # Инициализация переменной

# CMAKE_CXX_STANDARD наследуется из корневого CMakeLists.txt
# find_package(PkgConfig REQUIRED) # Больше не вызываем pkg_check_modules здесь напрямую

# Поиск основных зависимостей, также необходимых для тестов
#cmake_policy(SET CMP0167 NEW)
find_package(Boost 1.71.0 REQUIRED COMPONENTS system) # Предполагаем, что system нужен, добавьте другие при необходимости
find_package(nlohmann_json 3 REQUIRED) # Или любая ожидаемая версия

# Поиск RabbitMQ-C (предоставляется librabbitmq)
if(MY_USING_VCPKG)
  find_package(rabbitmq-c CONFIG REQUIRED) # Имя пакета rabbitmq-c, как подсказано vcpkg для librabbitmq
  # Нет необходимости проверять rabbitmq-c_FOUND из-за REQUIRED. Если не найден, CMake остановится.
  message(STATUS "Tests: Found rabbitmq-c package (likely provided by librabbitmq).") # Тесты: Найден пакет rabbitmq-c (вероятно, предоставлен librabbitmq).
  if(NOT TARGET rabbitmq::rabbitmq) # Проверка фактического имени цели
    message(FATAL_ERROR "Tests: Target rabbitmq::rabbitmq not found after finding rabbitmq-c package.") # Тесты: Цель rabbitmq::rabbitmq не найдена после нахождения пакета rabbitmq-c.
  else()
    message(STATUS "Tests: Successfully found target rabbitmq::rabbitmq.") # Тесты: Успешно найдена цель rabbitmq::rabbitmq.
    set(RabbitMQ_LINK_TARGET rabbitmq::rabbitmq)
  endif()
else()
  # Логика для RabbitMQ-C не через vcpkg
  message(STATUS "Tests: Not using vcpkg. Attempting find_package/pkg-config for RabbitMQ-C.") # Тесты: vcpkg не используется. Попытка find_package/pkg-config для RabbitMQ-C.
  find_package(RabbitMQC QUIET) # Сначала пытаемся найти старое имя пакета
  if(RabbitMQC_FOUND AND TARGET RabbitMQC::rabbitmq-c)
      message(STATUS "Tests: Found RabbitMQ-C using find_package(RabbitMQC). Using target RabbitMQC::rabbitmq-c.") # Тесты: Найден RabbitMQ-C с использованием find_package(RabbitMQC). Используется цель RabbitMQC::rabbitmq-c.
      set(RabbitMQ_LINK_TARGET RabbitMQC::rabbitmq-c)
  else()
      message(STATUS "Tests: RabbitMQC::rabbitmq-c not found via find_package(RabbitMQC). Attempting pkg-config for librabbitmq.") # Тесты: RabbitMQC::rabbitmq-c не найден через find_package(RabbitMQC). Попытка pkg-config для librabbitmq.
      find_package(PkgConfig QUIET)
      if(NOT PKG_CONFIG_FOUND)
          message(FATAL_ERROR "Tests: PkgConfig not found, cannot use it for RabbitMQ-C.") # Тесты: PkgConfig не найден, невозможно использовать его для RabbitMQ-C.
      endif()
      pkg_check_modules(PC_LIBRABBITMQ QUIET librabbitmq) # Поиск librabbitmq
      if(PC_LIBRABBITMQ_FOUND)
          message(STATUS "Tests: Found librabbitmq via pkg-config. Version: ${PC_LIBRABBITMQ_VERSION}") # Тесты: Найден librabbitmq через pkg-config. Версия: ...
          if(NOT TARGET RabbitMQC::rabbitmq-c) # Создаем, если еще не существует
              add_library(RabbitMQC::rabbitmq-c INTERFACE IMPORTED GLOBAL)
              target_include_directories(RabbitMQC::rabbitmq-c INTERFACE /usr/include) # Устанавливаем явно
              target_link_libraries(RabbitMQC::rabbitmq-c INTERFACE ${PC_LIBRABBITMQ_LIBRARIES})
              message(STATUS "Tests: Created GLOBAL IMPORTED target RabbitMQC::rabbitmq-c from pkg-config for librabbitmq (include dir forced to /usr/include).") # Тесты: Создана GLOBAL IMPORTED цель RabbitMQC::rabbitmq-c из pkg-config для librabbitmq (каталог include принудительно /usr/include).
          endif()
          set(RabbitMQ_LINK_TARGET RabbitMQC::rabbitmq-c)
      else()
          message(FATAL_ERROR "Tests: librabbitmq not found via pkg-config.") # Тесты: librabbitmq не найден через pkg-config.
      endif()
  endif()

  if(NOT RabbitMQ_LINK_TARGET) # Проверяем, что цель была установлена
      message(FATAL_ERROR "Tests: Failed to establish RabbitMQ-C target for non-vcpkg build.") # Тесты: Не удалось установить цель RabbitMQ-C для сборки не через vcpkg.
  endif()
endif()

# Поиск RdKafka
if(MY_USING_VCPKG)
  find_package(RdKafka CONFIG QUIET) # vcpkg должен предоставить это
  if(NOT RdKafka_FOUND)
    message(FATAL_ERROR "Tests: RdKafka package not found via vcpkg.") # Тесты: Пакет RdKafka не найден через vcpkg.
  else()
    message(STATUS "Tests: Found RdKafka package.") # Тесты: Найден пакет RdKafka.
    if(NOT TARGET RdKafka::rdkafka++)
      message(FATAL_ERROR "Tests: Target RdKafka::rdkafka++ not found after finding RdKafka package.") # Тесты: Цель RdKafka::rdkafka++ не найдена после нахождения пакета RdKafka.
    else()
      message(STATUS "Tests: Successfully found target RdKafka::rdkafka++.") # Тесты: Успешно найдена цель RdKafka::rdkafka++.
    endif()
  endif()
else()
  # Логика из game_server_cpp/CMakeLists.txt для RdKafka не через vcpkg
  message(STATUS "Tests: Not using vcpkg. Attempting find_package/pkg-config for RdKafka.") # Тесты: vcpkg не используется. Попытка find_package/pkg-config для RdKafka.
  find_package(PkgConfig QUIET) # Сначала убедимся, что PkgConfig найден
  if(NOT PKG_CONFIG_FOUND)
    message(FATAL_ERROR "Tests: PkgConfig not found, cannot use it for RdKafka.") # Тесты: PkgConfig не найден, невозможно использовать его для RdKafka.
  endif()
  pkg_check_modules(PC_RdKafkaCpp QUIET rdkafka++) # Получаем переменные
  if(PC_RdKafkaCpp_FOUND)
    message(STATUS "Tests: Found RdKafka (rdkafka++) via pkg-config. Version: ${PC_RdKafkaCpp_VERSION}") # Тесты: Найден RdKafka (rdkafka++) через pkg-config. Версия: ...
    if(NOT TARGET RdKafka::rdkafka++)
        add_library(RdKafka::rdkafka++ INTERFACE IMPORTED GLOBAL)
        target_include_directories(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_INCLUDE_DIRS})
        target_link_libraries(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_LIBRARIES})
        message(STATUS "Tests: Created GLOBAL IMPORTED target RdKafka::rdkafka++ from pkg-config.") # Тесты: Создана GLOBAL IMPORTED цель RdKafka::rdkafka++ из pkg-config.
    endif()
    set(RdKafka_FOUND TRUE) # Сигнализируем, что найдено
  else()
    message(FATAL_ERROR "Tests: RdKafka (rdkafka++) not found via pkg-config.") # Тесты: RdKafka (rdkafka++) не найден через pkg-config.
  endif()
  if(NOT RdKafka_FOUND OR NOT TARGET RdKafka::rdkafka++) # Двойная проверка
    message(FATAL_ERROR "Tests: Failed to find RdKafka C++ library (rdkafka++) for non-vcpkg build.") # Тесты: Не удалось найти библиотеку RdKafka C++ (rdkafka++) для сборки не через vcpkg.
  endif()
endif()

find_package(Threads REQUIRED)

# Protobuf и gRPC (даже если связаны через библиотеку, их поиск гарантирует доступность целей)
# Ожидаем, что они будут найдены из /usr/local, так как мы собрали их из исходников
# find_package(Protobuf CONFIG REQUIRED) # Должен быть найден верхнеуровневым CMakeLists.txt или gRPC
find_package(gRPC CONFIG REQUIRED COMPONENTS grpc++) # Или просто grpc++, если это имя компонента

# Поиск Catch2
# Это требует, чтобы Catch2 был установлен так, чтобы CMake мог его найти (например, системно, или установлен CMAKE_PREFIX_PATH)
# Для Catch2 v3.x он часто находится как пакет конфигурации CMake.
find_package(Catch2 3 REQUIRED) # Эта строка уже есть
if(NOT Catch2_FOUND)
    message(FATAL_ERROR "Catch2 version 3 or later not found. Please install Catch2 development files.")
else()
    message(STATUS "Found Catch2 version: ${Catch2_VERSION}")
endif()

# Добавляем исполняемый файл тестов
add_executable(game_tests
    main_test.cpp
    test_tank.cpp
    test_tank_pool.cpp
    test_game_session.cpp
    test_session_manager.cpp
    test_command_consumer.cpp   # Added
    test_auth_tcp_session.cpp   # Added
    test_game_udp_handler.cpp   # Added
    test_game_tcp_session.cpp   # Added
)

# Связываем исполняемый файл тестов с Catch2 и библиотекой игровой логики
# game_logic_lib определена в ../game_server_cpp/CMakeLists.txt
# auth_grpc_codegen_lib определена в ../protos/CMakeLists.txt
target_link_libraries(game_tests
    PRIVATE
    Catch2::Catch2WithMain       # Предоставляется find_package(Catch2)
    game_logic_lib
    auth_logic_lib             # Связываем новую библиотеку аутентификации
    proto_lib      # Изменено с auth_grpc_codegen_lib

    # Явно связываем то, что напрямую используется тестами, если не покрыто game_logic_lib или proto_lib
    Boost::system              # Предоставляется find_package(Boost)
    nlohmann_json::nlohmann_json # Предоставляется find_package(nlohmann_json)
    ${RabbitMQ_LINK_TARGET}    # Используем унифицированную переменную цели
    RdKafka::rdkafka++         # Используем согласованную GLOBAL цель
    Threads::Threads           # Предоставляется find_package(Threads)

    # Хорошей практикой является также связывание gRPC и Protobuf, если тесты используют их напрямую,
    # даже если proto_lib также их связывает.
    gRPC::grpc++_unsecure      # Изменено с gRPC::grpc++
    protobuf::libprotobuf      # Изменено с Protobuf::libprotobuf
    # gRPC::grpc++_reflection  # Только если рефлексия используется напрямую в тестах
)

# Каталоги для включения для тестов
target_include_directories(game_tests
    PRIVATE
    "${CMAKE_SOURCE_DIR}/game_server_cpp" # Чтобы найти *.h из game_server_cpp
    "${CMAKE_SOURCE_DIR}/auth_server_cpp" # Чтобы найти *.h из auth_server_cpp (например, auth_tcp_session.h)
    "${CMAKE_BINARY_DIR}/protos"          # Добавлено для поиска сгенерированных заголовков proto, таких как auth_service.grpc.pb.h
    # Путь включения для сгенерированных заголовков gRPC ("auth_service.grpc.pb.h")
    # должен поступать из PUBLIC include каталогов цели auth_grpc_codegen_lib.
    # Если CMAKE_SOURCE_DIR это cpp/, то каталог сборки protos это CMAKE_BINARY_DIR/protos/generated
    # Это должно обрабатываться INTERFACE_INCLUDE_DIRECTORIES цели auth_grpc_codegen_lib
)

# Добавляем этот исполняемый файл тестов в CTest
# Первый аргумент - это имя, которое CTest будет использовать для теста.
# Второй аргумент - это имя цели CMake для исполняемого файла теста.
add_test(NAME GameLogicUnitTests COMMAND game_tests)

message(STATUS "Configured game_tests executable.")
