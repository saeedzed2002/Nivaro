import re
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from nivaro_identity.domain.phone import normalize_phone


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Phone(Input):
    phone: str = Field(max_length=40)

    @field_validator("phone")
    @classmethod
    def normalized(cls, value: str) -> str:
        return normalize_phone(value)


class VerifyCode(Phone):
    challenge_id: UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class ChallengeResponse(BaseModel):
    challenge_id: UUID
    expires_in: int = 120
    resend_after: int = 60
    development_code: str | None = None


class AdminLogin(Input):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("password", mode="before")
    @classmethod
    def exact_password(cls, value: str) -> str:
        return value

    # Password whitespace is significant. Normalize only the email explicitly.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class ProfileEdit(Input):
    name: str = Field(max_length=80)


class Profile(BaseModel):
    id: UUID
    name: str
    phone: str


class SessionResponse(BaseModel):
    profile: Profile
    permissions: list[str]
    expires_at: datetime
    csrf_token: str


class CSRFResponse(BaseModel):
    csrf_token: str


class Logout(Input):
    all_devices: bool = False


class AddressInput(Phone):
    label: str = Field(min_length=1, max_length=40)
    recipient: str = Field(min_length=1, max_length=80)
    country: str = Field(pattern="^[A-Z]{2}$")
    city: str = Field(min_length=1, max_length=80)
    postal_code: str = Field(min_length=1, max_length=20)
    street: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def postal(self) -> Self:
        self.postal_code = self.postal_code.translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )
        if self.country == "IR" and not re.fullmatch("[0-9]{10}", self.postal_code):
            raise ValueError("Iran postal codes require ten digits")
        return self


class AddressEdit(AddressInput):
    version: int = Field(ge=1)


class AddressResponse(AddressInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int


class ErrorDetail(BaseModel):
    code: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class StaffProfile(BaseModel):
    name: str
    email: str
    role: str


class AvatarStatus(BaseModel):
    version: int
    active: UUID | None = None
    candidate: UUID | None = None
    state: str | None = None
    error_code: str | None = None
