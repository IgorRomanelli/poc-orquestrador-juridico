"""
Configuração global do pytest.

Carrega .env antes de qualquer teste para garantir que variáveis de ambiente
(ex: CNPJ_REQUEST_DELAY_MS) estejam disponíveis nos testes assíncronos.
"""

import pytest
from dotenv import load_dotenv


def pytest_configure(config):
    load_dotenv()
