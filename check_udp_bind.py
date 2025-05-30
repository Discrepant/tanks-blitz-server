import socket
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Test UDP socket binding.")
    parser.add_argument("host", help="Host to bind to (e.g., 0.0.0.0, localhost)")
    parser.add_argument("port", type=int, help="Port number to bind to (e.g., 29998)")
    args = parser.parse_args()

    host = args.host
    port = args.port

    sock = None  # Initialize sock to None
    print(f"Attempting to create and bind a UDP socket to {host}:{port}...")

    try:
        # Create a UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"  1. UDP socket created successfully.")

        # Try to bind the socket to the address and port
        sock.bind((host, port))
        print(f"  2. UDP socket successfully bound to {host}:{port}.")
        print("\nSUCCESS: UDP socket was bound successfully. This means the port is likely available and your user has permission.")
        print("If the game server still fails to bind, the issue might be specific to its implementation or another active process.")

    except socket.error as e:
        print(f"\nERROR: Could not bind to {host}:{port}")
        if e.errno == socket.errno.EADDRINUSE: # Address already in use
            print(f"  Reason: Address already in use. Another application might be using port {port}.")
            print(f"  Suggestion: Check for applications using this port (e.g., using 'netstat -lunp | grep {port}' on Linux, or 'netstat -ano | findstr UDP | findstr {port}' on Windows).")
        elif e.errno == socket.errno.EACCES: # Permission denied
            print(f"  Reason: Permission denied. You might need root/administrator privileges to bind to this port or address (especially for ports < 1024).")
            print(f"  Suggestion: Try running the script with 'sudo' (e.g., 'sudo python3 {sys.argv[0]} {host} {port}'). Use with caution, only if you understand the implications.")
        else:
            print(f"  Reason: An unexpected socket error occurred: {e} (errno: {e.errno})")
            print(f"  Suggestion: This could be a network configuration issue, firewall, or a more specific problem.")
    except OverflowError as e: # Port number might be out of range
        print(f"\nERROR: Invalid port number {port}. Port must be 0-65535.")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"\nERROR: An unexpected error occurred: {e}")
        print(f"  Type: {type(e).__name__}")
    finally:
        if sock:
            sock.close()
            print(f"\n  3. UDP socket closed.")
        else:
            print(f"\n  Socket was not created or an error occurred before it could be closed.")

if __name__ == "__main__":
    main()
