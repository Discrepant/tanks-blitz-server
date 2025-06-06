import pytest
from unittest.mock import patch, MagicMock
import os

# Импортируем тестируемую функцию
from auth_server.main import start_metrics_server

# Тест для start_metrics_server
def test_start_metrics_server_success():
    # Мокируем prometheus_client.start_http_server
    with patch('auth_server.main.start_http_server') as mock_start_http:
        # Мокируем os.getenv для предсказуемого порта, если он используется для порта метрик
        # (в auth_server.main порт метрик 8000 жестко задан, так что это может не понадобиться)
        # с учетом текущей реализации start_metrics_server, порт 8000 жестко задан.

        start_metrics_server() # Вызываем функцию

        # Проверяем, что start_http_server был вызван с портом 8000
        mock_start_http.assert_called_once_with(8000)

def test_start_metrics_server_os_error():
    # Мокируем prometheus_client.start_http_server, чтобы он вызывал OSError
    with patch('auth_server.main.start_http_server', side_effect=OSError("Test OSError")) as mock_start_http:
        with patch('auth_server.main.logger') as mock_logger: # Мокируем логгер для проверки вывода ошибки
            start_metrics_server()

            mock_start_http.assert_called_once_with(8000)
            # Проверяем, что ошибка была залогирована
            mock_logger.error.assert_called_once()
            # Можно также проверить текст сообщения, если он важен
            args, kwargs = mock_logger.error.call_args
            assert "OSError starting Prometheus metrics server" in args[0]
            # Проверяем, что exc_info содержит исключение (или равно True).
            # unittest.mock.call_args возвращает кортеж (args, kwargs). kwargs['exc_info'] должно быть исключением или True.
            # В зависимости от того, как вызывается logger.error с exc_info=True,
            # exc_info в call_args может быть True или фактическим объектом исключения.
            # Код использует exc_info=True, поэтому мы проверяем на True.
            assert kwargs.get('exc_info') is True

def test_start_metrics_server_generic_exception():
    # Мокируем prometheus_client.start_http_server, чтобы он вызывал общее исключение
    with patch('auth_server.main.start_http_server', side_effect=Exception("Test Exception")) as mock_start_http:
        with patch('auth_server.main.logger') as mock_logger:
            start_metrics_server()

            mock_start_http.assert_called_once_with(8000)
            mock_logger.error.assert_called_once()
            args, kwargs = mock_logger.error.call_args
            assert "Failed to start Prometheus metrics server" in args[0]
            # Аналогично OSError, проверяем exc_info
            assert kwargs.get('exc_info') is True
