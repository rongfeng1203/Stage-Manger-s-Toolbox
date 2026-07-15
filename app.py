from pathlib import Path

from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from backend.app.main import app

_FRONTEND_INDEX = Path(__file__).parent / "public" / "index.html"
_FRONTEND_ASSETS = _FRONTEND_INDEX.parent / "assets"

if _FRONTEND_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_ASSETS), name="frontend-assets")


@app.get("/", include_in_schema=False, response_model=None)
def frontend_index() -> Response:
    if not _FRONTEND_INDEX.exists():
        return RedirectResponse("/index.html", status_code=307)
    return FileResponse(_FRONTEND_INDEX)
