"""
Exportador de PDF: converte markdown em PDF via fpdf2 (pure Python, sem deps de sistema).

Duas funções públicas:
    export(markdown_text, output_path) → salva PDF em disco, retorna output_path
    to_bytes(markdown_text)            → retorna bytes do PDF
"""

import io
import os

import markdown as _md
from fpdf import FPDF

# ─── normalização Latin-1 ─────────────────────────────────────────────────────

# fpdf2 usa fontes built-in Latin-1; caracteres fora desse range causam erro.
# Acentos portugueses (ã, é, ç…) SÃO Latin-1 — só precisamos trocar os extras.
_UNICODE_REPLACEMENTS: dict[str, str] = {
    "\u2014": "-",    # em dash —
    "\u2013": "-",    # en dash –
    "\u2019": "'",    # aspas simples direita '
    "\u2018": "'",    # aspas simples esquerda '
    "\u201c": '"',    # aspas duplas esquerda "
    "\u201d": '"',    # aspas duplas direita "
    "\u2026": "...",  # reticências …
    "\u2022": "-",    # bullet •
    "\u00b7": ".",    # ponto central (já é Latin-1, mas causa problemas em alguns contextos)
}


def _to_latin1(text: str) -> str:
    """Substitui caracteres não-Latin-1 por equivalentes ASCII seguros."""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Garante que nenhum outro char fora do range Latin-1 vaze
    return text.encode("latin-1", errors="replace").decode("latin-1")

# ─── assets ───────────────────────────────────────────────────────────────────

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _load_logo_bytes() -> bytes | None:
    logo_path = os.path.join(_ASSETS_DIR, "logo_goulart_law.png")
    try:
        with open(logo_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


_LOGO_BYTES = _load_logo_bytes()

# ─── PDF class ────────────────────────────────────────────────────────────────

_RED = (234, 51, 35)
_NAVY = (26, 53, 102)
_GRAY = (136, 136, 136)


class _DossiePDF(FPDF):
    def header(self) -> None:
        if _LOGO_BYTES:
            self.image(io.BytesIO(_LOGO_BYTES), x=(self.w - 40) / 2, w=40)
            self.ln(3)
        else:
            self.set_font("Helvetica", "B", 11)
            self.set_text_color(*_RED)
            self.cell(0, 10, "Goulart|Law · Advocacia Especializada", align="C")
            self.ln(3)
        self.set_draw_color(*_RED)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(6)
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_GRAY)
        self.cell(0, 10, f"Goulart|Law - Advocacia Especializada  -  {self.page_no()}", align="C")


# ─── funções públicas ──────────────────────────────────────────────────────────


def to_bytes(markdown_text: str) -> bytes:
    """
    Converte markdown em PDF e retorna como bytes.

    Raises:
        RuntimeError: se a geração do PDF falhar.
    """
    try:
        safe_markdown = _to_latin1(markdown_text)
        html = _md.markdown(safe_markdown, extensions=["extra"])
        pdf = _DossiePDF()
        pdf.set_margins(20, 20, 20)
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        pdf.write_html(html)
        return bytes(pdf.output())
    except Exception as exc:
        raise RuntimeError(f"Erro ao gerar PDF: {exc}") from exc


def export(markdown_text: str, output_path: str) -> str:
    """
    Converte markdown em PDF e salva em output_path.

    Raises:
        RuntimeError: se a geração ou escrita do PDF falhar.
    """
    try:
        data = to_bytes(markdown_text)
        with open(output_path, "wb") as f:
            f.write(data)
        return output_path
    except Exception as exc:
        raise RuntimeError(f"Erro ao salvar PDF em '{output_path}': {exc}") from exc
