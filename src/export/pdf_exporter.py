"""
Exportador de PDF: converte markdown em HTML e depois em PDF via WeasyPrint.

Duas funções públicas:
    export(markdown_text, output_path) → salva PDF em disco, retorna output_path
    to_bytes(markdown_text)            → retorna bytes do PDF (para st.download_button)
"""

import markdown as _md

_CSS = """
@page {
    margin: 2.5cm 2cm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #666;
    }
}

body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a1a;
}

h1 {
    font-size: 18pt;
    margin-bottom: 0.3em;
    border-bottom: 2px solid #333;
    padding-bottom: 0.2em;
}

h2 {
    font-size: 13pt;
    margin-top: 1.4em;
    margin-bottom: 0.4em;
    border-bottom: 1px solid #aaa;
    padding-bottom: 0.1em;
}

h3 {
    font-size: 11pt;
    margin-top: 1em;
    margin-bottom: 0.2em;
}

p {
    margin: 0.3em 0 0.6em 0;
}

ul, ol {
    margin: 0.3em 0 0.6em 1.5em;
}

li {
    margin-bottom: 0.25em;
}

strong {
    font-weight: bold;
}

em {
    font-style: italic;
    color: #555;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1.2em 0;
}

a {
    color: #1a5276;
    word-break: break-all;
}
"""


def _to_html(markdown_text: str) -> str:
    body = _md.markdown(markdown_text, extensions=["extra"])
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def export(markdown_text: str, output_path: str) -> str:
    """
    Converte markdown em PDF e salva em output_path.

    Args:
        markdown_text: conteúdo markdown do dossiê.
        output_path: caminho do arquivo PDF de saída.

    Returns:
        output_path confirmado.

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

    Args:
        markdown_text: conteúdo markdown do dossiê.

    Returns:
        bytes do PDF gerado.

    Raises:
        RuntimeError: se a geração do PDF falhar.
    """
    from weasyprint import HTML

    html = _to_html(markdown_text)
    try:
        return HTML(string=html).write_pdf()
    except Exception as exc:
        raise RuntimeError(f"Erro ao gerar PDF: {exc}") from exc
