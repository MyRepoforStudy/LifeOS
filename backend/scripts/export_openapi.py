"""Write the OpenAPI schema to backend/openapi.json (the web client generates its types from it).

    .venv\\Scripts\\python scripts\\export_openapi.py
"""

import json
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# The schema does not depend on real settings; placeholders keep the script runnable anywhere.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder@localhost/placeholder")
os.environ.setdefault("JWT_SECRET", "placeholder-secret-for-schema-export-only")

from app.main import create_app  # noqa: E402

schema = create_app().openapi()
target = BACKEND_DIR / "openapi.json"
target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {target} ({len(schema['paths'])} paths)")
