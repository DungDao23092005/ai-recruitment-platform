from __future__ import annotations

import uuid
from contextvars import ContextVar

_workspace_company_id: ContextVar[uuid.UUID | None] = ContextVar(
    "workspace_company_id",
    default=None,
)


def set_workspace_company_id(company_id: uuid.UUID) -> object:
    return _workspace_company_id.set(company_id)


def reset_workspace_company_id(token: object) -> None:
    _workspace_company_id.reset(token)


def get_workspace_company_id() -> uuid.UUID | None:
    return _workspace_company_id.get()
