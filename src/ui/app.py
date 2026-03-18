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
import base64
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
from src.search.aggregator import aggregate
from src.search.facecheck_client import search_by_face
from src.search.google_vision_client import search_by_image
from src.search.orchestrator import search_image  # fallback

_SOCIAL_DOMAINS = frozenset({
    "instagram.com", "facebook.com", "twitter.com", "x.com",
    "tiktok.com", "youtube.com", "pinterest.com", "linkedin.com",
    "reddit.com", "snapchat.com", "tumblr.com", "flickr.com",
    "threads.net", "vk.com", "t.me",
})


def _is_social(item: dict) -> bool:
    """Retorna True se o domínio pertence a uma rede social conhecida."""
    domain = item.get("domain", "").lower()
    return any(social in domain for social in _SOCIAL_DOMAINS)


def _site_priority(item: dict) -> int:
    """
    Prioridade de ordenação por tipo de site.
    0 = site comercial / Google Maps (maior relevância jurídica)
    1 = rede social (menor relevância)
    """
    return 1 if _is_social(item) else 0


_CLASSIF_PRIORITY = {"pendente": 0, "violacao": 1, "investigar": 2, "nao_violacao": 3}


# ─── configuração da página ────────────────────────────────────────────────────

st.set_page_config(
    page_title="Buscador de Imagem Jurídico",
    page_icon="⚖️",
    layout="wide",
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Executa coroutine em contexto síncrono (Streamlit não é async)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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


def _fetch_image_base64(url: str) -> str | None:
    """
    Baixa imagem de uma URL e retorna como data URL base64.
    Retorna None se a URL não for acessível ou não for uma imagem.
    Timeout de 8s para não travar a geração do dossiê.
    """
    if not url:
        return None
    try:
        import httpx
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            return None
        b64 = base64.b64encode(resp.content).decode()
        return f"data:{content_type};base64,{b64}"
    except Exception:
        return None


def _passes_filter(
    item: dict,
    filter_sources: list,
    conf_min: float,
    conf_max: float,
    include_no_conf: bool,
    hide_social: bool = False,
) -> bool:
    if item.get("source") not in filter_sources:
        return False
    if hide_social and _is_social(item):
        return False
    conf = item.get("confidence")
    if conf is None:
        return include_no_conf
    return conf_min <= conf <= conf_max


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
            suffix = os.path.splitext(uploaded_file.name)[-1] or ".jpg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name

            try:
                import asyncio as _asyncio
                import concurrent.futures
                import time

                _err = {"status": "error", "results": [], "message": "não executado"}
                fc_result = _err
                gv_result = _err

                with st.status("🔍 Buscando ocorrências...", expanded=True) as search_status:
                    ph_fc = st.empty()
                    ph_gv = st.empty()
                    ph_fc.info("⏳ FaceCheck: aguardando...")
                    ph_gv.info("⏳ Google Vision: aguardando...")

                    def _run_fc():
                        try:
                            return _asyncio.run(search_by_face(tmp_path))
                        except Exception as exc:
                            return {"status": "error", "results": [], "message": str(exc)}

                    def _run_gv():
                        try:
                            return _asyncio.run(search_by_image(tmp_path))
                        except Exception as exc:
                            return {"status": "error", "results": [], "message": str(exc)}

                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                        fc_future = executor.submit(_run_fc)
                        gv_future = executor.submit(_run_gv)

                        fc_shown = False
                        gv_shown = False
                        while not (fc_future.done() and gv_future.done()):
                            if fc_future.done() and not fc_shown:
                                fc_result = fc_future.result()
                                n = len(fc_result.get("results", []))
                                ph_fc.success(f"✅ FaceCheck: {n} resultado(s)")
                                fc_shown = True
                            if gv_future.done() and not gv_shown:
                                gv_result = gv_future.result()
                                n = len(gv_result.get("results", []))
                                ph_gv.success(f"✅ Google Vision: {n} resultado(s)")
                                gv_shown = True
                            time.sleep(0.15)

                        if not fc_shown:
                            fc_result = fc_future.result()
                            n = len(fc_result.get("results", []))
                            ph_fc.success(f"✅ FaceCheck: {n} resultado(s)")
                        if not gv_shown:
                            gv_result = gv_future.result()
                            n = len(gv_result.get("results", []))
                            ph_gv.success(f"✅ Google Vision: {n} resultado(s)")

                    result = aggregate(fc_result, gv_result)
                    total = result.get("total_deduplicated", 0)
                    search_status.update(
                        label=f"✅ {total} resultado(s) encontrado(s)",
                        state="complete",
                        expanded=False,
                    )

            except Exception as exc:
                st.error(f"Erro na busca de imagem: {exc}")
                result = None
            finally:
                os.unlink(tmp_path)

            if result is not None:
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
        fcol1, fcol2, fcol3, fcol4 = st.columns([2, 3, 1, 1])
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
        with fcol4:
            hide_social = st.checkbox(
                "Ocultar redes sociais",
                value=True,
                help="Remove Instagram, Facebook, TikTok etc. — foca em sites e Google Maps.",
            )

    conf_min = conf_range[0] / 100
    conf_max = conf_range[1] / 100

    filtered_results = [
        r for r in results
        if _passes_filter(r, filter_sources, conf_min, conf_max, include_no_conf, hide_social)
    ]
    filtered_results = sorted(
        filtered_results,
        key=lambda r: (
            _CLASSIF_PRIORITY.get(classifs.get(r.get("page_url", ""), "pendente"), 0),
            _site_priority(r),
        ),
    )

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

            col_thumb, col_info, col_btns = st.columns([1, 2.5, 2])

            with col_thumb:
                img_url = item.get("image_url", "")
                if img_url:
                    try:
                        st.image(img_url, width=110, use_container_width=False)
                    except Exception:
                        st.caption("🖼️")
                else:
                    st.caption("—")

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
                        "✅ Violação",
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
                    for d, lr in zip(unique_domains, lookup_results):
                        if isinstance(lr, Exception):
                            domain_lookup[d] = {}
                        else:
                            domain_lookup[d] = lr

                with st.spinner("Gerando dossiê (buscando imagens)..."):
                    violations_data = []
                    investigate_data = []

                    for item in marked_items:
                        domain = item.get("domain", "")
                        item_copy = dict(item)

                        # Tentar embutir imagem para o PDF
                        img_url = item_copy.get("image_url", "")
                        if img_url and not item_copy.get("preview_thumbnail"):
                            thumbnail = _fetch_image_base64(img_url)
                            if thumbnail:
                                item_copy["preview_thumbnail"] = thumbnail

                        enriched = {
                            "search_result": item_copy,
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

                    try:
                        pdf_bytes = pdf_to_bytes(markdown_text)
                    except RuntimeError as exc:
                        st.error(str(exc))
                        pdf_bytes = None

                if pdf_bytes is not None:
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
