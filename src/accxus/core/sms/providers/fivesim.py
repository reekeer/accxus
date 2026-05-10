from __future__ import annotations

import logging
from typing import Any, ClassVar

from accxus.core.sms.base import AbstractSmsProvider
from accxus.types.core import SmsProviderConfig
from accxus.types.sms import Activation, ActivationStatus, ProviderBalance, ServiceInfo

log = logging.getLogger(__name__)

_BASE = "https://5sim.net/v1"


class FiveSimProvider(AbstractSmsProvider):
    name: ClassVar[str] = "fivesim"

    def __init__(self, config: SmsProviderConfig) -> None:
        super().__init__(config)
        self._base = config.base_url.rstrip("/") or _BASE
        self._headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    async def _get(self, path: str) -> Any:
        async with (
            self._session() as sess,
            sess.get(
                f"{self._base}{path}",
                headers=self._headers,
                **self._req_kw(),
            ) as resp,
        ):
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def _post(self, path: str) -> Any:
        async with (
            self._session() as sess,
            sess.post(
                f"{self._base}{path}",
                headers=self._headers,
                **self._req_kw(),
            ) as resp,
        ):
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def get_balance(self) -> ProviderBalance:
        data = await self._get("/user/profile")
        return ProviderBalance(
            provider=self.name,
            balance=float(data.get("balance", 0)),
            currency="USD",
        )

    async def get_number(self, service: str, country: int = 0) -> Activation:
        country_str = "russia" if country == 0 else str(country)
        data = await self._get(f"/user/buy/activation/{country_str}/any/{service}")
        act_id = str(data["id"])
        phone = str(data.get("phone", ""))
        return Activation(
            id=act_id,
            phone=phone,
            provider=self.name,
            service=service,
            country=country,
        )

    async def get_status(self, activation_id: str) -> tuple[ActivationStatus, str | None]:
        data = await self._get(f"/user/check/{activation_id}")
        raw = data.get("status", "PENDING").upper()
        sms_list: list[dict[str, Any]] = data.get("sms", [])

        code: str | None = None
        if sms_list:
            code = sms_list[-1].get("code") or sms_list[-1].get("text")

        status_map = {
            "PENDING": ActivationStatus.PENDING,
            "RECEIVED": ActivationStatus.RECEIVED,
            "FINISHED": ActivationStatus.CONFIRMED,
            "CANCELED": ActivationStatus.CANCELLED,
            "CANCELLED": ActivationStatus.CANCELLED,
            "TIMEOUT": ActivationStatus.EXPIRED,
            "BANNED": ActivationStatus.CANCELLED,
        }
        status = status_map.get(raw, ActivationStatus.PENDING)
        return status, code

    async def cancel(self, activation_id: str) -> bool:
        try:
            await self._post(f"/user/cancel/{activation_id}")
            return True
        except Exception as e:
            log.warning(f"[fivesim] cancel failed: {e}")
            return False

    async def confirm(self, activation_id: str) -> bool:
        try:
            await self._post(f"/user/finish/{activation_id}")
            return True
        except Exception as e:
            log.warning(f"[fivesim] confirm failed: {e}")
            return False

    async def list_services(self, country: int = 0) -> list[ServiceInfo]:
        try:
            country_str = "russia" if country == 0 else str(country)
            data = await self._get(f"/guest/products/{country_str}/any")
            return [
                ServiceInfo(
                    code=k,
                    name=k,
                    price=float(v.get("Price", 0)),
                    count=int(v.get("Qty", 0)),
                )
                for k, v in data.items()
            ]
        except Exception as e:
            log.warning(f"[fivesim] list_services failed: {e}")
            return []
