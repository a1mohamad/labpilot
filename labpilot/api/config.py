from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Read before ApiConfig evaluates os.getenv, and before any provider reads a
# key. override=False so a platform-supplied environment always wins over the
# committed file.
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)


class ApiConfig:
    TITLE = "LabPilot"
    VERSION = "0.1.0"
    SUMMARY = "Explains why two pieces of work produce different results."
    PREFIX = "/api/v1"

    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", "5000000"))

    # Multipart carries two files plus boundaries and headers, so the whole-body
    # ceiling is deliberately larger than twice the per-file one. It exists to
    # bound memory before parsing; the per-file limit is what users are told.
    MULTIPART_OVERHEAD_BYTES: int = 65_536
    MAX_REQUEST_BODY_BYTES: int = int(
        os.getenv(
            "MAX_REQUEST_BODY_BYTES",
            str(2 * MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES),
        )
    )

    # Mounted at /ui only when it exists, so an API-only deployment needs no
    # change. Same origin as the API, which is why CORS can stay empty.
    FRONTEND_DIR: Path = Path(os.getenv("FRONTEND_DIR", PROJECT_ROOT / "web"))

    CORS_ALLOW_ORIGINS: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",")
        if origin.strip()
    )
