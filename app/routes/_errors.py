"""Route helpers for mapping service errors to HTTP exceptions."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.services.errors import ServiceError


T = TypeVar("T")


async def run_service(call: Callable[[], Awaitable[T]]) -> T:
    try:
        return await call()
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
