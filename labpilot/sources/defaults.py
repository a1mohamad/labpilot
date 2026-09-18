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
        # MEASURED 2026-09-18, and it is the one entry here aimed at THIS
        # product's own users. Jupyter writes `.ipynb_checkpoints/<name>-
        # checkpoint.ipynb` beside every notebook it saves - a stale near-copy,
        # not a build artifact, so no other skip rule catches it.
        #
        # On the user's own `titanic` repository a real walk stored 463 chunks
        # of which 181 - 39.1% - were DUPLICATE TEXT, almost all of it the
        # checkpoint and two earlier versions of one notebook. Retrieval then
        # has to choose between several copies of the same answer, and the
        # comparison prompt can be handed the STALE one.
        #
        # This project already knows the shape: `lung` was 34.8% duplicate
        # chunks from mlflow artifact copies and `pydantic` 6.6% from mypy
        # outputs, and both had to be excluded by hand for the measurement.
        # Jupyter's is the case a notebook-first product cannot ask users to
        # exclude by hand.
        ".ipynb_checkpoints",
    }
)

MAX_FILE_BYTES = 5_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_FILES = 20_000

# An archive we accept must be able to REACH us, and 50MB never could: the API
# body limit is 2 x MAX_UPLOAD_BYTES plus overhead, about 10MB. Pinned as an
# xfail since 2026-08-28 because choosing the number before the feature existed
# would have been a guess; slice 7 wired the door, so it is chosen now.
#
# THE ARCHIVE'S NUMBER IS THE ONE THAT MOVES, for a reason that has nothing to
# do with the API: 50MB COMPRESSED against MAX_TOTAL_BYTES of 20MB UNCOMPRESSED
# was never coherent, since source code never expands to less than it packs to.
# The old value could not be reached through the door OR through the walk.
#
# 10MB compressed is a large source-only repository and fits both ceilings.
MAX_ARCHIVE_BYTES = 10_000_000
MAX_UNCOMPRESSED_BYTES = 200_000_000

COPY_CHUNK_BYTES = 65_536

CLONE_TIMEOUT_SECONDS = 300
