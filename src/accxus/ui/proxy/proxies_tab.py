from __future__ import annotations

from rigi import ComposeResult, Widget
from rigi.widgets import TabGroup

from accxus.ui.proxy.add import AddProxyTab
from accxus.ui.proxy.checker import ProxyCheckerTab
from accxus.ui.proxy.view import ViewProxiesTab


class ProxiesTab(Widget):
    DEFAULT_CSS = """
    ProxiesTab {
        height: 100%;
        width: 100%;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield TabGroup(
            [
                ("View", lambda: ViewProxiesTab()),
                ("Add", lambda: AddProxyTab()),
                ("Check", lambda: ProxyCheckerTab()),
            ]
        )
