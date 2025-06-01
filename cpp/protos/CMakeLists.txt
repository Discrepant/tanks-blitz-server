cmake_minimum_required(VERSION 3.16)
project(AuthGrpcCodegen CXX)

# Find necessary packages for codegen
find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED COMPONENTS grpc++)

# Define the location of .proto file
set(PROTO_FILE "${CMAKE_CURRENT_SOURCE_DIR}/auth_service.proto")

set(PROTO_FILES ${PROTO_FILE}) # Assuming PROTO_FILE is already defined as auth_service.proto

protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS ${PROTO_FILES})
grpc_generate_cpp(GRPC_SRCS GRPC_HDRS ${PROTO_FILES} PLUGIN_EXT ".grpc") # Added PLUGIN_EXT to avoid potential conflicts if not default

# The generated files (PROTO_SRCS, PROTO_HDRS, GRPC_SRCS, GRPC_HDRS) will be automatically
# placed in a directory like ${CMAKE_CURRENT_BINARY_DIR}/generated_sources/protobuf (actual path may vary by CMake version)
# For clarity, explicitly set an include directory if needed, or rely on CMake's default handling.
# If explicit control over output location is desired and standard functions don't offer it directly
# in older CMake versions, this might need adjustment. For now, assume standard behavior.

add_library(proto_lib STATIC
    ${PROTO_SRCS}
    ${GRPC_SRCS}
    ${PROTO_HDRS}
    ${GRPC_HDRS}
)

target_include_directories(proto_lib PUBLIC
    "${CMAKE_CURRENT_BINARY_DIR}"
)

target_link_libraries(proto_lib PRIVATE
    Protobuf::libprotobuf
    gRPC::grpc++_unsecure
)

message(STATUS "Configured proto_lib target with unsecure gRPC.")
