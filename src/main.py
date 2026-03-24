import asyncio
import logging
import os
import tempfile
import time
import uuid
from datetime import date
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from src.export.dossie_generator import generate as generate_dossie
from src.export.pdf_exporter import to_bytes as pdf_to_bytes
from src.lookup.orchestrator import lookup_domain
from src.search.full_search import run_full_search

logger = logging.getLogger(__name__)

app = FastAPI(title="Orquestrador de APIs Jurídicas")

_CORS_ORIGIN = os.getenv("CORS_ORIGIN", "https://projeto-alpha.vercel.app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_CORS_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_api_key_header = APIKeyHeader(name="X-API-Secret", auto_error=False)


def _require_secret(api_key: str = Depends(_api_key_header)) -> str:
    secret = os.getenv("API_SECRET", "")
    if not api_key or api_key != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return api_key


jobs: dict[str, dict] = {}

if not os.getenv("API_SECRET"):
    logger.warning("API_SECRET is not set — all requests will be rejected with 401")


def _extract_domain(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.")


def _to_search_result(raw: dict) -> dict:
    raw_confidence = raw.get("confidence")
    # If the source has no native score, fall back to Rekognition similarity (if available).
    # Final fallback: 0.5 (suspeito) — better than hiding a real match as inconclusivo.
    if raw_confidence is None:
        rek = raw.get("confidence_rekognition")
        confidence_float = rek if rek is not None else 0.5
    else:
        confidence_float = raw_confidence
    confidence_int = min(100, int(confidence_float * 100))
    if confidence_int >= 80:
        severity = "confirmado"
    elif confidence_int >= 40:
        severity = "suspeito"
    else:
        severity = "inconclusivo"
    page_url = raw.get("page_url", "")
    thumbnail = raw.get("image_url") or raw.get("preview_thumbnail") or ""
    return {
        "id": str(uuid.uuid4()),
        "thumbnailUrl": thumbnail,
        "domain": _extract_domain(page_url),
        "companyName": "",
        "confidence": confidence_int,
        "severity": severity,
        "contextTag": "anuncio",
        "pageUrl": page_url,
    }


async def _run_search(job_id: str, tmp_path: str, image_bytes: bytes) -> None:
    start = time.monotonic()
    try:
        raw_results = await run_full_search(tmp_path, image_bytes)
        results = [_to_search_result(r) for r in raw_results]
        jobs[job_id] = {
            "status": "done",
            "results": results,
            "total": len(results),
            "search_time_seconds": round(time.monotonic() - start, 2),
        }
    except Exception as exc:
        jobs[job_id] = {"status": "error", "message": str(exc)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/search", dependencies=[Depends(_require_secret)])
async def search(image: UploadFile, background_tasks: BackgroundTasks):
    image_bytes = await image.read()
    suffix = os.path.splitext(image.filename or "image.jpg")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing"}
    background_tasks.add_task(_run_search, job_id, tmp_path, image_bytes)
    return {"job_id": job_id}


@app.get("/status/{job_id}", dependencies=[Depends(_require_secret)])
async def status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/lookup/{domain}", dependencies=[Depends(_require_secret)])
async def lookup(domain: str):
    return await lookup_domain(domain)


class DossieRequest(BaseModel):
    client_name: str = ""
    session_id: str = ""
    user_email: str = ""
    results: list[dict]


@app.post("/dossie", dependencies=[Depends(_require_secret)])
async def dossie(body: DossieRequest):
    logger.info("dossie: received %d results for client=%r", len(body.results), body.client_name)
    try:
        unique_domains = list({r.get("domain", "") for r in body.results if r.get("domain")})
        logger.info("dossie: looking up %d unique domains", len(unique_domains))
        try:
            lookup_results = await asyncio.wait_for(
                asyncio.gather(*[lookup_domain(d) for d in unique_domains], return_exceptions=True),
                timeout=25.0,
            )
        except asyncio.TimeoutError:
            logger.warning("dossie: lookup timed out, proceeding without lookup data")
            lookup_results = [{"status": "error"} for _ in unique_domains]
        lookup_cache = {
            d: (r if not isinstance(r, Exception) else {"status": "error"})
            for d, r in zip(unique_domains, lookup_results)
        }
        for d, r in lookup_cache.items():
            logger.info(
                "dossie: lookup[%s] status=%s cnpj=%s whois_registrant=%s",
                d,
                r.get("status"),
                r.get("cnpj_data", {}).get("cnpj") if isinstance(r.get("cnpj_data"), dict) else "n/a",
                r.get("whois", {}).get("registrant") if isinstance(r.get("whois"), dict) else "n/a",
            )
        violations = [
            {"search_result": r, "lookup": lookup_cache.get(r.get("domain", ""), {"status": "error"})}
            for r in body.results
        ]
        logger.info("dossie: generating markdown for %d violations", len(violations))
        client_name = body.client_name or body.user_email or "não identificado"
        markdown = generate_dossie(client_name, violations, [], str(date.today()))
        logger.info("dossie: rendering PDF (%d chars markdown)", len(markdown))
        pdf_bytes = await asyncio.to_thread(pdf_to_bytes, markdown)
        logger.info("dossie: PDF generated (%d bytes)", len(pdf_bytes))
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as exc:
        logger.exception("dossie: unhandled error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar dossiê: {exc}") from exc
