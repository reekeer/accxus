from __future__ import annotations

import logging

from pyrogram import Client  # type: ignore[attr-defined]
from pyrogram.errors import (
    FloodWait,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    PhoneNumberUnoccupied,
    SessionPasswordNeeded,
)

from accxus.core.sms.manager import SmsManager
from accxus.platforms.base import AbstractRegistrar, RegResult
from accxus.types.sms import Activation

log = logging.getLogger(__name__)


class TelegramRegistrar(AbstractRegistrar):
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        first_name: str,
        last_name: str,
        sms: SmsManager,
        sms_timeout: int = 120,
        sms_poll: int = 5,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.first_name = first_name
        self.last_name = last_name
        self.sms = sms
        self.sms_timeout = sms_timeout
        self.sms_poll = sms_poll

    def _make_client(self, name: str) -> Client:
        return Client(  # type: ignore[call-arg]
            name=name,
            api_id=self.api_id,
            api_hash=self.api_hash,
            in_memory=True,
            no_updates=True,
        )

    async def register(self, activation: Activation) -> RegResult:  # type: ignore[override]
        phone = f"+{activation.phone}"
        log.info(f"[tg] [{phone}] starting registration")
        client = self._make_client(f"tmp_{activation.id}")

        try:
            await client.connect()
            sent = await client.send_code(phone)

            code = await self.sms.wait_for_code(
                activation, timeout=self.sms_timeout, poll=self.sms_poll
            )
            if not code:
                await self.sms.cancel(activation)
                return RegResult(phone, False, "SMS timeout / no code", platform="telegram")

            log.info(f"[tg] [{phone}] got code: {code}")

            try:
                await client.sign_in(
                    phone_number=phone,
                    phone_code_hash=sent.phone_code_hash,
                    phone_code=code,
                )
            except PhoneNumberUnoccupied:
                await client.sign_up(  # type: ignore[call-arg]
                    phone_number=phone,
                    phone_code_hash=sent.phone_code_hash,
                    first_name=self.first_name,
                    last_name=self.last_name,
                )
            except SessionPasswordNeeded:
                return RegResult(phone, False, "2FA required", platform="telegram")

            session = await client.export_session_string()
            await self.sms.confirm(activation)
            log.info(f"[tg] [{phone}] registered OK")
            return RegResult(phone, True, platform="telegram", session_string=session)

        except FloodWait as e:
            log.warning(f"[tg] [{phone}] FloodWait {e.value}s")
            return RegResult(phone, False, f"FloodWait {e.value}s", platform="telegram")
        except PhoneNumberInvalid:
            await self.sms.cancel(activation)
            return RegResult(phone, False, "PhoneNumberInvalid", platform="telegram")
        except PhoneCodeInvalid:
            return RegResult(phone, False, "PhoneCodeInvalid", platform="telegram")
        except PhoneCodeExpired:
            return RegResult(phone, False, "PhoneCodeExpired", platform="telegram")
        except Exception as e:
            log.exception(f"[tg] [{phone}] unexpected error")
            return RegResult(phone, False, str(e), platform="telegram")
        finally:
            if client.is_connected:
                await client.disconnect()
