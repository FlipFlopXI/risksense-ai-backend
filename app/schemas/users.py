from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PatientCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    phone_number: str | None = Field(default=None, max_length=30)


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    first_name: str
    last_name: str
    date_of_birth: date | None
    phone_number: str | None