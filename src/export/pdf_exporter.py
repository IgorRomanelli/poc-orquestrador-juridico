"""
Exportador de PDF via fpdf2 (pure Python, sem dependências de sistema).

Renderiza o markdown gerado pelo dossie_generator linha a linha,
com controle total sobre quebras de página — sem usar write_html().
"""

import base64
import io
import os
import re

from fpdf import FPDF

# ─── assets ───────────────────────────────────────────────────────────────────

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

_RED  = (234, 51, 35)
_NAVY = (26, 53, 102)
_GRAY = (136, 136, 136)

# ─── Latin-1 sanitization ─────────────────────────────────────────────────────

_UNICODE_MAP: dict[str, str] = {
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2019": "'",   "\u2018": "'",
    "\u201c": '"',   "\u201d": '"',
    "\u2026": "...", "\u2022": "-",
}


def _safe(text: str) -> str:
    for ch, rep in _UNICODE_MAP.items():
        text = text.replace(ch, rep)
    return text.encode("latin-1", errors="replace").decode("latin-1")


# ─── logo ─────────────────────────────────────────────────────────────────────


def _load_logo_bytes() -> bytes | None:
    path = os.path.join(_ASSETS_DIR, "logo_goulart_law.png")
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


_LOGO_BYTES = _load_logo_bytes()

# ─── PDF class ────────────────────────────────────────────────────────────────


class _DossiePDF(FPDF):
    def header(self) -> None:
        if _LOGO_BYTES:
            self.image(io.BytesIO(_LOGO_BYTES), x=(self.w - 40) / 2, w=40)
            self.ln(3)
        else:
            self.set_font("Helvetica", "B", 11)
            self.set_text_color(*_RED)
            self.cell(0, 10, "Goulart|Law - Advocacia Especializada", align="C")
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


# ─── rendering helpers ────────────────────────────────────────────────────────


def _ensure_space(pdf: _DossiePDF, mm: float) -> None:
    """Nova página se restar menos que `mm` mm antes da margem inferior."""
    if pdf.get_y() > pdf.h - pdf.b_margin - mm:
        pdf.add_page()


def _render_bullet(pdf: _DossiePDF, text: str) -> None:
    """Linha de bullet: **Chave:** valor — chave em negrito."""
    _ensure_space(pdf, 10)
    m = re.match(r"\*\*(.+?)\*\*(.*)", text)
    if m:
        key   = _safe(m.group(1))
        value = _safe(m.group(2).strip())
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font("Helvetica", size=10)
        pdf.write(5, "- ")
        pdf.set_font("Helvetica", "B", 10)
        pdf.write(5, key)
        pdf.set_font("Helvetica", size=10)
        # URLs e valores longos: quebra na próxima linha com recuo
        if len(value) > 68:
            pdf.ln(5)
            pdf.set_x(pdf.l_margin + 10)
            pdf.multi_cell(0, 5, value, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.write(5, value)
            pdf.ln(5)
    else:
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font("Helvetica", size=10)
        pdf.write(5, "- " + _safe(text))
        pdf.ln(5)


def _embed_image(pdf: _DossiePDF, src: str) -> None:
    """Incorpora imagem a partir de data: URI base64 ou URL remota."""
    try:
        if src.startswith("data:"):
            _header, b64data = src.split(",", 1)
            img_bytes = base64.b64decode(b64data)
        else:
            import httpx
            resp = httpx.get(src, timeout=5.0, follow_redirects=True)
            resp.raise_for_status()
            img_bytes = resp.content
        _ensure_space(pdf, 55)
        pdf.image(io.BytesIO(img_bytes), w=50)
        pdf.ln(3)
    except Exception:
        pass  # imagem inválida ou inacessível — ignora silenciosamente


def _render_markdown(pdf: _DossiePDF, markdown_text: str) -> None:
    """Percorre o markdown linha a linha e renderiza com fpdf2 nativo."""
    for raw_line in markdown_text.split("\n"):
        line = raw_line.strip()

        if not line:
            pdf.ln(2)

        # ── headings ──────────────────────────────────────────────────────────
        elif line.startswith("### "):
            _ensure_space(pdf, 50)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(*_RED)
            pdf.cell(0, 8, _safe(line[4:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

        elif line.startswith("## "):
            _ensure_space(pdf, 20)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(*_NAVY)
            pdf.cell(0, 9, _safe(line[3:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(*_NAVY)
            pdf.set_line_width(0.3)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(5)
            pdf.set_text_color(0, 0, 0)

        elif line.startswith("# "):
            _ensure_space(pdf, 20)
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(*_RED)
            pdf.cell(0, 12, _safe(line[2:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(3)

        # ── separador ─────────────────────────────────────────────────────────
        elif line.startswith("---"):
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.3)
            pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.w - pdf.r_margin, pdf.get_y() + 2)
            pdf.ln(6)

        # ── imagem data: URI embutida pelo dossie_generator ───────────────────
        elif line.startswith("<img"):
            m = re.search(r'src="([^"]+)"', line)
            if m:
                _embed_image(pdf, m.group(1))

        # ── item de lista ─────────────────────────────────────────────────────
        elif line.startswith("- "):
            _render_bullet(pdf, line[2:])

        # ── itálico (rodapé) ──────────────────────────────────────────────────
        elif line.startswith("_") and line.endswith("_"):
            _ensure_space(pdf, 10)
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(*_GRAY)
            pdf.multi_cell(0, 6, _safe(line.strip("_")), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

        # ── linha com negrito inline (**Chave:** valor) ───────────────────────
        elif "**" in line:
            _ensure_space(pdf, 8)
            parts = re.split(r"\*\*(.+?)\*\*", line)
            for i, part in enumerate(parts):
                if not part:
                    continue
                pdf.set_font("Helvetica", "B" if i % 2 == 1 else "", 10)
                pdf.write(6, _safe(part))
            pdf.ln(6)

        # ── texto simples ─────────────────────────────────────────────────────
        else:
            _ensure_space(pdf, 8)
            pdf.set_font("Helvetica", size=10)
            pdf.multi_cell(0, 6, _safe(line), new_x="LMARGIN", new_y="NEXT")


# ─── funções públicas ──────────────────────────────────────────────────────────


def to_bytes(markdown_text: str) -> bytes:
    """
    Converte markdown em PDF e retorna como bytes.

    Raises:
        RuntimeError: se a geração do PDF falhar.
    """
    try:
        pdf = _DossiePDF()
        pdf.set_margins(20, 20, 20)
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        _render_markdown(pdf, markdown_text)
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
