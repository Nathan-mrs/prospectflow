"""Diálogo de criação/edição de lead, com aba de histórico."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from app.clock import now
from app.db import session_scope
from app.models import BOARD_ORDER, InteractionType, Lead, LeadStatus, WebsiteStatus
from app.repositories import LeadRepository, NicheRepository
from app.services.leads import LeadForm, LeadService, LeadValidationError
from app.ui.components.badges import STATUS_COLORS, badge_html, safe_color
from app.ui.components.funnel_actions import move_lead, register_interaction, whatsapp_button
from app.ui.formatting import format_datetime, format_phone, relative_time

INTERACTION_ICONS: dict[InteractionType, str] = {
    InteractionType.FIRST_CONTACT: "send",
    InteractionType.FOLLOW_UP: "replay",
    InteractionType.PREVIEW_SENT: "web",
    InteractionType.PROPOSAL: "request_quote",
    InteractionType.REPLY: "chat",
    InteractionType.NOTE: "sticky_note_2",
}


def _set_error(element: ui.element, message: str | None) -> None:
    """Mostra/limpa a mensagem de erro de um campo Quasar (atribuição direta: sem parse de aspas)."""
    if message:
        element.props["error"] = True
        element.props["error-message"] = message
    else:
        element.props.pop("error", None)
        element.props.pop("error-message", None)


class LeadDialog:
    """Abre um diálogo modal; ``await LeadDialog(lead_id).open()`` retorna ``True`` se salvou."""

    def __init__(self, lead_id: int | None = None) -> None:
        self.lead_id = lead_id
        self.fields: dict[str, ui.element] = {}
        with session_scope() as session:
            self.niche_options: dict[int | None, str] = {None: "Sem nicho"} | {
                n.id: n.name for n in NicheRepository(session).list()
            }
            lead = LeadRepository(session).get_with_timeline(lead_id) if lead_id else None
            self.form = LeadForm.from_lead(lead) if lead else LeadForm()
            self.timeline = self._timeline_items(lead) if lead else []
            self.header = self._header(lead) if lead else None
        self._build()

    # -- dados para a aba de histórico -----------------------------------------------

    @staticmethod
    def _header(lead: Lead) -> dict[str, Any]:
        return {
            "status": lead.status,
            "score": lead.priority_score,
            "created": format_datetime(lead.created_at),
            "phone": format_phone(lead.phone),
            "wa_url": lead.whatsapp_url,
            "niche": lead.niche.name if lead.niche else None,
            "niche_color": safe_color(lead.niche.color if lead.niche else None),
        }

    @staticmethod
    def _timeline_items(lead: Lead) -> list[dict[str, Any]]:
        reference = now()
        items: list[dict[str, Any]] = [
            {
                "at": i.occurred_at,
                "icon": INTERACTION_ICONS[i.type],
                "title": i.type.label,
                "text": i.note or i.message or "",
                "when": relative_time(i.occurred_at, reference),
            }
            for i in lead.interactions
        ]
        items += [
            {
                "at": h.changed_at,
                "icon": "swap_horiz" if h.from_status else "flag",
                "title": f"Status: {h.to_status.label}" if h.from_status else "Lead criado",
                "text": f"{h.from_status.label} → {h.to_status.label}" if h.from_status else "",
                "when": relative_time(h.changed_at, reference),
                "color": "grey-6",
            }
            for h in lead.status_history
        ]
        return sorted(items, key=lambda item: item["at"], reverse=True)

    # -- interface -------------------------------------------------------------------

    def _input(self, key: str, label: str, **kwargs: Any) -> ui.input:
        element = ui.input(label, value=str(getattr(self.form, key) or ""), **kwargs).props(
            "outlined dense stack-label"
        )
        self.fields[key] = element
        return element

    def _build(self) -> None:
        with ui.dialog().props(':maximized="$q.screen.lt.sm"') as self.dialog, ui.card().classes(
            "w-full max-w-2xl p-0 gap-0"
        ).style("background: var(--pf-surface)"):
            with ui.row().classes("w-full items-center px-5 pt-4 pb-2"):
                ui.label("Editar lead" if self.lead_id else "Novo lead").classes("text-lg font-semibold")
                ui.space()
                ui.button(icon="close", on_click=lambda: self.dialog.submit(False)).props(
                    "flat round dense"
                )

            if self.lead_id:
                with ui.tabs().props("no-caps align=left dense").classes("px-3") as tabs:
                    data_tab = ui.tab("Dados", icon="edit")
                    actions_tab = ui.tab("Ações", icon="bolt")
                    history_tab = ui.tab(f"Histórico ({len(self.timeline)})", icon="history")
                with ui.tab_panels(tabs, value=data_tab).classes("w-full bg-transparent"):
                    with ui.tab_panel(data_tab).classes("p-0"):
                        self._form_body()
                    with ui.tab_panel(actions_tab):
                        self._actions_body()
                    with ui.tab_panel(history_tab):
                        self._history_body()
            else:
                self._form_body()

            with ui.row().classes("w-full justify-end gap-2 px-5 py-3").style(
                "border-top: 1px solid var(--pf-border)"
            ):
                ui.button("Cancelar", on_click=lambda: self.dialog.submit(False)).props("flat no-caps")
                ui.button("Salvar", icon="check", on_click=self._save).props("unelevated no-caps")

    def _form_body(self) -> None:
        with ui.element("div").classes("grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3 w-full px-5 py-3"):
            self._input("company_name", "Empresa *").classes("sm:col-span-2")
            self._input("contact_name", "Nome do contato", placeholder="usado em {nome}")
            self.fields["niche_id"] = ui.select(
                self.niche_options, label="Nicho", value=self.form.niche_id
            ).props("outlined dense stack-label")
            self._input("phone", "WhatsApp", placeholder="(11) 98765-4321")
            self._input("instagram", "Instagram", placeholder="@perfil")
            self._input("category", "Categoria (Google Maps)")
            self.fields["website_status"] = ui.select(
                {s.value: s.label for s in WebsiteStatus},
                label="Site",
                value=WebsiteStatus(self.form.website_status).value,
            ).props("outlined dense stack-label")
            self._input("google_rating", "Nota Google", placeholder="4,8")
            self._input("review_count", "Nº de avaliações", placeholder="312")
            self._input("neighborhood", "Bairro")
            self._input("city", "Cidade")
            self._input("maps_url", "Link do Google Maps").classes("sm:col-span-2")
            self.fields["notes"] = (
                ui.textarea("Observações", value=self.form.notes)
                .props("outlined dense stack-label autogrow")
                .classes("sm:col-span-2")
            )

    def _actions_body(self) -> None:
        header = self.header
        assert header is not None and self.lead_id is not None
        lead_id = self.lead_id
        with ui.column().classes("w-full gap-5"):
            with ui.column().classes("w-full gap-2"):
                ui.label("Etapa do funil").classes("text-sm font-semibold")
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    status = ui.select({s.value: s.label for s in BOARD_ORDER}, value=header["status"].value
                                       ).props("outlined dense").classes("grow")

                    async def move() -> None:
                        if await move_lead(lead_id, LeadStatus(status.value)):
                            self.dialog.submit(True)

                    ui.button("Mover", icon="swap_horiz", on_click=move).props("unelevated no-caps")
            with ui.column().classes("w-full gap-2"):
                ui.label("Registrar interação").classes("text-sm font-semibold")
                kind = ui.select({t.value: t.label for t in InteractionType}, value=InteractionType.NOTE.value
                                 ).props("outlined dense").classes("w-full")
                note = ui.textarea(placeholder="Anotação ou resumo da conversa (opcional)").props(
                    "outlined dense autogrow").classes("w-full")

                def register() -> None:
                    chosen = InteractionType(kind.value)
                    text = (note.value or "").strip() or None
                    if chosen is InteractionType.NOTE and not text:
                        ui.notify("Escreva a anotação.", type="warning")
                        return
                    if register_interaction(lead_id, chosen, note=text):
                        self.dialog.submit(True)

                ui.button("Registrar", icon="add_comment", on_click=register).props(
                    "outline no-caps").classes("self-end")
            if header["wa_url"]:
                whatsapp_button(header["wa_url"], "", "Abrir conversa no WhatsApp").props("outline")

    def _history_body(self) -> None:
        header = self.header
        if header:
            with ui.row().classes("items-center gap-2 pb-3"):
                ui.html(badge_html(header["status"].label, STATUS_COLORS[header["status"]]),
                        tag="span", sanitize=False)
                if header["niche"]:
                    ui.html(badge_html(header["niche"], header["niche_color"]), tag="span", sanitize=False)
                ui.label(f"Score {header['score']} · criado em {header['created']}").classes(
                    "text-sm pf-muted"
                )
        if not self.timeline:
            ui.label("Nenhuma interação registrada ainda.").classes("pf-muted")
            return
        with ui.timeline(side="right", layout="dense").classes("w-full"):
            for item in self.timeline:
                ui.timeline_entry(
                    item["text"],
                    title=item["title"],
                    subtitle=f"{item['when']} · {item['at'].strftime('%d/%m %H:%M')}",
                    icon=item["icon"],
                    color=item.get("color", "primary"),
                )

    # -- salvar ----------------------------------------------------------------------

    def _collect(self) -> LeadForm:
        values = {key: element.value for key, element in self.fields.items()}
        values["website_status"] = WebsiteStatus(values["website_status"])
        return LeadForm(**values)

    def _save(self) -> None:
        for element in self.fields.values():
            _set_error(element, None)
        form = self._collect()
        try:
            with session_scope() as session:
                service = LeadService(session)
                if self.lead_id:
                    lead, warnings = service.update(self.lead_id, form)
                else:
                    lead, warnings = service.create(form)
                name = lead.company_name
        except LeadValidationError as exc:
            for key, message in exc.errors.items():
                if key in self.fields:
                    _set_error(self.fields[key], message)
            ui.notify("Corrija os campos destacados.", type="warning")
            return
        ui.notify(f"“{name}” salvo.", type="positive")
        for warning in warnings:
            ui.notify(warning, type="info")
        self.dialog.submit(True)

    async def open(self) -> bool:
        """Abre o diálogo e espera o usuário fechar. ``True`` = salvou."""
        self.dialog.open()
        result = await self.dialog
        self.dialog.delete()
        return bool(result)
