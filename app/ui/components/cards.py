"""Cartões de métrica e estados vazios."""

from __future__ import annotations

from nicegui import ui


def stat_card(label: str, value: str | int, icon: str, color: str = "var(--pf-accent)",
              hint: str | None = None) -> ui.element:
    """Cartão compacto com ícone, valor e rótulo."""
    with ui.element("div").classes("pf-card p-4 flex items-center gap-4 min-w-0") as card:
        with ui.element("div").classes(
            "w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        ).style(f"background: color-mix(in srgb, {color} 14%, transparent); color: {color}"):
            ui.icon(icon, size="22px")
        with ui.column().classes("gap-0 min-w-0"):
            ui.label(str(value)).classes("text-2xl font-bold leading-tight")
            ui.label(label).classes("text-sm pf-muted truncate")
            if hint:
                ui.label(hint).classes("text-xs pf-muted")
    return card


def empty_state(icon: str, title: str, message: str,
                action_label: str | None = None, on_action: object = None) -> ui.element:
    """Estado vazio centralizado com ícone, texto e ação opcional."""
    with ui.element("div").classes(
        "pf-card w-full py-14 px-6 flex flex-col items-center text-center gap-3"
    ) as box:
        with ui.element("div").classes(
            "w-14 h-14 rounded-2xl flex items-center justify-center"
        ).style("background: var(--pf-accent-soft); color: var(--pf-accent)"):
            ui.icon(icon, size="28px")
        ui.label(title).classes("text-lg font-semibold")
        ui.label(message).classes("pf-muted max-w-md")
        if action_label and on_action:
            ui.button(action_label, on_click=on_action).props("unelevated no-caps").classes("mt-2")
    return box
