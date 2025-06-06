cmake_minimum_required(VERSION 3.28)
cmake_policy(SET CMP0167 NEW)
project(TankGameCppServices CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_EXTENSIONS OFF) # Отключаем специфичные для компилятора расширения, такие как -std=gnu++17

if(MSVC OR (CMAKE_SYSTEM_NAME STREQUAL "Windows" AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang"))
    # Определяем _WIN32_WINNT для нацеливания на Windows 10 (0x0A00) или выше.
    # Это помогает с библиотеками вроде Boost.Asio и избегает предупреждений.
    # Для Windows 7 используйте 0x0601. Для Windows 8 - 0x0602. Для Windows 8.1 - 0x0603.
    add_compile_definitions(_WIN32_WINNT=0x0A00)
    message(STATUS "Setting _WIN32_WINNT to 0x0A00 (Windows 10)")
elseif(CMAKE_SYSTEM_NAME STREQUAL "Windows" AND CMAKE_CXX_COMPILER_ID MATCHES "Intel")
    # Для компилятора Intel в Windows определение может отличаться или управляться окружением
    add_compile_definitions(_WIN32_WINNT=0x0A00) # Предполагаем аналогично для Intel C++ в Windows
    message(STATUS "Setting _WIN32_WINNT to 0x0A00 (Windows 10) for Intel Compiler")
endif()

# Общие настройки - могут быть расширены
set(CMAKE_EXPORT_COMPILE_COMMANDS ON) # Полезно для некоторых инструментов, таких как clangd

# Поиск глобальных зависимостей, которые могут использоваться несколькими подпроектами
# Например, если nlohmann_json используется повсеместно и версия согласована.
# Однако часто чище позволить подпроектам объявлять свои прямые зависимости.

# Добавляем подкаталоги
# Подкаталог 'protos' определит цель для генерации кода gRPC/Protobuf.
# Эта цель затем может быть связана другими подпроектами.
find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED)
add_subdirectory(protos)
add_subdirectory(game_server_cpp)
add_subdirectory(auth_server_cpp)

# Тестирование с Catch2
# Включаем тестирование для этого проекта
enable_testing()

# Добавляем подкаталог tests
# Предполагается, что tests/CMakeLists.txt определит исполняемый файл тестов
add_subdirectory(tests)

message(STATUS "Root CMakeLists.txt processed. Testing enabled.")
