# Base Python image
FROM python:3.9-slim-buster

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /usr/src/app

# Install system dependencies (if any are needed by Python packages)
# For example, if a library needed gcc or other build tools for installation via pip.
# RUN apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache for dependencies
# This assumes requirements.txt is in the root of the build context (auth_server/)
COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the protos directory for gRPC generated code
# This assumes the Docker build context for this service is the project root,
# OR that the protos directory is copied into the auth_server directory before build.
# Given docker-compose context is usually ./auth_server, protos needs to be there or copied in.
# For a cleaner build, the root Dockerfile (cpp/Dockerfile) context is the project root.
# Let's assume the context for this Dockerfile (auth_server/Dockerfile) will be the project root.
# So, COPY ./protos ./protos will copy the protos dir from project root.
COPY ./protos ./protos

# Copy the auth_server application code into the container
# This assumes the context is project root: copies auth_server/* to /usr/src/app/auth_server/*
COPY ./auth_server ./auth_server

# Copy gRPC generated files for Python (auth_server/grpc_generated)
# These are generated from protos/auth_service.proto
# The generation step should happen before building this image or as part of a multi-stage build.
# For simplicity now, assume they are pre-generated and copied.
# If auth_server/grpc_generated is already inside auth_server/ when copied above, this is redundant.
# Let's ensure the generated files are correctly placed relative to auth_server.
# The python -m grpc_tools.protoc command output them to auth_server/grpc_generated.
# So, the `COPY ./auth_server ./auth_server` should already include them.

# Expose the gRPC port (as defined in docker-compose.yml and auth_grpc_server.py)
EXPOSE 50051

# Command to run the gRPC server
# This runs auth_grpc_server.py located inside the auth_server package.
CMD ["python", "-m", "auth_server.auth_grpc_server"]
