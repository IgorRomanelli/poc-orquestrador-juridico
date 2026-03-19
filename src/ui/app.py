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

# Bridge: injeta st.secrets no os.environ para que os.getenv() funcione no Streamlit Cloud
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

from src.export.dossie_generator import generate as generate_dossie
from src.export.pdf_exporter import to_bytes as pdf_to_bytes
from src.lookup.orchestrator import lookup_domain
from src.search.aggregator import aggregate, enrich_with_rekognition
from src.search.facecheck_client import search_by_face
from src.search.google_vision_client import search_by_image
from src.search.orchestrator import search_image  # fallback
from src.search.rekognition_client import _is_configured as _rekognition_configured
from src.search.s3_temp_client import _BUCKET as _s3_bucket
from src.search.s3_temp_client import delete_object as _s3_delete
from src.search.s3_temp_client import upload_and_get_url as _s3_upload
from src.search.searchapi_client import _API_KEY as _searchapi_key
from src.search.searchapi_client import search_by_image_url as _searchapi_search
from src.search.serper_client import _API_KEY as _serper_key
from src.search.serper_client import search_by_image_url as _serper_search

from src.ui.helpers import (
    _CLASSIF_PRIORITY,
    _SOCIAL_DOMAINS,
    get_display_image_url as _get_display_image_url,
    is_social as _is_social,
    site_priority as _site_priority,
    sort_results as _sort_results,
)


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
    reko = item.get("confidence_rekognition")

    if conf is not None:
        return f"{int(conf * 100)}% (FaceCheck)"
    if reko is not None:
        return f"{int(reko * 100)}% (Rekognition)"
    return "⚠️ Sem validação facial"


def _source_label(item: dict) -> str:
    source = item.get("source", "")
    if source == "facecheck":
        return "FaceCheck"
    if source == "searchapi":
        return "SearchAPI"
    if source == "serper":
        return "Serper Lens"
    return "Google Vision"


def _render_result_card(item: dict, classifs: dict) -> None:
    url = item.get("page_url", "")
    domain = item.get("domain", "—")
    classification = classifs.get(url, "pendente")
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
            img_url = _get_display_image_url(item)
            if img_url:
                try:
                    st.image(img_url, width=110)
                except Exception:
                    st.caption("🖼️")
            else:
                st.caption("—")

        with col_info:
            st.markdown(f"**Domínio:** {domain}")
            st.markdown(
                f"**URL:** [{url[:80]}...]({url})" if len(url) > 80 else f"**URL:** [{url}]({url})"
            )
            st.caption(f"Fonte: {_source_label(item)} | Confiança: {_confidence_label(item)}")

        with col_btns:
            btn_cols = st.columns(3)
            with btn_cols[0]:
                active = classification == "violacao"
                if st.button("✅ Violação", key=f"v_{url}", type="primary" if active else "secondary", width="stretch"):
                    _classify(url, "violacao")
                    st.rerun()
            with btn_cols[1]:
                active = classification == "nao_violacao"
                if st.button("❌ Não é", key=f"n_{url}", type="primary" if active else "secondary", width="stretch"):
                    _classify(url, "nao_violacao")
                    st.rerun()
            with btn_cols[2]:
                active = classification == "investigar"
                if st.button("🔍 Investigar", key=f"i_{url}", type="primary" if active else "secondary", width="stretch"):
                    _classify(url, "investigar")
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


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
        if st.button("Buscar ocorrências", type="primary", width="content"):
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
                sp_result = {"status": "not_found", "results": [], "requires_manual_review": False, "message": None}

                _searchapi_enabled = bool(_searchapi_key and _s3_bucket)
                _serper_enabled = bool(_serper_key and _s3_bucket)
                ser_result = {"status": "not_found", "results": [], "requires_manual_review": False, "message": None}

                with st.status("🔍 Buscando ocorrências...", expanded=True) as search_status:
                    ph_fc = st.empty()
                    ph_gv = st.empty()
                    ph_fc.info("⏳ FaceCheck: aguardando...")
                    ph_gv.info("⏳ Google Vision: aguardando...")
                    if _searchapi_enabled:
                        ph_sp = st.empty()
                        ph_sp.info("⏳ SearchAPI: aguardando...")
                    if _serper_enabled:
                        ph_ser = st.empty()
                        ph_ser.info("⏳ Serper Lens: aguardando...")

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

                    # Upload S3 único — URL compartilhada por SearchAPI e Serper
                    _shared_image_url = None
                    _shared_s3_key = None
                    if _searchapi_enabled or _serper_enabled:
                        try:
                            _shared_image_url, _shared_s3_key = _s3_upload(uploaded_file.getvalue())
                        except Exception:
                            _shared_image_url = None

                    def _run_searchapi():
                        if not _searchapi_enabled or not _shared_image_url:
                            return sp_result
                        try:
                            return _asyncio.run(_searchapi_search(_shared_image_url))
                        except Exception as exc:
                            return {"status": "error", "results": [], "requires_manual_review": True, "message": str(exc)}

                    def _run_serper():
                        if not _serper_enabled or not _shared_image_url:
                            return ser_result
                        try:
                            return _asyncio.run(_serper_search(_shared_image_url))
                        except Exception as exc:
                            return {"status": "error", "results": [], "requires_manual_review": True, "message": str(exc)}

                    n_workers = 2 + int(_searchapi_enabled) + int(_serper_enabled)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
                        fc_future = executor.submit(_run_fc)
                        gv_future = executor.submit(_run_gv)
                        sp_future = executor.submit(_run_searchapi)
                        ser_future = executor.submit(_run_serper)

                        fc_shown = False
                        gv_shown = False
                        sp_shown = False
                        ser_shown = False
                        while not (fc_future.done() and gv_future.done() and sp_future.done() and ser_future.done()):
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
                            if _searchapi_enabled and sp_future.done() and not sp_shown:
                                sp_result = sp_future.result()
                                n = len(sp_result.get("results", []))
                                ph_sp.success(f"✅ SearchAPI: {n} resultado(s)")
                                sp_shown = True
                            if _serper_enabled and ser_future.done() and not ser_shown:
                                ser_result = ser_future.result()
                                n = len(ser_result.get("results", []))
                                ph_ser.success(f"✅ Serper Lens: {n} resultado(s)")
                                ser_shown = True
                            time.sleep(0.15)

                        if not fc_shown:
                            fc_result = fc_future.result()
                            n = len(fc_result.get("results", []))
                            ph_fc.success(f"✅ FaceCheck: {n} resultado(s)")
                        if not gv_shown:
                            gv_result = gv_future.result()
                            n = len(gv_result.get("results", []))
                            ph_gv.success(f"✅ Google Vision: {n} resultado(s)")
                        if _searchapi_enabled and not sp_shown:
                            sp_result = sp_future.result()
                            n = len(sp_result.get("results", []))
                            ph_sp.success(f"✅ SearchAPI: {n} resultado(s)")
                        if _serper_enabled and not ser_shown:
                            ser_result = ser_future.result()
                            n = len(ser_result.get("results", []))
                            ph_ser.success(f"✅ Serper Lens: {n} resultado(s)")

                    if _shared_s3_key:
                        try:
                            _s3_delete(_shared_s3_key)
                        except Exception:
                            pass

                    result = aggregate(fc_result, gv_result, sp_result, ser_result)

                    if _rekognition_configured and result.get("results"):
                        try:
                            import io
                            from PIL import Image as _PILImage
                            _raw = uploaded_file.getvalue()
                            _img = _PILImage.open(io.BytesIO(_raw)).convert("RGB")
                            _buf = io.BytesIO()
                            _img.save(_buf, format="JPEG", quality=90)
                            source_bytes = _buf.getvalue()
                            result["results"] = _asyncio.run(
                                enrich_with_rekognition(result["results"], source_bytes)
                            )
                        except Exception as _exc:
                            print(f"[REKO] enriquecimento falhou: {_exc}")

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
                options=["facecheck", "google_vision", "searchapi", "serper"],
                default=["facecheck", "google_vision", "searchapi", "serper"],
                format_func=lambda x: {
                    "facecheck": "FaceCheck",
                    "google_vision": "Google Vision",
                    "searchapi": "SearchAPI",
                    "serper": "Serper Lens",
                }.get(x, x),
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

    st.subheader(f"Resultados ({len(filtered_results)} exibidos de {len(results)})")
    st.caption(
        "Classifique cada resultado antes de exportar. "
        "Apenas **Violação** e **Investigar** entrarão no dossiê."
    )

    # Contador de classificações (sobre TODOS os resultados, não só os filtrados)
    classifs = st.session_state.classifications

    filtered_results = _sort_results(filtered_results, classifs)
    n_violacao = sum(1 for v in classifs.values() if v == "violacao")
    n_investigar = sum(1 for v in classifs.values() if v == "investigar")
    st.info(
        f"Classificados: **{n_violacao} violações** | **{n_investigar} para investigar** "
        f"| {len(results) - n_violacao - n_investigar} pendentes"
    )

    classified = [
        r for r in filtered_results
        if classifs.get(r.get("page_url", ""), "pendente") in ("violacao", "investigar")
    ]
    pending = [
        r for r in filtered_results
        if classifs.get(r.get("page_url", ""), "pendente") == "pendente"
    ]
    discarded = [
        r for r in filtered_results
        if classifs.get(r.get("page_url", ""), "pendente") == "nao_violacao"
    ]

    if pending:
        for item in pending:
            _render_result_card(item, classifs)

    if classified:
        with st.expander(f"✅ Classificados ({len(classified)})", expanded=False):
            for item in classified:
                _render_result_card(item, classifs)

    if discarded:
        with st.expander(f"❌ Descartados ({len(discarded)})", expanded=False):
            for item in discarded:
                _render_result_card(item, classifs)

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

                        # Tentar embutir imagem para o PDF (converter tudo para data URI)
                        thumb = item_copy.get("preview_thumbnail") or ""
                        img_url = item_copy.get("image_url") or ""
                        if thumb and not thumb.startswith("data:") and not thumb.startswith("http"):
                            # FaceCheck: base64 bruto → converter para data URI
                            item_copy["preview_thumbnail"] = f"data:image/jpeg;base64,{thumb}"
                        elif thumb and thumb.startswith("http"):
                            # SearchAPI: URL do thumbnail → baixar e converter
                            fetched = _fetch_image_base64(thumb)
                            if fetched:
                                item_copy["preview_thumbnail"] = fetched
                        elif img_url and img_url.startswith("http"):
                            # Google Vision: image_url → baixar e converter
                            fetched = _fetch_image_base64(img_url)
                            if fetched:
                                item_copy["preview_thumbnail"] = fetched

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
                        st.markdown(markdown_text, unsafe_allow_html=True)
