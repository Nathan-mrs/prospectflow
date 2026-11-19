"""Ponto de entrada do ProspectFlow.

Uso::

    python -m app.main
"""

from __future__ import annotations

from nicegui import app, ui

from app.config import get_settings
from app.db import get_engine, init_db, session_scope
from app.scheduler import start_scheduler, stop_scheduler
from app.services.bootstrap import ensure_defaults
from app.ui.pages import register_routes
from app.ui.theme import install_theme


def _startup() -> None:
    """Cria o schema e os dados padrão (nichos, templates, metas)."""
    init_db(get_engine())
    with session_scope() as session:
        ensure_defaults(session)
    start_scheduler()


def main() -> None:
    """Configura e inicia o servidor."""
    settings = get_settings()
    app.on_startup(_startup)
    app.on_shutdown(stop_scheduler)
    install_theme()
    register_routes()
    ui.run(
        title="ProspectFlow",
        host=settings.host,
        port=settings.port,
        storage_secret=settings.storage_secret,
        reload=settings.debug,
        show=False,
        language="pt-BR",
        favicon="⚡",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
