from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from labpilot.llm import LLMClient


def get_client(request: Request) -> LLMClient:
    return request.app.state.client


LLMClientDep = Annotated[LLMClient, Depends(get_client)]
