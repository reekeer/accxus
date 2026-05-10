from __future__ import annotations

from rigi import ComposeResult, Widget
from rigi.layout.pane import RigiCard, RigiPane
from rigi.widgets import Button, DataTable, Input, Label, Select, Switch

import accxus.config as cfg
from accxus.core.sms.manager import SmsManager
from accxus.types.core import SmsProviderConfig


class SmsProvidersTab(Widget):
    DEFAULT_CSS = """
    SmsProvidersTab Button {
        min-width: 16;
        height: 3;
    }
    SmsProvidersTab Input {
        height: 3;
        margin-bottom: 1;
    }
    SmsProvidersTab Select {
        height: 3;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield RigiPane(
            RigiCard(
                Label("[bold cyan]SMS Providers[/bold cyan]"),
                Label("[dim]Manage SMS provider configuration[/dim]"),
                Button("Check All Balances", id="check_balances_btn", variant="primary"),
                Button("Refresh", id="refresh_providers_btn", variant="default"),
                title="  SMS Providers",
            ),
            RigiCard(
                DataTable(
                    id="providers_table",
                    cursor_type="row",
                    zebra_stripes=True,
                ),
                title="  Configured Providers",
            ),
            RigiCard(
                Label("[bold]Edit Provider Configuration[/bold]"),
                Label("\n[bold]Provider:[/bold]"),
                Select(
                    id="edit_provider_select",
                    options=[
                        ("SMS Activate", "sms_activate"),
                        ("HeroSMS", "herosms"),
                        ("5sim", "fivesim"),
                        ("SMSPool", "smspool"),
                    ],
                    value="sms_activate",
                ),
                Label("\n[bold]API Key:[/bold]"),
                Input(placeholder="Enter API key", id="provider_api_key", password=True),
                Label("\n[bold]Priority (0-100, lower = higher priority):[/bold]"),
                Input(placeholder="50", id="provider_priority"),
                Label("\n[bold]Timeout (seconds):[/bold]"),
                Input(placeholder="120", id="provider_timeout"),
                Switch(id="provider_enabled", value=True),
                Label("[dim]Enabled[/dim]"),
                Label(""),
                Button("Save Configuration", id="save_provider_btn", variant="success"),
                Button("Disable Provider", id="disable_provider_btn", variant="error"),
                title="  Edit Provider",
            ),
        )

    def on_mount(self) -> None:
        self.run_worker(self._load_providers())

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "edit_provider_select":
            self._load_provider_into_form()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "check_balances_btn":
            await self._check_balances()
        elif event.button.id == "refresh_providers_btn":
            await self._load_providers()
        elif event.button.id == "save_provider_btn":
            await self._save_provider()
        elif event.button.id == "disable_provider_btn":
            await self._disable_provider()

    def _selected_provider_name(self) -> str | None:
        value = self.query_one("#edit_provider_select", Select).value
        return str(value) if isinstance(value, str) else None

    async def _load_providers(self) -> None:
        table = self.query_one("#providers_table", DataTable)
        table.clear(columns=True)
        table.add_columns("Provider", "Status", "Balance", "Priority", "Actions")

        for name, config_data in cfg.config.sms_providers.items():
            config = (
                SmsProviderConfig(**config_data) if isinstance(config_data, dict) else config_data
            )
            status_color = "green" if config.enabled and config.api_key else "red"
            status_text = "✓ Active" if config.enabled and config.api_key else "✗ Inactive"
            has_key = "✓" if config.api_key else "✗ No key"

            table.add_row(
                f"[cyan]{name}[/cyan]",
                f"[{status_color}]{status_text}[/{status_color}]",
                f"[dim]{has_key}[/dim]",
                str(config.priority),
                "[dim]—[/dim]",
            )

        if table.row_count == 0:
            table.add_row(
                "[dim]No providers configured[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
            )

    def _load_provider_into_form(self) -> None:
        provider_name = self._selected_provider_name()
        if not provider_name:
            return
        config_data = cfg.config.sms_providers.get(provider_name)
        if not config_data:
            return
        config = SmsProviderConfig(**config_data) if isinstance(config_data, dict) else config_data
        self.query_one("#provider_api_key", Input).value = config.api_key
        self.query_one("#provider_priority", Input).value = str(config.priority)
        self.query_one("#provider_timeout", Input).value = str(config.timeout)
        self.query_one("#provider_enabled", Switch).value = config.enabled

    async def _save_provider(self) -> None:
        try:
            provider_name = self._selected_provider_name()
            if not provider_name:
                self.notify("Select a provider first", severity="warning")
                return
            api_key = self.query_one("#provider_api_key", Input).value.strip()
            priority_str = self.query_one("#provider_priority", Input).value.strip()
            timeout_str = self.query_one("#provider_timeout", Input).value.strip()
            enabled = self.query_one("#provider_enabled", Switch).value

            priority = int(priority_str) if priority_str else 50
            timeout = int(timeout_str) if timeout_str else 120

            existing = cfg.config.sms_providers.get(provider_name)
            config = (
                SmsProviderConfig(**existing)
                if isinstance(existing, dict)
                else (existing or SmsProviderConfig())
            )
            config.api_key = api_key
            config.priority = priority
            config.timeout = timeout
            config.enabled = enabled

            cfg.config.sms_providers[provider_name] = config
            cfg.save_config(cfg.config)
            self.notify(f"✓ Saved configuration for {provider_name}", severity="information")
            await self._load_providers()
        except Exception as e:
            self.notify(f"Failed to save configuration: {e}", severity="error")

    async def _disable_provider(self) -> None:
        provider_name = self._selected_provider_name()
        if not provider_name:
            self.notify("Select a provider first", severity="warning")
            return
        config_data = cfg.config.sms_providers.get(provider_name)
        if not config_data:
            return
        config = SmsProviderConfig(**config_data) if isinstance(config_data, dict) else config_data
        config.enabled = False
        cfg.config.sms_providers[provider_name] = config
        cfg.save_config(cfg.config)
        self.notify(f"✓ Disabled {provider_name}", severity="information")
        await self._load_providers()

    async def _check_balances(self) -> None:
        self.notify("Checking balances...", timeout=2)
        try:
            manager = SmsManager.from_config(cfg.config.sms_providers)
            if not manager.active_providers:
                self.notify("No active providers configured", severity="warning")
                return

            balances = await manager.get_balance_all()
            if not balances:
                self.notify("All providers failed to respond", severity="error")
                return

            table = self.query_one("#providers_table", DataTable)
            table.clear(columns=True)
            table.add_columns("Provider", "Status", "Balance", "Priority", "Actions")

            balance_map = {b.provider: b for b in balances}
            for name, config_data in cfg.config.sms_providers.items():
                config = (
                    SmsProviderConfig(**config_data)
                    if isinstance(config_data, dict)
                    else config_data
                )
                balance = balance_map.get(name)
                balance_text = (
                    f"[green]{balance.balance:.2f} {balance.currency}[/green]"
                    if balance
                    else "[dim]—[/dim]"
                )
                status_color = "green" if config.enabled and config.api_key else "red"
                status_text = "✓ Active" if config.enabled and config.api_key else "✗ Inactive"

                table.add_row(
                    f"[cyan]{name}[/cyan]",
                    f"[{status_color}]{status_text}[/{status_color}]",
                    balance_text,
                    str(config.priority),
                    "[dim]—[/dim]",
                )

            self.notify(f"✓ Checked {len(balances)} providers", severity="information")
        except Exception as e:
            self.notify(f"Failed to check balances: {e}", severity="error")
