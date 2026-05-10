from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProxyConfig(BaseModel):
    name: str = ""
    country: str = ""
    country_code: str = ""
    exit_ip: str = ""
    latency_ms: float = 0.0
    scheme: Literal["socks4", "socks5", "http", "https"] = "socks5"
    host: str
    port: int = Field(ge=1, le=65535)
    username: str = ""
    password: str = ""

    @property
    def flag(self) -> str:
        code = self.country_code.strip().upper()
        if len(code) != 2 or not code.isalpha():
            return "🌐"
        return "".join(chr(ord(char) + 127397) for char in code)

    @property
    def country_label(self) -> str:
        country = self.country.strip() or "Unknown"
        return f"{self.flag} {country}"

    @property
    def display_name(self) -> str:
        return self.name.strip() or self.country_label

    def to_url(self) -> str:
        if self.username:
            return f"{self.scheme}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"

    def to_pyrogram(self) -> dict[str, Any]:
        d: dict[str, Any] = {"scheme": self.scheme, "hostname": self.host, "port": self.port}
        if self.username:
            d["username"] = self.username
        if self.password:
            d["password"] = self.password
        return d

    def to_aiohttp_kwargs(self) -> dict[str, Any]:
        import aiohttp

        if self.scheme in ("http", "https"):
            kw: dict[str, Any] = {"proxy": f"http://{self.host}:{self.port}"}
            if self.username:
                kw["proxy_auth"] = aiohttp.BasicAuth(self.username, self.password)
            return kw
        return {"proxy": self.to_url()}


class SmsProviderConfig(BaseModel):
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    priority: int = Field(default=50, ge=0, le=100)
    proxy: ProxyConfig | None = None
    country: int = 0
    timeout: int = 120
    poll: int = 5


class AppConfig(BaseModel):
    tg_api_id: int = 12345
    tg_api_hash: str = "your_api_hash"
    tg_app_version: str = "6.3.10 x64"
    tg_device_model: str = "Telegram Desktop"
    tg_system_version: str = "Windows 11"
    telegram_proxy: ProxyConfig | None = None
    proxies: list[ProxyConfig] = Field(default_factory=list)

    sms_providers: dict[str, SmsProviderConfig] = Field(
        default_factory=lambda: {
            "sms_activate": SmsProviderConfig(priority=10),
            "herosms": SmsProviderConfig(priority=20),
            "fivesim": SmsProviderConfig(priority=30),
            "smspool": SmsProviderConfig(priority=40),
        }
    )

    @field_validator("tg_api_id", mode="before")
    @classmethod
    def _coerce_api_id(cls, v: object) -> int:
        return int(v)  # type: ignore[arg-type]
