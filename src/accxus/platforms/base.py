from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RegResult:
    phone: str
    success: bool
    error: str | None = None
    session_string: str | None = None
    platform: str = ""


class AbstractRegistrar(ABC):
    @abstractmethod
    async def register(self, activation: object) -> RegResult: ...
