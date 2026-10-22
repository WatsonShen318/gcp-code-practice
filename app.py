import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "case.json"

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/")
def read_root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/case")
def read_case():
    # Read on every request so local JSON edits appear after refreshing.
    try:
        with DATA_FILE.open(encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Unable to read data/case.json. Check that the file exists and contains valid JSON.") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="data/case.json must contain a JSON object.")
    return data


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}
