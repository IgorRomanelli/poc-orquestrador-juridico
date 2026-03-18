"""
Exportador de PDF: converte markdown em HTML e depois em PDF via WeasyPrint.
Identidade visual: Goulart|Law — Advocacia Especializada.

Duas funções públicas:
    export(markdown_text, output_path) → salva PDF em disco, retorna output_path
    to_bytes(markdown_text)            → retorna bytes do PDF (para st.download_button)
"""

import base64
import os

import markdown as _md

# ─── assets ───────────────────────────────────────────────────────────────────

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _load_logo_b64() -> str:
    """Carrega logo como base64. Retorna string vazia se arquivo não encontrado."""
    logo_path = os.path.join(_ASSETS_DIR, "logo_goulart_law.png")
    try:
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""


_LOGO_B64 = _load_logo_b64()

# ─── CSS — identidade visual Goulart|Law ──────────────────────────────────────

_CSS = """
@page {
    margin: 2.5cm 2cm 3cm 2cm;
    @bottom-center {
        content: "Goulart|Law · Advocacia Especializada  —  " counter(page) " / " counter(pages);
        font-size: 8pt;
        color: #888;
        font-family: "Garamond", Georgia, serif;
    }
}

body {
    font-family: "Garamond", Georgia, "Times New Roman", serif;
    font-size: 11pt;
    line-height: 1.7;
    color: #1a1a1a;
}

.doc-header {
    text-align: center;
    margin-bottom: 1.5em;
    padding-bottom: 1em;
    border-bottom: 2px solid #C00000;
}

.doc-header img {
    height: 80px;
    border: none;
    margin: 0 auto;
    display: block;
}

h1 {
    font-size: 17pt;
    color: #C00000;
    margin-bottom: 0.2em;
    margin-top: 0.6em;
}

h2 {
    font-size: 12pt;
    color: #1A3566;
    margin-top: 1.6em;
    margin-bottom: 0.4em;
    border-bottom: 1px solid #1A3566;
    padding-bottom: 0.15em;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

h3 {
    font-size: 11pt;
    color: #C00000;
    margin-top: 1.2em;
    margin-bottom: 0.3em;
}

p {
    margin: 0.3em 0 0.5em 0;
}

ul, ol {
    margin: 0.3em 0 0.6em 1.4em;
}

li {
    margin-bottom: 0.2em;
}

strong {
    font-weight: bold;
    color: #1a1a1a;
}

em {
    font-style: italic;
    color: #555;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 1.2em 0;
}

a {
    color: #1A3566;
    word-break: break-all;
}

img {
    max-width: 240px;
    max-height: 240px;
    border: 1px solid #ccc;
    margin: 6px 0;
    display: block;
}
"""

# ─── funções internas ──────────────────────────────────────────────────────────


def _to_html(markdown_text: str) -> str:
    body = _md.markdown(markdown_text, extensions=["extra"])
    logo_tag = (
        f'<img src="data:image/png;base64,{_LOGO_B64}" alt="Goulart|Law">'
        if _LOGO_B64
        else "<strong>Goulart|Law · Advocacia Especializada</strong>"
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<style>{_CSS}</style>
</head>
<body>
<div class="doc-header">
  {logo_tag}
</div>
{body}
</body>
</html>"""


# ─── funções públicas ──────────────────────────────────────────────────────────


def export(markdown_text: str, output_path: str) -> str:
    """
    Converte markdown em PDF e salva em output_path.

    Raises:
        RuntimeError: se a geração ou escrita do PDF falhar.
    """
    from weasyprint import HTML

    html = _to_html(markdown_text)
    try:
        HTML(string=html).write_pdf(output_path)
    except Exception as exc:
        raise RuntimeError(f"Erro ao gerar PDF em '{output_path}': {exc}") from exc
    return output_path


def to_bytes(markdown_text: str) -> bytes:
    """
    Converte markdown em PDF e retorna como bytes.
    Usado para st.download_button no Streamlit.

    Raises:
        RuntimeError: se a geração do PDF falhar.
    """
    from weasyprint import HTML

    html = _to_html(markdown_text)
    try:
        return HTML(string=html).write_pdf()
    except Exception as exc:
        raise RuntimeError(f"Erro ao gerar PDF: {exc}") from exc
