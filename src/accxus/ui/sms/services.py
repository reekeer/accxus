from __future__ import annotations

from rigi import ComposeResult, Widget
from rigi.layout.pane import Card, Pane
from rigi.widgets import Button, DataTable, Label, Select

import accxus.config as cfg
from accxus.core.sms.manager import SmsManager


class SmsServicesTab(Widget):
    DEFAULT_CSS = """
    SmsServicesTab Button {
        min-width: 16;
        height: 3;
    }
    SmsServicesTab Select {
        height: 3;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Pane(
            Card(
                Label("[bold cyan]SMS Services[/bold cyan]"),
                Label("[dim]View available services from SMS providers[/dim]"),
                Label("\n[bold]Provider:[/bold]"),
                Select(
                    id="provider_select",
                    options=[("All Providers", "")],
                    value="",
                ),
                Button("Refresh Services", id="refresh_services_btn", variant="primary"),
                title="  SMS Services",
            ),
            Card(
                DataTable(
                    id="services_table",
                    cursor_type="row",
                    zebra_stripes=True,
                ),
                Label(id="services_status", markup=True),
                title="  Available Services",
            ),
        )

    def on_mount(self) -> None:
        self.run_worker(self._load_providers())

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider_select":
            self.run_worker(self._load_services())

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh_services_btn":
            await self._load_services()

    async def _load_providers(self) -> None:
        manager = SmsManager.from_config(cfg.config.sms_providers)
        providers = manager.active_providers

        if providers:
            await self._load_services()
        else:
            self.query_one("#services_status", Label).update(
                "[yellow]No SMS providers configured. Add API keys in config.[/yellow]"
            )

    def _selected_provider(self) -> str | None:
        value = self.query_one("#provider_select", Select).value
        if not isinstance(value, str) or not value:
            return None
        return value

    async def _load_services(self) -> None:
        table = self.query_one("#services_table", DataTable)
        status = self.query_one("#services_status", Label)
        table.clear(columns=True)
        table.add_columns("Provider", "Service", "Name", "Price", "Available")
        status.update("[dim]Loading services...[/dim]")

        try:
            manager = SmsManager.from_config(cfg.config.sms_providers)
            if not manager.active_providers:
                status.update("[yellow]No active providers configured[/yellow]")
                return

            services_by_provider = await manager.list_services(
                country=0,
                provider=self._selected_provider(),
            )

            total_services = 0
            for provider, services in services_by_provider.items():
                for svc in services:
                    table.add_row(
                        f"[cyan]{provider}[/cyan]",
                        f"[bold]{svc.code}[/bold]",
                        svc.name,
                        f"{svc.price:.2f}",
                        str(svc.count) if svc.count > 0 else "[dim]—[/dim]",
                    )
                    total_services += 1

            if total_services == 0:
                table.add_row(
                    "[dim]—[/dim]",
                    "[dim]No services available[/dim]",
                    "[dim]—[/dim]",
                    "[dim]—[/dim]",
                    "[dim]—[/dim]",
                )
                status.update("[yellow]No services found[/yellow]")
            else:
                status.update(f"[green]Found {total_services} services[/green]")

        except Exception as e:
            status.update(f"[red]Error loading services: {e}[/red]")
            self.notify(f"Failed to load services: {e}", severity="error")
