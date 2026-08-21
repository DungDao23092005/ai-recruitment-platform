from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobStatusCount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    count: int


class ApplicationStatusCount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    count: int


class RecruiterMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_jobs: int
    total_applications: int
    jobs_by_status: list[JobStatusCount]
    applications_by_status: list[ApplicationStatusCount]