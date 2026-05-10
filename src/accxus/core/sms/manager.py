from __future__ import annotations

import logging
from collections.abc import Mapping

from accxus.core.sms.base import AbstractSmsProvider
from accxus.types.sms import Activation, ActivationStatus, ProviderBalance, ServiceInfo

log = logging.getLogger(__name__)


class SmsManager:
    def __init__(self, providers: list[AbstractSmsProvider]) -> None:
        self._providers = sorted(providers, key=lambda p: p.config.priority)

    @classmethod
    def from_config(cls, provider_configs: Mapping[str, object]) -> SmsManager:
        from accxus.core.sms.providers import (
            FiveSimProvider,
            HeroSmsProvider,
            SmsActivateProvider,
            SmsPoolProvider,
        )
        from accxus.types.core import SmsProviderConfig

        _registry: dict[str, type[AbstractSmsProvider]] = {
            "sms_activate": SmsActivateProvider,
            "herosms": HeroSmsProvider,
            "fivesim": FiveSimProvider,
            "smspool": SmsPoolProvider,
        }

        providers: list[AbstractSmsProvider] = []
        for name, cfg_data in provider_configs.items():
            klass = _registry.get(name)
            if klass is None:
                log.warning(f"[sms_manager] unknown provider {name!r} — skipped")
                continue
            if isinstance(cfg_data, dict):
                cfg: SmsProviderConfig = SmsProviderConfig(**cfg_data)
            elif isinstance(cfg_data, SmsProviderConfig):
                cfg = cfg_data
            else:
                continue
            if not cfg.enabled or not cfg.api_key:
                continue
            providers.append(klass(cfg))

        return cls(providers)

    @property
    def active_providers(self) -> list[AbstractSmsProvider]:
        return list(self._providers)

    async def get_balance_all(self) -> list[ProviderBalance]:
        import asyncio

        async def _one(p: AbstractSmsProvider) -> ProviderBalance | None:
            try:
                return await p.get_balance()
            except Exception as e:
                log.warning(f"[{p.name}] get_balance failed: {e}")
                return None

        results = await asyncio.gather(*(_one(p) for p in self._providers))
        return [r for r in results if r is not None]

    async def get_number(
        self,
        service: str,
        country: int = 0,
        provider: str | None = None,
    ) -> Activation:
        targets = (
            [p for p in self._providers if p.name == provider] if provider else self._providers
        )
        if not targets:
            raise RuntimeError(f"No provider{f' named {provider!r}' if provider else ''} available")
        last_err: Exception = RuntimeError("No providers configured")
        for p in targets:
            try:
                act = await p.get_number(service, country)
                log.info(f"[sms_manager] got number from {p.name}: {act.phone}")
                return act
            except Exception as e:
                log.warning(f"[sms_manager] {p.name} failed: {e}")
                last_err = e
        raise RuntimeError(f"All providers failed. Last: {last_err}") from last_err

    async def get_status(self, activation: Activation) -> tuple[ActivationStatus, str | None]:
        provider = self._find(activation.provider)
        return await provider.get_status(activation.id)

    async def wait_for_code(
        self,
        activation: Activation,
        timeout: int | None = None,
        poll: int | None = None,
    ) -> str | None:
        provider = self._find(activation.provider)
        return await provider.wait_for_code(activation.id, timeout=timeout, poll=poll)

    async def cancel(self, activation: Activation) -> bool:
        provider = self._find(activation.provider)
        return await provider.cancel(activation.id)

    async def confirm(self, activation: Activation) -> bool:
        provider = self._find(activation.provider)
        return await provider.confirm(activation.id)

    async def list_services(
        self, country: int = 0, provider: str | None = None
    ) -> dict[str, list[ServiceInfo]]:
        import asyncio

        targets = (
            [p for p in self._providers if p.name == provider] if provider else self._providers
        )

        async def _one(p: AbstractSmsProvider) -> tuple[str, list[ServiceInfo]]:
            try:
                return p.name, await p.list_services(country)
            except Exception as e:
                log.warning(f"[{p.name}] list_services failed: {e}")
                return p.name, []

        pairs = await asyncio.gather(*(_one(p) for p in targets))
        return dict(pairs)

    def _find(self, name: str) -> AbstractSmsProvider:
        for p in self._providers:
            if p.name == name:
                return p
        raise KeyError(f"Provider {name!r} not found in manager")
