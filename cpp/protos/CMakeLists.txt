# protos/CMakeLists.txt
set(PROTO_FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/auth_service.proto
)

# Укажите директорию для генерации кода
set(PROTOBUF_OUTPUT_DIR ${CMAKE_CURRENT_BINARY_DIR})

# Включите библиотеки Protobuf и gRPC
# find_package(Protobuf CONFIG REQUIRED) # Protobuf должен быть найден protobuf_generate_cpp или унаследован
find_package(gRPC CONFIG REQUIRED) # Это должно определить gRPC_GRPC_CPP_PLUGIN_EXECUTABLE

# Генерация Protobuf кода
# protobuf_generate_cpp сгенерирует файлы .pb.cc и .pb.h.
# Он устанавливает PROTO_SRCS в список сгенерированных файлов .pb.cc
# и PROTO_HDRS в список сгенерированных файлов .pb.h.
protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS ${PROTO_FILES})

# Генерация gRPC кода
# Отзыв пользователя определяет GRPC_SRCS и GRPC_HDRS как конкретные имена файлов.
set(GRPC_SRCS ${PROTOBUF_OUTPUT_DIR}/auth_service.grpc.pb.cc)
set(GRPC_HDRS ${PROTOBUF_OUTPUT_DIR}/auth_service.grpc.pb.h)

# Поиск исполняемого файла плагина gRPC C++
find_program(GRPC_CPP_PLUGIN_EXECUTABLE_PATH
    NAMES grpc_cpp_plugin.exe grpc_cpp_plugin protoc-gen-grpc.exe protoc-gen-grpc
    HINTS
        "C:/Users/Hoshi/vcpkg/installed/x64-windows/tools/grpc" # Прямой путь пользователя
        "${CMAKE_TOOLCHAIN_FILE_DIR}/../../installed/${VCPKG_TARGET_TRIPLET}/tools/grpc" # Относительно vcpkg.cmake
        "$ENV{VCPKG_ROOT}/installed/${VCPKG_TARGET_TRIPLET}/tools/grpc" # Через переменную окружения VCPKG_ROOT
    # PATHS # Явное добавление системных путей может быть слишком широким; полагаемся на HINTS и стандартный поиск CMake после HINTS
)

if(NOT GRPC_CPP_PLUGIN_EXECUTABLE_PATH)
    message(FATAL_ERROR "gRPC C++ plugin (e.g., grpc_cpp_plugin.exe) not found.     Please ensure it is installed correctly by vcpkg (in tools/grpc) or is in your system PATH.     HINTS for find_program included 'C:/Users/Hoshi/vcpkg/installed/x64-windows/tools/grpc'.")
else()
    message(STATUS "Found gRPC C++ plugin at: ${GRPC_CPP_PLUGIN_EXECUTABLE_PATH}")
endif()

add_custom_command(
    OUTPUT ${GRPC_SRCS} ${GRPC_HDRS}
    COMMAND ${Protobuf_PROTOC_EXECUTABLE}
    ARGS --proto_path=${CMAKE_CURRENT_SOURCE_DIR} # Добавлена эта строка
         --grpc_out=${PROTOBUF_OUTPUT_DIR}
         --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN_EXECUTABLE_PATH}
         ${PROTO_FILES} # Это ${CMAKE_CURRENT_SOURCE_DIR}/auth_service.proto
    DEPENDS ${PROTO_FILES}
    COMMENT "Generating gRPC code from auth_service.proto"
    VERBATIM
)

# Создание библиотеки
add_library(proto_lib STATIC
    ${PROTO_SRCS}          # Сгенерировано protobuf_generate_cpp
    ${GRPC_SRCS}           # Сгенерировано add_custom_command
    ${PROTO_HDRS}          # Сгенерировано protobuf_generate_cpp
    ${GRPC_HDRS}           # Вывод add_custom_command
)

target_link_libraries(proto_lib PRIVATE
    protobuf::libprotobuf
    gRPC::grpc++_unsecure
)

target_include_directories(proto_lib PUBLIC
    ${PROTOBUF_OUTPUT_DIR}
)

message(STATUS "Configured proto_lib with custom gRPC generation.")
