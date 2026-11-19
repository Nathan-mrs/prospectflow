"""Estrutura comum das páginas: sidebar fixa, cabeçalho e alternância de tema."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from nicegui import app, events, ui

from app.ui.theme import apply_page_theme


@dataclass(frozen=True, slots=True)
class NavItem:
    key: str
    label: str
    icon: str
    path: str


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("today", "Hoje", "today", "/"),
    NavItem("leads", "Leads", "group", "/leads"),
    NavItem("funnel", "Funil", "view_kanban", "/funil"),
    NavItem("import", "Importar", "upload_file", "/importar"),
    NavItem("dashboard", "Dashboard", "insights", "/dashboard"),
    NavItem("settings", "Configurações", "settings", "/configuracoes"),
)


def _theme_icon(is_dark: bool) -> str:
    return "light_mode" if is_dark else "dark_mode"


@contextmanager
def page_frame(active: str, title: str, subtitle: str | None = None) -> Iterator[ui.column]:
    """Monta sidebar + cabeçalho e devolve a coluna de conteúdo.

    Uso::

        with page_frame("import", "Importar planilha"):
            ui.label("conteúdo")
    """
    apply_page_theme()
    # modo escuro persistido por navegador
    dark = ui.dark_mode(value=app.storage.user.get("dark", False))

    def toggle_theme(e: events.ClickEventArguments) -> None:
        dark.toggle()
        app.storage.user["dark"] = dark.value
        e.sender.props(f"icon={_theme_icon(bool(dark.value))}")

    with ui.left_drawer(value=None, bordered=True).props("width=232 breakpoint=1024") as drawer:
        with ui.row().classes("items-center gap-2 px-3 pt-2 pb-6"):
            with ui.element("div").classes(
                "w-8 h-8 rounded-lg flex items-center justify-center"
            ).style("background: var(--pf-accent)"):
                ui.icon("bolt", color="white", size="20px")
            ui.label("ProspectFlow").classes("text-base font-bold tracking-tight")

        with ui.column().classes("w-full gap-1 px-1"):
            for item in NAV_ITEMS:
                classes = "pf-nav-item w-full" + (" pf-active" if item.key == active else "")
                with ui.link(target=item.path).classes("no-underline w-full"):
                    with ui.row().classes(f"{classes} items-center gap-3 px-3"):
                        ui.icon(item.icon, size="20px")
                        ui.label(item.label).classes("text-sm")

    with ui.header().classes("items-center px-4 py-2 gap-2"):
        ui.button(icon="menu", on_click=drawer.toggle).props("flat round dense").classes("lt-lg")
        ui.space()
        ui.button(icon=_theme_icon(bool(dark.value)), on_click=toggle_theme).props(
            "flat round dense"
        ).tooltip("Alternar tema")

    with ui.column().classes("w-full max-w-6xl mx-auto px-4 sm:px-8 py-6 gap-6") as content:
        with ui.column().classes("gap-1"):
            ui.label(title).classes("pf-title")
            if subtitle:
                ui.label(subtitle).classes("pf-subtitle")
        yield content
