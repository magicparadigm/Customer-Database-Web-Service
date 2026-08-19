from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    street: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    """Every field optional — supports PATCH-style partial updates."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    street: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_active: bool | None = None


class CustomerRead(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class CustomerPage(BaseModel):
    """A page of results plus enough metadata to render pagination."""

    items: list[CustomerRead]
    total: int
    page: int
    page_size: int
    total_pages: int
