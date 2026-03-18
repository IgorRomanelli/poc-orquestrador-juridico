"""
Testes unitários — módulo de exportação (dossie_generator + pdf_exporter).

Cobertura:
    TestDossieGenerator:
        - test_generates_required_sections
        - test_empty_fields_show_placeholder
        - test_violations_and_investigate_separated
        - test_no_violations_generates_empty_section

    TestPdfExporter:
        - test_to_bytes_returns_bytes
        - test_markdown_content_reflected
"""

import pytest

from src.export.dossie_generator import generate


# ─── fixtures ──────────────────────────────────────────────────────────────────

def _make_item(
    page_url="https://example.com/page",
    domain="example.com",
    source="facecheck",
    confidence=0.87,
    razao_social="Empresa Exemplo Ltda",
    cnpj="12.345.678/0001-99",
    socios=None,
    situacao="ATIVA",
    logradouro="Rua das Flores, 123",
    municipio="São Paulo",
    uf="SP",
    registrant="Empresa Exemplo Ltda",
    created="2020-01-01",
    expiration_date="2026-01-01",
    jucesp_url="https://www.jucesponline.sp.gov.br/ResultadoBusca.aspx?chave=exemplo",
) -> dict:
    if socios is None:
        socios = [{"nome": "João da Silva", "qualificacao": "Sócio Administrador"}]
    return {
        "search_result": {
            "page_url": page_url,
            "domain": domain,
            "source": source,
            "confidence": confidence,
        },
        "lookup": {
            "whois": {
                "registrant": registrant,
                "created": created,
                "expiration_date": expiration_date,
            },
            "cnpj_data": {
                "cnpj": cnpj,
                "razao_social": razao_social,
                "situacao": situacao,
                "logradouro": logradouro,
                "municipio": municipio,
                "uf": uf,
                "socios": socios,
            },
            "jucesp": {
                "jucesp_search_url": jucesp_url,
            },
            "summary": {
                "razao_social": razao_social,
                "cnpj": cnpj,
                "registrant": registrant,
            },
        },
    }


# ─── TestDossieGenerator ───────────────────────────────────────────────────────

class TestDossieGenerator:

    def test_generates_required_sections(self):
        md = generate(
            client_name="Cliente Teste",
            violations=[_make_item()],
            investigate=[],
            date="2026-03-18",
        )

        assert "# Dossiê de Violação de Imagem" in md
        assert "**Cliente:** Cliente Teste" in md
        assert "**Data:** 2026-03-18" in md
        assert "## Violações Identificadas" in md
        assert "## Para Investigação" in md
        assert "Dossiê gerado automaticamente" in md

    def test_empty_fields_show_placeholder(self):
        item = _make_item(
            razao_social=None,
            cnpj=None,
            socios=[],
            situacao=None,
            logradouro=None,
            registrant=None,
            jucesp_url=None,
        )
        # Apagar summary também
        item["lookup"]["summary"]["razao_social"] = None
        item["lookup"]["summary"]["cnpj"] = None

        md = generate(
            client_name="Cliente",
            violations=[item],
            investigate=[],
            date="2026-03-18",
        )

        placeholder = "— não identificado"
        # Deve aparecer múltiplas vezes (empresa, cnpj, responsável, situação, endereço, etc.)
        assert md.count(placeholder) >= 4

    def test_violations_and_investigate_separated(self):
        violation = _make_item(page_url="https://violation.com/page", domain="violation.com")
        investigar = _make_item(page_url="https://investigate.com/page", domain="investigate.com")

        md = generate(
            client_name="Cliente",
            violations=[violation],
            investigate=[investigar],
            date="2026-03-18",
        )

        violations_pos = md.index("## Violações Identificadas")
        investigate_pos = md.index("## Para Investigação")

        # Violação aparece antes da seção de investigação
        assert md.index("violation.com") < investigate_pos
        # Item de investigação aparece depois da seção de investigação
        assert md.index("investigate.com") > investigate_pos
        # Seção de violações vem antes de investigação
        assert violations_pos < investigate_pos

    def test_investigate_item_header_when_razao_social_contains_violacao(self):
        """_render_investigate_item não deve corromper dados que contêm 'Violação'."""
        item = _make_item(
            razao_social="Empresa Violação 1 Ltda",  # dado contém "Violação 1"
            page_url="https://investigate.com/page",
            domain="investigate.com",
        )
        md = generate(
            client_name="Cliente",
            violations=[],
            investigate=[item],
            date="2026-03-18",
        )
        # O cabeçalho do bloco deve ser "Investigação 1", não "### Violação 1"
        assert "### Investigação 1" in md
        # A razão social não deve ter sido modificada
        assert "Empresa Violação 1 Ltda" in md

    def test_no_violations_generates_empty_section(self):
        md = generate(
            client_name="Cliente",
            violations=[],
            investigate=[],
            date="2026-03-18",
        )

        assert "## Violações Identificadas" in md
        assert "## Para Investigação" in md
        assert "_Nenhuma violação identificada._" in md
        assert "_Nenhum item para investigação._" in md


# ─── TestPdfExporter ───────────────────────────────────────────────────────────

class TestPdfExporter:

    def test_to_bytes_returns_bytes(self):
        try:
            import weasyprint  # noqa: F401
        except (ImportError, OSError):
            pytest.skip("WeasyPrint ou dependências do sistema não disponíveis")
        from src.export.pdf_exporter import to_bytes

        md = generate(
            client_name="Teste PDF",
            violations=[_make_item()],
            investigate=[],
            date="2026-03-18",
        )
        result = to_bytes(md)

        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[:4] == b"%PDF", "Resultado não é um PDF válido"

    def test_to_bytes_raises_runtime_error_with_message_on_failure(self):
        """Falha do WeasyPrint deve virar RuntimeError com mensagem amigável."""
        import sys
        from unittest.mock import MagicMock, patch
        from src.export.pdf_exporter import to_bytes

        mock_html_class = MagicMock()
        mock_html_class.return_value.write_pdf.side_effect = Exception("cairo not found")
        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML = mock_html_class

        with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
            with pytest.raises(RuntimeError, match="Erro ao gerar PDF"):
                to_bytes("# Teste")

    def test_markdown_content_reflected(self):
        """Verifica que o texto do markdown aparece no HTML intermediário (sem WeasyPrint)."""
        from src.export.pdf_exporter import _to_html

        md = generate(
            client_name="Cliente Verificação",
            violations=[_make_item(razao_social="Empresa ABC Ltda")],
            investigate=[],
            date="2026-03-18",
        )
        html = _to_html(md)

        assert "Cliente Verificação" in html
        assert "Empresa ABC Ltda" in html
        assert "Dossiê de Violação de Imagem" in html
