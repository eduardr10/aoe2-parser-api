import io
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aoc-parser")

app = FastAPI(title="AoC Recorded Game Parser", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".mgz", ".mgx", ".mgl", ".aoe2record"}


def _summarize(data: bytes) -> dict:
    """Parse usando Summary (máxima compatibilidad)."""
    from mgz.summary import Summary

    try:
        s = Summary(io.BytesIO(data))
    except Exception as e:
        logger.exception("Summary init failed")
        raise HTTPException(status_code=422, detail=f"No se pudo leer la partida: {e}")

    try:
        result = {
            "version": list(s.get_version()) if s.get_version() else None,
            "map": s.get_map(),
            "duration_ms": s.get_duration(),
            "completed": s.get_completed(),
            "players": s.get_players(),
            "settings": s.get_settings(),
            "platform": s.get_platform(),
            "diplomacy": s.get_diplomacy(),
            "teams": [list(t) for t in (s.get_teams() or [])],
            "chat": s.get_chat(),
            "start_time": s.get_start_time(),
            "has_achievements": s.has_achievements(),
            "file_hash": s.get_file_hash(),
        }
        return result
    except Exception as e:
        logger.exception("Summary access failed")
        raise HTTPException(status_code=422, detail=f"Error al leer datos: {e}")


def _summarize_model(data: bytes) -> dict | None:
    """Intenta parsear con model (más datos pero menos compatible)."""
    from mgz.model import parse_match, serialize

    try:
        match = parse_match(io.BytesIO(data))
        return serialize(match)
    except Exception as e:
        logger.warning("Model parser failed, falling back: %s", e)
        return None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "index.html")


@app.post("/parse", summary="Parse an uploaded recorded game file")
async def parse_file(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    data = await file.read()
    result = _summarize_model(data)
    if result is not None:
        return result
    return _summarize(data)


@app.post("/parse-url", summary="Parse a recorded game from a URL")
async def parse_url(url: str = Form(...)):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")
    result = _summarize_model(resp.content)
    if result is not None:
        return result
    return _summarize(resp.content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
