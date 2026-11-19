"""Diálogo de confirmação reutilizável."""

from __future__ import annotations

from nicegui import ui


async def confirm(
    title: str, message: str, confirm_label: str = "Confirmar", danger: bool = False
) -> bool:
    """Pergunta ao usuário e retorna ``True`` se ele confirmar."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-sm p-5 gap-3").style(
        "background: var(--pf-surface)"
    ):
        ui.label(title).classes("text-lg font-semibold")
        ui.label(message).classes("pf-muted")
        with ui.row().classes("w-full justify-end gap-2 pt-2"):
            ui.button("Cancelar", on_click=lambda: dialog.submit(False)).props("flat no-caps")
            ui.button(confirm_label, on_click=lambda: dialog.submit(True)).props(
                f"unelevated no-caps {'color=negative' if danger else ''}"
            )
    dialog.open()
    result = await dialog
    dialog.delete()
    return bool(result)
