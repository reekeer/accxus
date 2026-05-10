from __future__ import annotations


def test_config_loads() -> None:
    import accxus.config as cfg

    assert cfg.SESSIONS_DIR is not None
    assert cfg.DATA_DIR is not None
    assert cfg.TG_API_ID is not None


def test_no_pyrogram_at_import_time() -> None:
    import sys

    for key in list(sys.modules):
        if key.startswith("pyrogram"):
            del sys.modules[key]

    import accxus.ui.app  # noqa: F401 — import side-effect test # pyright: ignore[reportUnusedImport]

    assert "pyrogram" not in sys.modules, (
        "pyrogram was imported at module level — that crashes Python 3.14. "
        "Use lazy imports inside function bodies."
    )


def test_build_app_returns_rigi_app() -> None:
    from rigi import RigiApp

    from accxus.ui.app import _build_app  # pyright: ignore[reportPrivateUsage]

    app = _build_app()
    assert isinstance(app, RigiApp)


def test_proxy_pool_import() -> None:
    from accxus.core.proxy.pool import ProxyPool

    assert ProxyPool is not None


def test_proxy_checker_import() -> None:
    from accxus.core.proxy.checker import ProxyCheckResult, check_proxy

    assert check_proxy is not None
    assert ProxyCheckResult is not None


def test_variables_expand() -> None:
    from accxus.utils.variables import expand

    result = expand("Hello {name}!", name="Alice")
    assert result == "Hello Alice!"


def test_variables_random_token() -> None:
    from accxus.utils.variables import expand

    r1 = expand("{random}")
    r2 = expand("{random}")
    assert len(r1) > 0
    assert r1 != r2
