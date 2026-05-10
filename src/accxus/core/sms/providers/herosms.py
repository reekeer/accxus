from __future__ import annotations

import logging
from typing import ClassVar

from accxus.core.sms.base import AbstractSmsProvider
from accxus.types.core import SmsProviderConfig
from accxus.types.sms import Activation, ActivationStatus, ProviderBalance

log = logging.getLogger(__name__)

_DEFAULT_URL = "https://herosms.ru/stubs/handler_api.php"


class HeroSmsProvider(AbstractSmsProvider):
    name: ClassVar[str] = "herosms"

    def __init__(self, config: SmsProviderConfig) -> None:
        super().__init__(config)
        self._base = config.base_url.rstrip("/") or _DEFAULT_URL

    async def _get(self, **params: str | int) -> str:
        params["api_key"] = self._api_key
        async with (
            self._session() as sess,
            sess.get(self._base, params=params, **self._req_kw()) as resp,
        ):
            resp.raise_for_status()
            return await resp.text()

    async def get_balance(self) -> ProviderBalance:
        text = await self._get(action="getBalance")
        balance = float(text.split(":")[-1]) if ":" in text else 0.0
        return ProviderBalance(provider=self.name, balance=balance)

    async def get_number(self, service: str, country: int = 0) -> Activation:
        text = await self._get(action="getNumber", service=service, country=country)
        if not text.startswith("ACCESS_NUMBER:"):
            raise RuntimeError(f"[herosms] no number: {text!r}")
        _, act_id, phone = text.split(":", 2)
        return Activation(
            id=act_id, phone=phone, provider=self.name, service=service, country=country
        )

    async def get_status(self, activation_id: str) -> tuple[ActivationStatus, str | None]:
        text = await self._get(action="getStatus", id=activation_id)
        if text in ("STATUS_WAIT_CODE", "STATUS_WAIT_RESEND"):
            return ActivationStatus.PENDING, None
        if text == "STATUS_CANCEL":
            return ActivationStatus.CANCELLED, None
        if text.startswith("STATUS_OK:"):
            return ActivationStatus.RECEIVED, text.split(":", 1)[1]
        return ActivationStatus.PENDING, None

    async def cancel(self, activation_id: str) -> bool:
        text = await self._get(action="setStatus", id=activation_id, status=8)
        return "CANCEL" in text

    async def confirm(self, activation_id: str) -> bool:
        text = await self._get(action="setStatus", id=activation_id, status=6)
        return "ACCESS" in text
