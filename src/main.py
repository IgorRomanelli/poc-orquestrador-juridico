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


def _extract_domain(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.")


def _to_search_result(raw: dict) -> dict:
    confidence_int = int((raw.get("confidence") or 0.0) * 100)
    if confidence_int >= 80:
        severity = "confirmado"
    elif confidence_int >= 40:
        severity = "suspeito"
    else:
        severity = "inconclusivo"
    page_url = raw.get("page_url", "")
    return {
        "id": str(uuid.uuid4()),
        "thumbnailUrl": raw.get("image_url", ""),
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
    client_name: str
    results: list[dict]


@app.post("/dossie", dependencies=[Depends(_require_secret)])
async def dossie(body: DossieRequest):
    seen: set[str] = set()
    violations: list[dict] = []
    for result in body.results:
        domain = result.get("domain", "")
        if domain not in seen:
            seen.add(domain)
            try:
                lookup_result = await lookup_domain(domain)
            except Exception:
                lookup_result = {"status": "error"}
        else:
            lookup_result = {"status": "error"}
        violations.append({"search_result": result, "lookup": lookup_result})
    markdown = generate_dossie(body.client_name, violations, [], str(date.today()))
    return Response(content=pdf_to_bytes(markdown), media_type="application/pdf")
