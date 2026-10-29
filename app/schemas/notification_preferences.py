from pydantic import BaseModel, ConfigDict, StrictBool


class NotificationPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_elevated_results: bool


class NotificationPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_elevated_results: StrictBool
