from __future__ import annotations

READABLE_SUFFIXES = frozenset({".py", ".md", ".markdown", ".txt", ".rst"})

SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "site-packages",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        "target",
        ".next",
        ".tox",
        ".eggs",
        ".idea",
        ".vscode",
    }
)

MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_FILES = 20_000

MAX_ARCHIVE_BYTES = 50_000_000
MAX_UNCOMPRESSED_BYTES = 200_000_000

COPY_CHUNK_BYTES = 65_536

CLONE_TIMEOUT_SECONDS = 300
