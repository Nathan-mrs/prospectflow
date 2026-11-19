"""Tela "Hoje": fila de abordagem do nicho do dia, follow-ups e cobranças."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nicegui import ui

from app.clock import now
from app.db import session_scope
from app.models import WEEKDAY_LABELS, InteractionType, Lead, LeadStatus
from app.repositories import SettingRepository
from app.services.billing import mark_paid
from app.services.daily_queue import build_daily_queue
from app.services.templates import render, suggested_stage, template_variables, templates_by_stage, whatsapp_link
from app.ui.components import empty_state, stat_card
from app.ui.components.badges import badge_html, safe_color, score_color
from app.ui.components.funnel_actions import move_lead, register_interaction, whatsapp_button
from app.ui.components.lead_dialog import LeadDialog
from app.ui.formatting import format_money, format_phone, format_rating, relative_time
from app.ui.layout import page_frame


@dataclass(frozen=True, slots=True)
class QueueCard:
    """Dados de um lead já prontos para a tela (sem objetos ORM)."""

    id: int
    company: str
    subtitle: str
    score: int
    niche: str | None
    niche_color: str
    stage: InteractionType | None
    message: str
    wa_url: str | None
    followups: int
    last_contact: str


def _card(lead: Lead, templates: dict, service: str, at: datetime) -> QueueCard:
    stage = suggested_stage(lead)
    options = templates.get(stage, []) if stage else []
    message = render(options[0].body, template_variables(lead, service)) if options else ""
    parts = [format_phone(lead.phone) if lead.phone else "sem WhatsApp", lead.city or ""]
    if lead.google_rating is not None:
        parts.append(f"★ {format_rating(lead.google_rating)} ({lead.review_count or 0})")
    return QueueCard(
        id=lead.id,
        company=lead.company_name,
        subtitle=" · ".join(p for p in parts if p),
        score=lead.priority_score,
        niche=lead.niche.name if lead.niche else None,
        niche_color=safe_color(lead.niche.color if lead.niche else None),
        stage=stage,
        message=message,
        wa_url=whatsapp_link(lead.phone, message),
        followups=lead.followup_count,
        last_contact=relative_time(lead.last_contact_at, at) if lead.last_contact_at else "",
    )


class TodayView:
    def __init__(self) -> None:
        self.extra = 0

    @ui.refreshable_method
    def render(self) -> None:
        at = now()
        with session_scope() as session:
            queue = build_daily_queue(session, at, extra=self.extra)
            settings = SettingRepository(session).all()
            templates = templates_by_stage(session)
            service = str(settings["service_name"])
            max_followups = int(settings["max_followups"])
            new_cards = [_card(lead, templates, service, at) for lead in queue.new_leads]
            follow_cards = [_card(lead, templates, service, at) for lead in queue.followups]
            lost_cards = [_card(lead, templates, service, at) for lead in queue.suggest_lost]
            niche = (queue.niche.name, safe_color(queue.niche.color)) if queue.niche else None
            charges, goal, done, remaining = queue.charges, queue.goal, queue.done_today, queue.remaining_new
            progress = queue.progress

        # -- cabeçalho do dia -------------------------------------------------------
        with ui.element("div").classes("pf-card p-5 w-full flex flex-col gap-3"):
            with ui.row().classes("items-center gap-3 flex-wrap"):
                ui.label(f"{WEEKDAY_LABELS[at.weekday()]}, {at.strftime('%d/%m')}").classes(
                    "text-lg font-semibold"
                )
                if niche:
                    ui.html(badge_html(f"Nicho do dia: {niche[0]}", niche[1]), tag="span", sanitize=False)
                ui.space()
                ui.label(f"{done}/{goal} abordagens").classes("font-semibold")
            ui.linear_progress(value=progress, show_value=False, size="10px").props(
                f"rounded color={'positive' if done >= goal else 'primary'}"
            )
            if done >= goal:
                ui.label("Meta do dia batida! 🎯 Use “carregar mais” se quiser continuar.").classes(
                    "text-sm pf-muted"
                )

        with ui.element("div").classes("grid grid-cols-2 lg:grid-cols-4 gap-4 w-full"):
            stat_card("Na fila hoje", len(new_cards), "format_list_numbered")
            stat_card("Follow-ups pendentes", len(follow_cards), "replay", "#D97706")
            stat_card("Sugestão de perda", len(lost_cards), "heart_broken", "#DC2626")
            stat_card("Cobranças em aberto", len(charges), "payments", "#16A34A")

        # -- fila de abordagem ------------------------------------------------------
        ui.label("Fila de abordagem").classes("pf-section")
        if niche is None:
            empty_state("event_busy", "Nenhum nicho para hoje",
                        "Defina um dia da semana para seus nichos em Configurações.",
                        "Abrir configurações", lambda: ui.navigate.to("/configuracoes"))
        elif not new_cards:
            empty_state("task_alt", "Fila zerada",
                        f"Não há mais leads novos de {niche[0]} para hoje." if not remaining
                        else "Você já bateu a meta de hoje.",
                        "Carregar mais 5" if remaining else "Importar leads",
                        self._load_more if remaining else lambda: ui.navigate.to("/importar"))
        else:
            with ui.column().classes("w-full gap-3"):
                for card in new_cards:
                    self._lead_card(card)
            if remaining:
                ui.button(f"Carregar mais 5 ({remaining} restantes)", icon="expand_more",
                          on_click=self._load_more).props("flat no-caps").classes("self-center")

        # -- follow-ups ------------------------------------------------------------
        if follow_cards:
            ui.label("Follow-ups de hoje").classes("pf-section")
            with ui.column().classes("w-full gap-3"):
                for card in follow_cards:
                    self._lead_card(card, followup_of=max_followups)

        if lost_cards:
            ui.label("Sem resposta após todos os follow-ups").classes("pf-section")
            with ui.column().classes("w-full gap-3"):
                for card in lost_cards:
                    self._lost_card(card)

        # -- cobranças -------------------------------------------------------------
        if charges:
            ui.label("Cobranças do mês").classes("pf-section")
            with ui.element("div").classes("pf-card w-full divide-y"):
                for charge in charges:
                    late = (f"{charge.days_late} dia(s) em atraso" if charge.days_late > 0
                            else "vence hoje" if charge.days_late == 0 else "a vencer")
                    text = (f"Oi! Tudo bem? Passando para lembrar da mensalidade do site "
                            f"({charge.reference_month[5:]}/{charge.reference_month[:4]}) "
                            f"no valor de {format_money(charge.amount)}. Obrigado!")
                    with ui.row().classes("items-center gap-3 p-4 flex-wrap"):
                        with ui.column().classes("gap-0 grow"):
                            ui.label(charge.company).classes("font-semibold")
                            ui.label(
                                f"{format_money(charge.amount)} · ref. {charge.reference_month} · {late}"
                            ).classes("text-sm " + ("text-negative" if charge.days_late > 0 else "pf-muted"))
                        whatsapp_button(whatsapp_link(charge.phone, text), text, "Cobrar")
                        ui.button("Marcar pago", icon="check",
                                  on_click=lambda _, p=charge.payment_id: self._paid(p)).props(
                            "outline no-caps"
                        )

    # -- cards -----------------------------------------------------------------------

    def _header(self, card: QueueCard) -> None:
        with ui.row().classes("items-start gap-3 w-full no-wrap"):
            ui.label(str(card.score)).classes(
                "w-10 h-10 rounded-xl flex items-center justify-center font-bold shrink-0"
            ).style(f"color: {score_color(card.score)}; "
                    f"background: color-mix(in srgb, {score_color(card.score)} 14%, transparent)")
            with ui.column().classes("gap-0 grow min-w-0"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(card.company).classes("font-semibold cursor-pointer hover:underline").on(
                        "click", lambda _, i=card.id: self._open(i)
                    )
                    if card.niche:
                        ui.html(badge_html(card.niche, card.niche_color), tag="span", sanitize=False)
                ui.label(card.subtitle).classes("text-sm pf-muted")

    def _lead_card(self, card: QueueCard, followup_of: int | None = None) -> None:
        with ui.element("div").classes("pf-card p-4 w-full flex flex-col gap-3"):
            self._header(card)
            if followup_of is not None:
                ui.label(
                    f"Follow-up {card.followups + 1}/{followup_of} · último contato {card.last_contact}"
                ).classes("text-xs font-medium").style("color: var(--pf-warning)")
            if card.message:
                ui.label(card.message).classes("text-sm whitespace-pre-line p-3 rounded-lg").style(
                    "background: var(--pf-bg); border: 1px solid var(--pf-border)"
                )
            with ui.row().classes("gap-2 flex-wrap"):
                whatsapp_button(card.wa_url, card.message)
                if card.stage:
                    ui.button("Enviei", icon="done",
                              on_click=lambda _, c=card: self._sent(c)).props("outline no-caps")
                if followup_of is not None:
                    ui.button("Respondeu", icon="chat",
                              on_click=lambda _, c=card: self._replied(c)).props("flat no-caps")

    def _lost_card(self, card: QueueCard) -> None:
        with ui.element("div").classes("pf-card p-4 w-full flex flex-col gap-3"):
            self._header(card)
            ui.label(f"{card.followups} follow-ups sem resposta · último contato {card.last_contact}"
                     ).classes("text-xs pf-muted")
            with ui.row().classes("gap-2"):
                ui.button("Marcar perdido", icon="close",
                          on_click=lambda _, c=card: self._lost(c)).props(
                    "unelevated no-caps color=negative"
                )
                ui.button("Respondeu", icon="chat",
                          on_click=lambda _, c=card: self._replied(c)).props("flat no-caps")

    # -- ações -----------------------------------------------------------------------

    def _sent(self, card: QueueCard) -> None:
        if card.stage and register_interaction(card.id, card.stage, message=card.message):
            self.render.refresh()

    def _replied(self, card: QueueCard) -> None:
        if register_interaction(card.id, InteractionType.REPLY):
            self.render.refresh()

    async def _lost(self, card: QueueCard) -> None:
        if await move_lead(card.id, LeadStatus.LOST, lost_reason="Sem resposta"):
            self.render.refresh()

    def _paid(self, payment_id: int) -> None:
        with session_scope() as session:
            mark_paid(session, payment_id, now())
        ui.notify("Mensalidade marcada como paga 💰", type="positive")
        self.render.refresh()

    def _load_more(self) -> None:
        self.extra += 5
        self.render.refresh()

    async def _open(self, lead_id: int) -> None:
        if await LeadDialog(lead_id).open():
            self.render.refresh()


def today_page() -> None:
    with page_frame("today", "Hoje", "Sua fila do dia, follow-ups e cobranças."):
        TodayView().render()
