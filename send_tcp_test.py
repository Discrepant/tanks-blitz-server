# send_tcp_test.py
import socket
import time

def send_tcp_message(host, port, message):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(message.encode())
            print(f"Sent: {message.strip()}")
            response = s.recv(1024)
            print(f"Received: {response.decode().strip()}")
    except Exception as e:
        print(f"Error sending/receiving: {e}")

if __name__ == "__main__":
    server_host = "localhost"
    server_port = 8888

    messages = [
        "LOGIN player1 password123\n",  # Корректный запрос
        "LOGIN testuser wrongpass\n",   # Неверный пароль
        "LOGIN non_existent_user mypass\n", # Несуществующий пользователь
        "INVALID_COMMAND_FORMAT\n",    # Неверный формат
        "LOGIN short\n"                # Слишком короткий
    ]

    for msg in messages:
        send_tcp_message(server_host, server_port, msg)
        time.sleep(0.5)
