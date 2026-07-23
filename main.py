import io
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from mgz.model import parse_match, serialize

app = FastAPI(title="AoC Recorded Game Parser", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".mgz", ".mgx", ".mgl", ".aoe2record"}


def _parse(data: bytes) -> dict:
    try:
        match = parse_match(io.BytesIO(data))
        return serialize(match)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


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
    return _parse(data)


@app.post("/parse-url", summary="Parse a recorded game from a URL")
async def parse_url(url: str = Form(...)):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")
    return _parse(resp.content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
