# CMakeLists.txt for game_server_cpp

# CMAKE_CXX_STANDARD is set in the root CMakeLists.txt

# Find direct dependencies for the game_logic_lib
find_package(Boost 1.71.0 REQUIRED COMPONENTS system asio)
message(STATUS "GameServerCpp: Found Boost version: ${Boost_VERSION_STRING}")

find_package(nlohmann_json 3.2.0 QUIET)
if(NOT nlohmann_json_FOUND)
    find_package(nlohmann_json 3.0.0 REQUIRED)
endif()
if(NOT nlohmann_json_FOUND)
    message(FATAL_ERROR "GameServerCpp: nlohmann_json not found.")
else()
    message(STATUS "GameServerCpp: Found nlohmann_json version ${nlohmann_json_VERSION}")
endif()

find_package(RdKafka REQUIRED)
# Add any necessary checks for RdKafka_FOUND if needed
# message(STATUS "GameServerCpp: Found RdKafka version ${RdKafka_VERSION}") # If available

find_package(Threads REQUIRED) # For ASIO, gRPC, Kafka, RabbitMQ callbacks etc.

# Define a static library for core game logic and handlers that don't depend on main_auth.cpp specific gRPC client
# This library will be linked by game_server_app and tests.
add_library(game_logic_lib STATIC
    kafka_producer_handler.cpp
    tank.cpp
    tank_pool.cpp
    game_session.cpp    # Added game_session.cpp
    session_manager.cpp # Added session_manager.cpp
    # command_consumer.cpp # To be added when recreated - needs RabbitMQ
)

# Dependencies for game_logic_lib
target_link_libraries(game_logic_lib PRIVATE
    librdkafka::librdkafka
    Threads::Threads
    nlohmann_json::nlohmann_json # If used in .cpp files, not just headers
    Boost::asio
)

target_include_directories(game_logic_lib PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR} # So game_server_app can include headers from here
)


# Executable for the main game server
add_executable(game_server_app
    main.cpp
    udp_handler.cpp     # Ensures udp_handler is included
    tcp_handler.cpp     # Ensures tcp_handler is included
    tcp_session.cpp     # Ensures tcp_session is included
    command_consumer.cpp # Added command_consumer.cpp here
)

# --- Begin Manual Find for librabbitmq ---
message(STATUS "Attempting manual find for librabbitmq...")
set(LIBRABBITMQ_FOUND FALSE)

# Try to find the include directory
# Common triplet for the user is x64-windows
set(_VCPKG_USER_INSTALL_PREFIX "C:/Users/Hoshi/vcpkg/installed/x64-windows") # User specific path

find_path(LIBRABBITMQ_INCLUDE_DIR amqp.h
    HINTS 
        "${_VCPKG_USER_INSTALL_PREFIX}/include"
        "${CMAKE_TOOLCHAIN_FILE_DIR}/../../installed/x64-windows/include" # Relative to vcpkg.cmake
        "$ENV{VCPKG_ROOT}/installed/x64-windows/include" # If VCPKG_ROOT is set
    PATH_SUFFIXES librabbitmq # Some libraries have their headers in a subfolder
    NO_DEFAULT_PATH
)

# Try to find the library
# For Release
find_library(LIBRABBITMQ_LIBRARY_RELEASE NAMES librabbitmq rabbitmq amqp
    HINTS 
        "${_VCPKG_USER_INSTALL_PREFIX}/lib"
        "${CMAKE_TOOLCHAIN_FILE_DIR}/../../installed/x64-windows/lib"
        "$ENV{VCPKG_ROOT}/installed/x64-windows/lib"
    NO_DEFAULT_PATH
)
# For Debug
find_library(LIBRABBITMQ_LIBRARY_DEBUG NAMES librabbitmqd rabbitmqd amqpd # Common debug suffixes
    HINTS 
        "${_VCPKG_USER_INSTALL_PREFIX}/debug/lib"
        "${CMAKE_TOOLCHAIN_FILE_DIR}/../../installed/x64-windows/debug/lib"
        "$ENV{VCPKG_ROOT}/installed/x64-windows/debug/lib"
    NO_DEFAULT_PATH
)

if(LIBRABBITMQ_INCLUDE_DIR AND LIBRABBITMQ_LIBRARY_RELEASE) # Debug library is optional for basic success
    # Ensure we have at least the release library. Debug is a bonus.
    # If debug is not found, but release is, we can still proceed for release builds.
    if(NOT LIBRABBITMQ_LIBRARY_DEBUG)
        message(STATUS "Manual find for librabbitmq: Debug library not found, Release library will be used for debug configurations as well if not specified otherwise.")
        set(LIBRABBITMQ_LIBRARY_DEBUG ${LIBRABBITMQ_LIBRARY_RELEASE}) # Fallback: use release for debug
    endif()

    # Create the imported target if it doesn't exist yet
    if(NOT TARGET librabbitmq::librabbitmq)
        add_library(librabbitmq::librabbitmq UNKNOWN IMPORTED GLOBAL)
        set_target_properties(librabbitmq::librabbitmq PROPERTIES
            INTERFACE_INCLUDE_DIRECTORIES "${LIBRABBITMQ_INCLUDE_DIR}"
        )
        # Set release and debug locations
        set_property(TARGET librabbitmq::librabbitmq APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
        set_target_properties(librabbitmq::librabbitmq PROPERTIES
            IMPORTED_LOCATION_RELEASE "${LIBRABBITMQ_LIBRARY_RELEASE}"
        )
        set_property(TARGET librabbitmq::librabbitmq APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG)
        set_target_properties(librabbitmq::librabbitmq PROPERTIES
            IMPORTED_LOCATION_DEBUG "${LIBRABBITMQ_LIBRARY_DEBUG}" # This will be same as release if debug not found
        )
        message(STATUS "Created librabbitmq::librabbitmq imported target manually.")
    else()
        message(STATUS "Target librabbitmq::librabbitmq already exists.")
    endif()
    
    set(LIBRABBITMQ_FOUND TRUE)
    message(STATUS "Found librabbitmq manually. Include: ${LIBRABBITMQ_INCLUDE_DIR}, LibRelease: ${LIBRABBITMQ_LIBRARY_RELEASE}, LibDebug: ${LIBRABBITMQ_LIBRARY_DEBUG}")
else()
    set(LIBRABBITMQ_FOUND FALSE) # Explicitly set if not found
    message(WARNING "Manual find for librabbitmq FAILED. Check paths and vcpkg installation. Include_Dir: ${LIBRABBITMQ_INCLUDE_DIR}, LibRelease: ${LIBRABBITMQ_LIBRARY_RELEASE}, LibDebug: ${LIBRABBITMQ_LIBRARY_DEBUG}")
    # Consider making this a FATAL_ERROR if librabbitmq is absolutely essential
    # message(FATAL_ERROR "Failed to find librabbitmq manually.")
endif()
# --- End Manual Find for librabbitmq ---

# Link game_server_app against its constituent libraries and dependencies
target_link_libraries(game_server_app PRIVATE
    game_logic_lib        # Core logic
    proto_lib # For gRPC stubs (defined in protos/CMakeLists.txt)
    Boost::asio         # For ASIO
    librdkafka::librdkafka
    librabbitmq::librabbitmq
    Threads::Threads
    nlohmann_json::nlohmann_json # For JSON processing in handlers
    # gRPC::grpc++ and protobuf::libprotobuf are transitive dependencies from proto_lib
    # but if GameTCPSession uses gRPC types directly and proto_lib doesn't
    # export gRPC::grpc++ as INTERFACE or PUBLIC, we might need to link it here too.
    # Assuming auth_grpc_codegen_lib correctly exports gRPC & Protobuf linkage.
)

target_include_directories(game_server_app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR} # To find its own headers like udp_handler.h etc.
)

install(TARGETS game_server_app DESTINATION bin)

message(STATUS "CMake configuration for game_server_cpp finished.")
