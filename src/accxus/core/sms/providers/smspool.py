from __future__ import annotations

import logging
from typing import Any, ClassVar

from accxus.core.sms.base import AbstractSmsProvider
from accxus.types.core import SmsProviderConfig
from accxus.types.sms import Activation, ActivationStatus, ProviderBalance, ServiceInfo

log = logging.getLogger(__name__)

_BASE = "https://api.smspool.net"


class SmsPoolProvider(AbstractSmsProvider):
    name: ClassVar[str] = "smspool"

    def __init__(self, config: SmsProviderConfig) -> None:
        super().__init__(config)
        self._base = config.base_url.rstrip("/") or _BASE

    async def _post(self, path: str, **data: str | int) -> Any:
        data["key"] = self._api_key
        async with (
            self._session() as sess,
            sess.post(
                f"{self._base}{path}",
                data=data,
                **self._req_kw(),
            ) as resp,
        ):
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def get_balance(self) -> ProviderBalance:
        data = await self._post("/request/balance")
        balance = float(data.get("balance", 0))
        return ProviderBalance(provider=self.name, balance=balance, currency="USD")

    async def get_number(self, service: str, country: int = 0) -> Activation:
        data = await self._post(
            "/purchase/sms",
            country=country,
            service=service,
        )
        if not data.get("success"):
            msg = data.get("message", "unknown error")
            raise RuntimeError(f"[smspool] {msg}")
        order_id = str(data["order_id"])
        phone = str(data.get("phonenumber", ""))
        return Activation(
            id=order_id,
            phone=phone,
            provider=self.name,
            service=service,
            country=country,
        )

    async def get_status(self, activation_id: str) -> tuple[ActivationStatus, str | None]:
        data = await self._post("/sms/check", orderid=activation_id)
        raw = str(data.get("status", "pending")).lower()
        code: str | None = data.get("sms") or data.get("code") or None

        if raw == "completed" and code:
            return ActivationStatus.RECEIVED, code
        if raw in ("cancelled", "refunded"):
            return ActivationStatus.CANCELLED, None
        if raw == "expired":
            return ActivationStatus.EXPIRED, None
        return ActivationStatus.PENDING, None

    async def cancel(self, activation_id: str) -> bool:
        try:
            data = await self._post("/sms/cancel", orderid=activation_id)
            return bool(data.get("success"))
        except Exception as e:
            log.warning(f"[smspool] cancel failed: {e}")
            return False

    async def confirm(self, activation_id: str) -> bool:
        return True

    async def list_services(self, country: int = 0) -> list[ServiceInfo]:
        try:
            data = await self._post("/request/service_list", country=country)
            if not isinstance(data, list):
                return []
            return [
                ServiceInfo(
                    code=str(s.get("sms_pool_code", "")),
                    name=str(s.get("name", "")),
                    price=float(s.get("price", 0)),
                    count=int(s.get("amount", 0)),
                )
                for s in data
            ]
        except Exception as e:
            log.warning(f"[smspool] list_services failed: {e}")
            return []
