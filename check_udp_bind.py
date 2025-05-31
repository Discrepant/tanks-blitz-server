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

    sock = None  # Инициализируем sock как None
    print(f"Попытка создать и привязать UDP сокет к {host}:{port}...")

    try:
        # Создаем UDP сокет
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"  1. UDP сокет успешно создан.")

        # Пытаемся привязать сокет к адресу и порту
        sock.bind((host, port))
        print(f"  2. UDP сокет успешно привязан к {host}:{port}.")
        print("\nУСПЕХ: UDP сокет был успешно привязан. Это означает, что порт, скорее всего, доступен, и у вашего пользователя есть разрешение.")
        print("Если игровой сервер по-прежнему не может привязаться, проблема может быть специфична для его реализации или другого активного процесса.")

    except socket.error as e:
        print(f"\nОШИБКА: Не удалось привязаться к {host}:{port}")
        if e.errno == socket.errno.EADDRINUSE: # Адрес уже используется
            print(f"  Причина: Адрес уже используется. Другое приложение может использовать порт {port}.")
            print(f"  Предложение: Проверьте приложения, использующие этот порт (например, с помощью 'netstat -lunp | grep {port}' в Linux или 'netstat -ano | findstr UDP | findstr {port}' в Windows).")
        elif e.errno == socket.errno.EACCES: # Отказано в доступе
            print(f"  Причина: Отказано в доступе. Вам могут потребоваться права root/администратора для привязки к этому порту или адресу (особенно для портов < 1024).")
            print(f"  Предложение: Попробуйте запустить скрипт с 'sudo' (например, 'sudo python3 {sys.argv[0]} {host} {port}'). Используйте с осторожностью, только если вы понимаете последствия.")
        else:
            print(f"  Причина: Произошла непредвиденная ошибка сокета: {e} (errno: {e.errno})")
            print(f"  Предложение: Это может быть проблема конфигурации сети, брандмауэра или более специфическая проблема.")
    except OverflowError as e: # Номер порта может быть вне допустимого диапазона
        print(f"\nОШИБКА: Недопустимый номер порта {port}. Порт должен быть в диапазоне 0-65535.")
        print(f"  Подробности: {e}")
    except Exception as e:
        print(f"\nОШИБКА: Произошла непредвиденная ошибка: {e}")
        print(f"  Тип: {type(e).__name__}")
    finally:
        if sock:
            sock.close()
            print(f"\n  3. UDP сокет закрыт.")
        else:
            print(f"\n  Сокет не был создан или произошла ошибка до того, как его можно было закрыть.")

if __name__ == "__main__":
    main()
