"""
Interface Streamlit — POC Orquestrador de APIs Jurídicas.

Fluxo:
    1. Sidebar: campo "Nome do cliente"
    2. Upload de foto
    3. Botão "Buscar" → search_image() → exibe resultados
    4. Por resultado: botões Violação / Não é violação / Investigar
    5. Botão "Exportar Dossiê PDF" → lookup de domínios marcados → gera markdown → PDF

Como rodar:
    cd poc-orquestrador
    streamlit run src/ui/app.py
"""

import asyncio
import os
import sys
import tempfile
from datetime import date

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()

from src.export.dossie_generator import generate as generate_dossie
from src.export.pdf_exporter import to_bytes as pdf_to_bytes
from src.lookup.orchestrator import lookup_domain
from src.search.orchestrator import search_image


# ─── configuração da página ────────────────────────────────────────────────────

st.set_page_config(
    page_title="Buscador de Imagem Jurídico",
    page_icon="⚖️",
    layout="wide",
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Executa coroutine em contexto síncrono (Streamlit não é async)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _confidence_label(item: dict) -> str:
    conf = item.get("confidence")
    if conf is None:
        return "—"
    return f"{int(conf * 100)}%"


def _source_label(item: dict) -> str:
    source = item.get("source", "")
    return "FaceCheck" if source == "facecheck" else "Google Vision"


def _init_classifications(results: list):
    """Inicializa estado de classificações na primeira busca."""
    if "classifications" not in st.session_state:
        st.session_state.classifications = {}
    for item in results:
        key = item.get("page_url", "")
        if key not in st.session_state.classifications:
            st.session_state.classifications[key] = "pendente"


def _classify(url: str, label: str):
    st.session_state.classifications[url] = label


# ─── sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚖️ Dossiê Jurídico")
    st.markdown("---")
    client_name = st.text_input(
        "Nome do cliente",
        placeholder="Ex: João da Silva",
        help="Aparecerá no cabeçalho do dossiê exportado.",
    )
    st.markdown("---")
    st.caption("POC — uso restrito a casos encerrados")


# ─── área principal ────────────────────────────────────────────────────────────

st.title("Buscador de Imagem Jurídico")
st.markdown("Faça upload da foto do cliente para localizar usos não autorizados na internet.")

uploaded_file = st.file_uploader(
    "Foto do cliente",
    type=["jpg", "jpeg", "png", "webp"],
    help="Formatos aceitos: JPG, PNG, WebP.",
)

if uploaded_file:
    col_img, col_btn = st.columns([1, 3])
    with col_img:
        st.image(uploaded_file, width=160, caption="Foto carregada")
    with col_btn:
        if st.button("Buscar ocorrências", type="primary", use_container_width=False):
            with st.spinner("Buscando em FaceCheck e Google Vision..."):
                # Salvar arquivo temporariamente para os clientes (precisam de path)
                suffix = os.path.splitext(uploaded_file.name)[-1] or ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name

                try:
                    result = _run_async(search_image(tmp_path))
                finally:
                    os.unlink(tmp_path)

            st.session_state.search_result = result
            st.session_state.classifications = {}
            st.rerun()

# ─── resultados ───────────────────────────────────────────────────────────────

if "search_result" in st.session_state:
    result = st.session_state.search_result
    results = result.get("results", [])

    _init_classifications(results)

    # Métricas de resumo
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Resultados", result.get("total_deduplicated", len(results)))
    col2.metric("Domínios", len(result.get("domains", [])))
    col3.metric("Tempo", f"{result.get('search_time_seconds', 0):.1f}s")
    status = result.get("status", "—")
    col4.metric("Status", status.upper())

    if result.get("requires_manual_review"):
        st.warning("Revisão manual recomendada — uma das fontes retornou dados parciais.")

    st.markdown("---")

    # ─── filtros ──────────────────────────────────────────────────────────────
    with st.expander("Filtros", expanded=False):
        fcol1, fcol2, fcol3 = st.columns([2, 3, 1])
        with fcol1:
            filter_sources = st.multiselect(
                "Fonte",
                options=["facecheck", "google_vision"],
                default=["facecheck", "google_vision"],
                format_func=lambda x: "FaceCheck" if x == "facecheck" else "Google Vision",
            )
        with fcol2:
            conf_range = st.slider("Confiança (%)", 0, 100, (0, 100), step=1)
        with fcol3:
            include_no_conf = st.checkbox("Sem confiança", value=True,
                                          help="Incluir resultados sem valor de confiança (geralmente Google Vision)")

    conf_min = conf_range[0] / 100
    conf_max = conf_range[1] / 100

    def _passes_filter(item: dict) -> bool:
        if item.get("source") not in filter_sources:
            return False
        conf = item.get("confidence")
        if conf is None:
            return include_no_conf
        return conf_min <= conf <= conf_max

    filtered_results = [r for r in results if _passes_filter(r)]

    st.subheader(f"Resultados ({len(filtered_results)} exibidos de {len(results)})")
    st.caption(
        "Classifique cada resultado antes de exportar. "
        "Apenas **Violação** e **Investigar** entrarão no dossiê."
    )

    # Contador de classificações (sobre TODOS os resultados, não só os filtrados)
    classifs = st.session_state.classifications
    n_violacao = sum(1 for v in classifs.values() if v == "violacao")
    n_investigar = sum(1 for v in classifs.values() if v == "investigar")
    st.info(
        f"Classificados: **{n_violacao} violações** | **{n_investigar} para investigar** "
        f"| {len(results) - n_violacao - n_investigar} pendentes"
    )

    for item in filtered_results:
        url = item.get("page_url", "")
        domain = item.get("domain", "—")
        classification = classifs.get(url, "pendente")

        # Cor de fundo por classificação
        border_color = {
            "violacao": "#e74c3c",
            "investigar": "#f39c12",
            "nao_violacao": "#27ae60",
            "pendente": "#bdc3c7",
        }.get(classification, "#bdc3c7")

        with st.container():
            st.markdown(
                f'<div style="border-left: 4px solid {border_color}; padding-left: 12px; margin-bottom: 8px;">',
                unsafe_allow_html=True,
            )

            col_info, col_btns = st.columns([3, 2])

            with col_info:
                st.markdown(f"**Domínio:** {domain}")
                st.markdown(f"**URL:** [{url[:80]}...]({url})" if len(url) > 80 else f"**URL:** [{url}]({url})")
                st.caption(
                    f"Fonte: {_source_label(item)} | Confiança: {_confidence_label(item)}"
                )

            with col_btns:
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    active = classification == "violacao"
                    if st.button(
                        "✅ Violação" if not active else "✅ *Violação*",
                        key=f"v_{url}",
                        type="primary" if active else "secondary",
                        use_container_width=True,
                    ):
                        _classify(url, "violacao")
                        st.rerun()
                with btn_cols[1]:
                    active = classification == "nao_violacao"
                    if st.button(
                        "❌ Não é",
                        key=f"n_{url}",
                        type="primary" if active else "secondary",
                        use_container_width=True,
                    ):
                        _classify(url, "nao_violacao")
                        st.rerun()
                with btn_cols[2]:
                    active = classification == "investigar"
                    if st.button(
                        "🔍 Investigar",
                        key=f"i_{url}",
                        type="primary" if active else "secondary",
                        use_container_width=True,
                    ):
                        _classify(url, "investigar")
                        st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

    # ─── exportação ───────────────────────────────────────────────────────────

    st.markdown("---")
    st.subheader("Exportar Dossiê")

    if n_violacao == 0 and n_investigar == 0:
        st.info("Classifique pelo menos um resultado como **Violação** ou **Investigar** para exportar.")
    else:
        if not client_name.strip():
            st.warning("Preencha o **Nome do cliente** na barra lateral antes de exportar.")
        else:
            if st.button("Gerar Dossiê PDF", type="primary"):
                with st.spinner("Consultando dados dos responsáveis..."):
                    # Coletar domínios únicos dos itens marcados
                    marked_items = [
                        item for item in results
                        if classifs.get(item.get("page_url", "")) in ("violacao", "investigar")
                    ]
                    unique_domains = list({item.get("domain", "") for item in marked_items if item.get("domain")})

                    # Lookup em paralelo só para domínios marcados
                    async def _lookup_all():
                        tasks = [lookup_domain(d) for d in unique_domains]
                        return await asyncio.gather(*tasks, return_exceptions=True)

                    lookup_results = _run_async(_lookup_all())
                    domain_lookup = {}
                    for domain, lr in zip(unique_domains, lookup_results):
                        if isinstance(lr, Exception):
                            domain_lookup[domain] = {}
                        else:
                            domain_lookup[domain] = lr

                with st.spinner("Gerando dossiê..."):
                    violations_data = []
                    investigate_data = []

                    for item in marked_items:
                        domain = item.get("domain", "")
                        enriched = {
                            "search_result": item,
                            "lookup": domain_lookup.get(domain, {}),
                        }
                        label = classifs.get(item.get("page_url", ""))
                        if label == "violacao":
                            violations_data.append(enriched)
                        else:
                            investigate_data.append(enriched)

                    today = str(date.today())
                    markdown_text = generate_dossie(
                        client_name=client_name,
                        violations=violations_data,
                        investigate=investigate_data,
                        date=today,
                    )

                    pdf_bytes = pdf_to_bytes(markdown_text)

                filename = f"dossie_{client_name.lower().replace(' ', '_')}_{today}.pdf"
                st.download_button(
                    label="Baixar Dossiê PDF",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    type="primary",
                )

                with st.expander("Pré-visualizar markdown do dossiê"):
                    st.markdown(markdown_text)
