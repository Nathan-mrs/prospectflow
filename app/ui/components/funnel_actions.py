"""Ações de funil reutilizadas pelas telas (Kanban, Hoje e diálogo do lead).

Cada ação abre sua própria sessão, mostra um toast e retorna se algo mudou.
"""

from __future__ import annotations

import json

from nicegui import ui

from app.db import session_scope
from app.models import InteractionType, Lead, LeadStatus, SalePlan
from app.services.funnel import FunnelError, FunnelService

LOST_REASONS = (
    "Sem resposta",
    "Achou caro",
    "Já tem site",
    "Sem interesse no momento",
    "Fechou com outro",
)

PLAN_OPTIONS: dict[SalePlan, tuple[str, str]] = {
    SalePlan.ONE_TIME: ("R$ 497 à vista", "Pagamento único"),
    SalePlan.RECURRING: ("R$ 297 + R$ 49/mês", "Entrada + mensalidade (entra no MRR)"),
}


async def ask_plan() -> SalePlan | None:
    """Pergunta o plano da venda. ``None`` = cancelado."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-5 gap-3").style(
        "background: var(--pf-surface)"
    ):
        ui.label("🎉 Venda fechada!").classes("text-lg font-semibold")
        ui.label("Qual plano o cliente escolheu?").classes("pf-muted")
        for plan, (title, hint) in PLAN_OPTIONS.items():
            with ui.button(on_click=lambda p=plan: dialog.submit(p)).props(
                "outline no-caps align=left"
            ).classes("w-full"):
                with ui.column().classes("gap-0 items-start py-1"):
                    ui.label(title).classes("font-semibold")
                    ui.label(hint).classes("text-xs pf-muted")
        ui.button("Cancelar", on_click=lambda: dialog.submit(None)).props("flat no-caps").classes(
            "self-end"
        )
    dialog.open()
    result = await dialog
    dialog.delete()
    return result


async def ask_lost_reason(default: str | None = None) -> str | None:
    """Pergunta o motivo da perda. ``None`` = cancelado; ``""`` = sem motivo."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-5 gap-3").style(
        "background: var(--pf-surface)"
    ):
        ui.label("Marcar como perdido").classes("text-lg font-semibold")
        reason = ui.select(
            list(LOST_REASONS), label="Motivo", value=default, new_value_mode="add-unique",
            with_input=True,
        ).props("outlined dense stack-label").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 pt-2"):
            ui.button("Cancelar", on_click=lambda: dialog.submit(None)).props("flat no-caps")
            ui.button(
                "Marcar perdido", on_click=lambda: dialog.submit(reason.value or "")
            ).props("unelevated no-caps color=negative")
    dialog.open()
    result = await dialog
    dialog.delete()
    return result


async def move_lead(lead_id: int, to_status: LeadStatus, lost_reason: str | None = None) -> bool:
    """Move o lead perguntando o plano (Fechado) ou o motivo (Perdido) quando preciso."""
    plan: SalePlan | None = None
    if to_status is LeadStatus.WON:
        plan = await ask_plan()
        if plan is None:
            return False
    elif to_status is LeadStatus.LOST and lost_reason is None:
        lost_reason = await ask_lost_reason()
        if lost_reason is None:
            return False
    try:
        with session_scope() as session:
            lead = session.get(Lead, lead_id)
            if lead is None:
                ui.notify("Lead não encontrado.", type="negative")
                return False
            changed = FunnelService(session).move(
                lead, to_status, plan=plan, lost_reason=lost_reason or None
            )
            name = lead.company_name
    except FunnelError as exc:
        ui.notify(str(exc), type="warning")
        return False
    if changed:
        ui.notify(f"“{name}” → {to_status.label}", type="positive")
    return changed


def register_interaction(
    lead_id: int, kind: InteractionType, message: str | None = None, note: str | None = None
) -> bool:
    """Registra uma interação (mensagem enviada, resposta ou anotação)."""
    try:
        with session_scope() as session:
            lead = session.get(Lead, lead_id)
            if lead is None:
                ui.notify("Lead não encontrado.", type="negative")
                return False
            before = lead.status
            FunnelService(session).register(lead, kind, message=message, note=note)
            name, after = lead.company_name, lead.status
    except FunnelError as exc:
        ui.notify(str(exc), type="warning")
        return False
    suffix = f" · agora em {after.label}" if after is not before else ""
    ui.notify(f"{kind.label} registrado para “{name}”{suffix}", type="positive")
    return True


def whatsapp_button(url: str | None, text: str, label: str = "Copiar + WhatsApp") -> ui.button:
    """Botão que copia a mensagem (no navegador, dentro do clique) e abre o ``wa.me``."""
    button = ui.button(label, icon="content_copy").props("unelevated no-caps color=positive")
    if not url:
        button.props("disable").tooltip("Lead sem WhatsApp válido")
        return button
    button.props["href"] = url
    button.props["target"] = "_blank"
    if text:
        button.on("click", js_handler=f"() => navigator.clipboard?.writeText({json.dumps(text)})")
        button.on("click", lambda: ui.notify("Mensagem copiada — cole no WhatsApp 📋", type="info"))
    return button
