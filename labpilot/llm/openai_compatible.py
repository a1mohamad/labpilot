from __future__ import annotations

from dataclasses import dataclass
import logging
import os

import requests

from labpilot.llm._text import truncate
from labpilot.llm.contracts import LLMResult
from labpilot.llm.defaults import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
)
from labpilot.llm.errors import LLMError