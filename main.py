import io
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aoc-parser")

# --- Parche mgz para save version >= 67.0 (DLC The Last Chieftains) ---
# Basado en https://github.com/happyleavesaoc/aoc-mgz/pull/142
# Parchea los fuentes ANTES de importar mgz
import importlib.util as _iut
_mgz_spec = _iut.find_spec("mgz")
if _mgz_spec and _mgz_spec.origin:
    _mgz_base = Path(_mgz_spec.origin).parent
    _patches = [
        (_mgz_base / "fast" / "header.py", [
            ('if save >= 64.3:\n            data.read(4)\n\n        players.append(dict(',
             'if save >= 64.3:\n            data.read(4)\n        if save >= 67.0:\n            de_string(data)\n\n        players.append(dict('),
            ('if save >= 37:\n            timestamp, x = unpack(\'<II\', data)\n    rms_mod_id',
             'if save >= 37:\n            timestamp, x = unpack(\'<II\', data)\n        if save >= 67.0:\n            data.read(8)\n    rms_mod_id'),
        ]),
        (_mgz_base / "header" / "de.py", [
            (', "unknown_de_64_3" / Int32ul),\n)\n\nstring_block',
             ', "unknown_de_64_3" / Int32ul),\n    If(lambda ctx: find_save_version(ctx) >= 67.0, "unknown_67_0" / de_string),\n)\n\nstring_block'),
            ('Int32ul\n    ))\n)', 'Int32ul\n    )),\n    If(lambda ctx: find_save_version(ctx) >= 67.0, Bytes(8)),\n)'),
        ]),
    ]
    for _fpath, _repls in _patches:
        _content = _fpath.read_text(encoding="utf-8")
        _new = _content
        for _old, _new_text in _repls:
            if _old in _new:
                _new = _new.replace(_old, _new_text, 1)
        if _new != _content:
            _fpath.write_text(_new, encoding="utf-8")

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
        info = _diagnose(data)
        detail = f"No se pudo leer la partida: {e}"
        if info:
            detail += f"\n\nInformación del archivo: save_version={info['save_version']}, game_version={info['game_version']}"
        raise HTTPException(status_code=422, detail=detail)

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


def _diagnose(data: bytes) -> dict | None:
    """Extrae info básica del header sin parse completo."""
    from mgz.fast.header import decompress, parse_version
    from mgz.util import Version
    try:
        header = decompress(io.BytesIO(data))
        version, game, save, log = parse_version(header, data)
        return {
            "version_enum": str(version),
            "game_version": game,
            "save_version": save,
            "log_version": log,
        }
    except Exception:
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


@app.post("/diagnose", summary="Diagnose a file without fully parsing it")
async def diagnose(file: UploadFile = File(...)):
    data = await file.read()
    info = _diagnose(data)
    if not info:
        raise HTTPException(status_code=422, detail="No se pudo leer el header del archivo")
    return info


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
