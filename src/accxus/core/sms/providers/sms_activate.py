from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from accxus.core.sms.base import AbstractSmsProvider
from accxus.types.core import SmsProviderConfig
from accxus.types.sms import Activation, ActivationStatus, ProviderBalance, ServiceInfo

log = logging.getLogger(__name__)

_DEFAULT_URL = "https://api.sms-activate.org/stubs/handler_api.php"


class SmsActivateProvider(AbstractSmsProvider):
    name: ClassVar[str] = "sms_activate"

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

    @staticmethod
    def _check_error(text: str) -> None:
        errors = {
            "BAD_KEY": "Invalid API key",
            "ERROR_SQL": "Provider SQL error",
            "BAD_ACTION": "Unknown action",
            "BAD_SERVICE": "Unknown service",
            "BAD_STATUS": "Unknown status",
            "NO_NUMBERS": "No numbers available",
            "NO_BALANCE": "Insufficient balance",
            "WRONG_OPERATOR": "Wrong operator",
            "NO_ACTIVATION": "Activation not found",
        }
        if text in errors:
            raise RuntimeError(f"[sms_activate] {errors[text]}: {text}")

    async def get_balance(self) -> ProviderBalance:
        text = await self._get(action="getBalance")
        self._check_error(text)
        balance = float(text.split(":")[-1])
        return ProviderBalance(provider=self.name, balance=balance)

    async def get_number(self, service: str, country: int = 0) -> Activation:
        text = await self._get(action="getNumber", service=service, country=country)
        self._check_error(text)
        if not text.startswith("ACCESS_NUMBER:"):
            raise RuntimeError(f"[sms_activate] unexpected response: {text!r}")
        _, act_id, phone = text.split(":", 2)
        return Activation(
            id=act_id,
            phone=phone,
            provider=self.name,
            service=service,
            country=country,
        )

    async def get_status(self, activation_id: str) -> tuple[ActivationStatus, str | None]:
        text = await self._get(action="getStatus", id=activation_id)
        self._check_error(text)
        if text == "STATUS_WAIT_CODE":
            return ActivationStatus.PENDING, None
        if text == "STATUS_WAIT_RESEND":
            return ActivationStatus.PENDING, None
        if text == "STATUS_CANCEL":
            return ActivationStatus.CANCELLED, None
        if text.startswith("STATUS_OK:"):
            code = text.split(":", 1)[1]
            return ActivationStatus.RECEIVED, code
        log.warning(f"[sms_activate] unknown status: {text!r}")
        return ActivationStatus.PENDING, None

    async def cancel(self, activation_id: str) -> bool:
        text = await self._get(action="setStatus", id=activation_id, status=8)
        return text == "ACCESS_CANCEL"

    async def confirm(self, activation_id: str) -> bool:
        text = await self._get(action="setStatus", id=activation_id, status=6)
        return text in ("ACCESS_ACTIVATION", "ACCESS_READY_FOR_RETRY")

    async def list_services(self, country: int = 0) -> list[ServiceInfo]:
        try:
            text = await self._get(action="getPrices", service="", country=country)
            data: dict[str, dict[str, Any]] = json.loads(text)
            out: list[ServiceInfo] = []
            for service_code, countries in data.items():
                info: dict[str, Any] = countries.get(str(country), countries.get("0", {}))
                out.append(
                    ServiceInfo(
                        code=service_code,
                        name=service_code,
                        price=float(info.get("cost", 0)),
                        count=int(info.get("count", 0)),
                    )
                )
            return out
        except Exception as e:
            log.warning(f"[sms_activate] list_services failed: {e}")
            return []

    async def list_countries_for_service(self, service: str) -> list[tuple[int, str, float]]:
        try:
            text = await self._get(action="getPrices", service=service)
            data: dict[str, dict[str, Any]] = json.loads(text)
            prices: dict[int, float] = {}
            for country_str, info in data.get(service, {}).items():
                if int(info.get("count", 0)) > 0:
                    prices[int(country_str)] = float(info.get("cost", 0))
            if not prices:
                return []
            names_text = await self._get(action="getCountries")
            names_data: list[dict[str, Any]] = json.loads(names_text)
            out: list[tuple[int, str, float]] = []
            for item in names_data:
                cid = int(item.get("id", 0))
                if cid in prices:
                    name = item.get("name", f"Country {cid}")
                    out.append((cid, name, prices[cid]))
            return out
        except Exception as e:
            log.warning(f"[sms_activate] list_countries_for_service failed: {e}")
            return []
