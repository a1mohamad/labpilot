from __future__ import annotations

# Plain text, every one of them: no loader, and split_recursive already breaks
# on the blank lines between functions. Measured on real Go, JS and Python.
CODE_SUFFIXES = frozenset(
    {
        # JavaScript and TypeScript
        ".js",
        ".mjs",
        ".cjs",
        ".jsx",
        ".ts",
        ".tsx",
        # JVM
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".groovy",
        ".clj",
        # C family
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".cxx",
        ".hpp",
        ".hh",
        # .NET
        ".cs",
        ".fs",
        # systems
        ".go",
        ".rs",
        ".swift",
        ".zig",
        # scripting
        ".py",
        ".rb",
        ".php",
        ".lua",
        ".pl",
        ".pm",
        ".dart",
        ".ex",
        ".exs",
        ".erl",
        ".hs",
        # data science -- .m is MATLAB or Objective-C, both plain text
        ".r",
        ".jl",
        ".m",
        ".sas",
        # shell and query
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".sql",
        # web
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".vue",
        ".svelte",
        # config: this is where a paper's hyperparameters actually live
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
    }
)

# Never readable through ANY door. .env holds API keys, and the rest are
# private keys: reading one means sending it to a model provider.
SECRET_SUFFIXES = frozenset(
    {".env", ".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}
)

DOCUMENT_SUFFIXES = frozenset(
    {".md", ".markdown", ".txt", ".rst", ".ipynb", ".pdf", ".docx"}
)

# Deliberately absent, and each for its own reason:
#   .env   holds API keys and must never reach a provider
#   .json  a dataset is usually .json, and a pretty-printed one has short
#          lines, so the generated-file guard would not catch it
#   .csv .xml   data and generated output, not source
READABLE_SUFFIXES = CODE_SUFFIXES | DOCUMENT_SUFFIXES
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

MAX_FILE_BYTES = 5_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_FILES = 20_000

MAX_ARCHIVE_BYTES = 50_000_000
MAX_UNCOMPRESSED_BYTES = 200_000_000

COPY_CHUNK_BYTES = 65_536

CLONE_TIMEOUT_SECONDS = 300
