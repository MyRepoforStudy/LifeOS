"""Serves the built PWA (web/dist) from the API process.

In production one process answers everything on one origin: /api/* and /health go to
the API, every other GET returns a file of the build or index.html (client-side routes).
"""

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.errors import error_body

# Windows takes MIME types from the registry, where .js is sometimes text/plain;
# browsers refuse module scripts served like that.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/manifest+json", ".webmanifest")

NO_CACHE = {"Cache-Control": "no-cache"}
# Vite puts a content hash in every file name under assets/.
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def mount_web(app: FastAPI, dist: Path | None) -> bool:
    """Register the catch-all route if a build exists. Call after all API routes."""
    if dist is None or not (dist / "index.html").is_file():
        return False
    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def web(path: str) -> FileResponse | JSONResponse:
        if path == "api" or path.startswith("api/"):
            return JSONResponse(status_code=404, content=error_body("not_found", "Not found"))
        if path:
            candidate = (root / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate, headers=IMMUTABLE if path.startswith("assets/") else NO_CACHE)
        return FileResponse(index, headers=NO_CACHE)

    return True
