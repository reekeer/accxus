from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ActivationStatus(str, Enum):
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Activation(BaseModel):
    id: str
    phone: str
    provider: str
    service: str
    country: int = 0
    status: ActivationStatus = ActivationStatus.PENDING
    code: str | None = None


class ProviderBalance(BaseModel):
    provider: str
    balance: float
    currency: str = "RUB"


class ServiceInfo(BaseModel):
    code: str
    name: str
    price: float = 0.0
    count: int = 0
