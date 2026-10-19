"""Write the OpenAPI schema to a file without starting the server.

py -m uv run python -m app.export_openapi ../frontend/src/api/openapi.json
"""

import json
import sys
from pathlib import Path

from app.main import app

if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
