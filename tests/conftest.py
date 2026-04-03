"""
Configuração global do pytest.

Carrega .env antes de qualquer teste para garantir que variáveis de ambiente
(ex: CNPJ_REQUEST_DELAY_MS) estejam disponíveis nos testes assíncronos.
"""

import pytest
from dotenv import load_dotenv


def pytest_configure(config):
    load_dotenv()


@pytest.fixture
def sample_search_item():
    """Item de busca padrão para testes de export e UI."""
    return {
        "image_url": None,
        "page_url": "https://example.com/page",
        "domain": "example.com",
        "source": "facecheck",
        "confidence": 0.87,
        "preview_thumbnail": None,
    }


@pytest.fixture
def sample_lookup_result():
    """Resultado de lookup padrão para testes de export."""
    return {
        "whois": {
            "registrant": "Empresa Exemplo Ltda",
            "created": "2020-01-01",
            "expiration_date": "2026-01-01",
        },
        "cnpj_data": {
            "cnpj": "12.345.678/0001-99",
            "razao_social": "Empresa Exemplo Ltda",
            "situacao": "ATIVA",
            "logradouro": "Rua das Flores, 123",
            "municipio": "São Paulo",
            "uf": "SP",
            "socios": [{"nome": "João da Silva", "qualificacao": "Sócio Administrador"}],
        },
        "summary": {
            "razao_social": "Empresa Exemplo Ltda",
            "cnpj": "12.345.678/0001-99",
            "registrant": "Empresa Exemplo Ltda",
        },
    }
