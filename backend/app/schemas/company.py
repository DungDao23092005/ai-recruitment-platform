import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CompanySize


class CompanyCreate(BaseModel):
    name: str
    slug: str
    tax_code: str
    size: CompanySize


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    tax_code: str
    size: CompanySize
    created_at: datetime
    updated_at: datetime


class CompanyUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    tax_code: str | None = None
    size: CompanySize | None = None
