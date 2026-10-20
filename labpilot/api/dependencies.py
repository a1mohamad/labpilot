from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from psycopg_pool import ConnectionPool

from labpilot.llm import LLMClient


def get_client(request: Request) -> LLMClient:
    return request.app.state.client


def get_pool(request: Request) -> ConnectionPool | None:
    return getattr(request.app.state, "pool", None)


LLMClientDep = Annotated[LLMClient, Depends(get_client)]
PoolDep = Annotated[ConnectionPool | None, Depends(get_pool)]
