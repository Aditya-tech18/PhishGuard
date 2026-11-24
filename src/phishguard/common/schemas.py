"""Shared API and Kafka contracts. No implicit label inference."""

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from phishguard.features.url_features import normalize_url


class URLRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, max_length=2048)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return normalize_url(value)


class URLBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[URLRequest] = Field(min_length=1, max_length=32)


class Prediction(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    probability: float = Field(ge=0, le=1)
    verdict: Literal["phishing", "low_risk"]
    model_version: str
    reasons: list[str]
    review_required: bool = False
    coverage_warning: str | None = None
    disclaimer: str = "Model estimate only; low risk does not guarantee safety."


class URLEvent(URLRequest):
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: Literal[1] = 1

    @field_validator("timestamp")
    @classmethod
    def aware_timestamp(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamp must contain a timezone")
        return value.astimezone(timezone.utc)


class ImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: Literal[True]
    image_base64: str = Field(max_length=6700000)

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_boolean_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit boolean true consent is required")
        return value
