"""Páginas da aplicação e registro de rotas."""

from __future__ import annotations

from nicegui import ui

from app.ui.pages.dashboard import dashboard_page
from app.ui.pages.funnel import funnel_page
from app.ui.pages.importer import import_page
from app.ui.pages.leads import leads_page
from app.ui.pages.settings import settings_page
from app.ui.pages.today import today_page

ROUTES = (
    ("/", "Hoje", today_page),
    ("/leads", "Leads", leads_page),
    ("/funil", "Funil", funnel_page),
    ("/importar", "Importar", import_page),
    ("/dashboard", "Dashboard", dashboard_page),
    ("/configuracoes", "Configurações", settings_page),
)


def register_routes() -> None:
    """Registra todas as rotas no NiceGUI (chamado pelo ``app.main``)."""
    for path, title, builder in ROUTES:
        ui.page(path, title=f"{title} · ProspectFlow")(builder)
