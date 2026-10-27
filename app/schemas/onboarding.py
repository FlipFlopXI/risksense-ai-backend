from pydantic import BaseModel, ConfigDict, Field, model_validator


class OnboardingDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ethnicity: str | None = Field(default=None, max_length=100)
    height_cm: float = Field(ge=100, le=250, allow_inf_nan=False)
    weight_kg: float = Field(ge=25, le=350, allow_inf_nan=False)
    waist_circumference_cm: float | None = Field(default=None, ge=40, le=250, allow_inf_nan=False)
    smoking_status: str = Field(pattern=r"^(Never|Former|Current)$")
    activity_level: str = Field(pattern=r"^(Sedentary|Light|Moderate|Active)$")
    alcohol_status: str = Field(pattern=r"^(None|Occasional|Regular|Prefer not to say)$")
    family_history_diabetes: bool | None
    family_history_heart_disease: bool | None
    family_history_hypertension: bool | None
    has_chronic_condition: bool
    chronic_conditions: str | None = Field(default=None, max_length=1000)
    chronic_medications: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_chronic(self):
        self.ethnicity = self.ethnicity.strip() or None if self.ethnicity else None
        self.chronic_conditions = self.chronic_conditions.strip() or None if self.chronic_conditions else None
        self.chronic_medications = self.chronic_medications.strip() or None if self.chronic_medications else None
        if self.has_chronic_condition and not self.chronic_conditions:
            raise ValueError("Describe the chronic condition when selected.")
        if not self.has_chronic_condition and (self.chronic_conditions or self.chronic_medications):
            raise ValueError("Chronic conditions and medication require the chronic condition option.")
        return self


class OnboardingContext(BaseModel):
    completed: bool
    existing: dict


class OnboardingResult(BaseModel):
    saved: bool
