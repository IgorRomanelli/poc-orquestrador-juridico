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


# ─── TestPdfExporterIdentidade ─────────────────────────────────────────────────

class TestPdfExporterIdentidade:

    def test_html_contains_logo(self):
        """PDF HTML deve conter o logo do escritório como base64."""
        from src.export.pdf_exporter import _to_html
        html = _to_html("# Teste")
        assert "data:image/png;base64," in html, "HTML deve conter logo base64"

    def test_html_contains_brand_colors(self):
        """CSS deve usar as cores da marca Goulart|Law."""
        from src.export.pdf_exporter import _CSS
        assert "#C00000" in _CSS, "Vermelho primário ausente"
        assert "#1A3566" in _CSS, "Azul primário ausente"

    def test_html_contains_footer_text(self):
        """Rodapé deve mencionar Goulart|Law."""
        from src.export.pdf_exporter import _to_html
        html = _to_html("# Teste")
        assert "Goulart" in html


# ─── helpers para Task 7 / Task 8 ─────────────────────────────────────────────

def _make_full_item(
    page_url="https://example.com/page",
    domain="example.com",
    razao_social="Empresa Exemplo Ltda",
    nome_fantasia="Exemplo",
    cnpj="12.345.678/0001-99",
    situacao="ATIVA",
    natureza_juridica="206-2 - Sociedade Empresária Limitada",
    capital_social="100000.00",
    logradouro="Rua das Flores, 123",
    cep="01310-100",
    municipio="São Paulo",
    uf="SP",
    telefone="(11) 3000-0000",
    email="contato@empresa.com",
    atividade_principal="Desenvolvimento de sistemas",
    fonte="https://www.receitaws.com.br/v1/cnpj/12345678000199",
    socios=None,
) -> dict:
    if socios is None:
        socios = [{"nome": "João da Silva", "qualificacao": "Sócio Administrador"}]
    return {
        "search_result": {"page_url": page_url, "domain": domain, "source": "facecheck", "confidence": 0.87},
        "lookup": {
            "whois": {"registrant": "Empresa Exemplo Ltda", "created": "2020-01-01", "expiration_date": "2026-01-01"},
            "cnpj_data": {
                "cnpj": cnpj,
                "razao_social": razao_social,
                "nome_fantasia": nome_fantasia,
                "situacao": situacao,
                "natureza_juridica": natureza_juridica,
                "capital_social": capital_social,
                "logradouro": logradouro,
                "cep": cep,
                "municipio": municipio,
                "uf": uf,
                "telefone": telefone,
                "email": email,
                "atividade_principal": atividade_principal,
                "fonte": fonte,
                "socios": socios,
            },
            "jucesp": {"jucesp_search_url": "https://www.jucesponline.sp.gov.br/ResultadoBusca.aspx?chave=exemplo"},
            "summary": {"razao_social": razao_social, "cnpj": cnpj, "registrant": "Empresa Exemplo Ltda"},
        },
    }


# ─── TestDossieGeneratorCamposCompletos ────────────────────────────────────────

class TestDossieGeneratorCamposCompletos:

    def test_nome_fantasia_present(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "**Nome fantasia:**" in md
        assert "Exemplo" in md

    def test_atividade_principal_present(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "**Atividade principal:**" in md
        assert "Desenvolvimento de sistemas" in md

    def test_telefone_present(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "**Telefone:**" in md
        assert "(11) 3000-0000" in md

    def test_email_present(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "**E-mail:**" in md
        assert "contato@empresa.com" in md

    def test_cep_in_endereco(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "01310-100" in md

    def test_natureza_juridica_present(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "**Natureza jurídica:**" in md
        assert "Sociedade Empresária Limitada" in md

    def test_capital_social_present(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "**Capital social:**" in md
        assert "100000" in md

    def test_fonte_present(self):
        md = generate(client_name="C", violations=[_make_full_item()], investigate=[], date="2026-03-18")
        assert "**Fonte CNPJ:**" in md
        assert "receitaws" in md

    def test_missing_optional_fields_show_placeholder(self):
        item = _make_full_item(nome_fantasia=None, telefone=None, email=None, atividade_principal=None)
        md = generate(client_name="C", violations=[item], investigate=[], date="2026-03-18")
        # Each None field must still appear as placeholder (at least 4 occurrences total)
        assert md.count("— não identificado") >= 4


# ─── TestDossieGeneratorGoogleMaps ─────────────────────────────────────────────

class TestDossieGeneratorGoogleMaps:

    def test_maps_link_present_when_address_available(self):
        item = _make_full_item(
            logradouro="Rua das Flores, 123",
            municipio="São Paulo",
            uf="SP",
            cep="01310-100",
        )
        md = generate(client_name="C", violations=[item], investigate=[], date="2026-03-18")
        assert "maps.google.com" in md or "google.com/maps" in md

    def test_maps_link_encodes_address(self):
        item = _make_full_item(
            logradouro="Av. Paulista, 1000",
            municipio="São Paulo",
            uf="SP",
        )
        md = generate(client_name="C", violations=[item], investigate=[], date="2026-03-18")
        # URL must contain something from the address (encoded or plain)
        assert "Paulista" in md or "Paulista".replace(" ", "+") in md or "%20" in md

    def test_maps_link_absent_when_no_address(self):
        item = _make_full_item(logradouro=None, municipio="", uf="")
        item["lookup"]["cnpj_data"]["logradouro"] = None
        item["lookup"]["cnpj_data"]["municipio"] = ""
        item["lookup"]["cnpj_data"]["uf"] = ""
        md = generate(client_name="C", violations=[item], investigate=[], date="2026-03-18")
        # No Maps link when address is unknown
        assert "maps.google.com" not in md and "google.com/maps" not in md


# ─── TestThumbnailFormatting ───────────────────────────────────────────────────

class TestThumbnailFormatting:

    def test_thumbnail_preserves_list_formatting(self):
        """Quando preview_thumbnail está presente, os campos do dossiê devem continuar
        renderizando como lista (<li>), não como parágrafo simples."""
        from src.export.pdf_exporter import _to_html

        item = _make_full_item()
        item["search_result"]["preview_thumbnail"] = (
            "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwME"
        )
        md = generate(client_name="C", violations=[item], investigate=[], date="2026-03-18")
        html = _to_html(md)

        assert "<li>" in html, "Campos devem renderizar como itens de lista (<li>)"


# ─── TestPdfIdentidadeVisual ───────────────────────────────────────────────────

class TestPdfIdentidadeVisual:

    def test_doc_header_img_has_no_border(self):
        """Logo no cabeçalho não deve ter borda (border: none explícito no seletor .doc-header img)."""
        from src.export.pdf_exporter import _CSS
        # O seletor .doc-header img deve aparecer antes de border: none
        header_img_pos = _CSS.find(".doc-header img")
        border_none_after = _CSS.find("border: none", header_img_pos)
        assert header_img_pos != -1, ".doc-header img não encontrado no CSS"
        assert border_none_after != -1, ".doc-header img deve ter border: none explícito"

    def test_doc_header_is_centered(self):
        """Cabeçalho do documento deve ser centralizado."""
        from src.export.pdf_exporter import _CSS
        # text-align: center no .doc-header
        assert "text-align: center" in _CSS, ".doc-header deve ter text-align: center"

    def test_metadata_renders_on_separate_lines(self):
        """Cliente, Data e Gerado por devem aparecer em linhas separadas no HTML."""
        from src.export.pdf_exporter import _to_html
        md = generate(
            client_name="Cliente Teste",
            violations=[],
            investigate=[],
            date="2026-03-18",
        )
        html = _to_html(md)
        # Com dois espaços + \n no markdown, o parser gera <br> entre os campos
        assert "<br" in html, "Metadados devem ser separados por <br> para ficarem em linhas distintas"
