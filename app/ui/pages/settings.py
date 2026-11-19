"""Configurações: nichos, templates de mensagem e metas."""

from __future__ import annotations

from typing import Any

from nicegui import ui
from sqlalchemy import func, select

from app.db import session_scope
from app.models import TEMPLATE_VARIABLES, WEEKDAY_LABELS, InteractionType, Lead, MessageTemplate, Niche
from app.repositories import SettingRepository
from app.services.catalog import CatalogError, CatalogService, NicheForm, TemplateForm, parse_keywords
from app.services.leads import LeadService
from app.services.templates import render, unknown_variables
from app.ui.components import empty_state
from app.ui.components.badges import badge_html, safe_color
from app.ui.components.confirm import confirm
from app.ui.layout import page_frame

WEEKDAY_OPTIONS: dict[int | None, str] = {None: "Nenhum dia"} | dict(enumerate(WEEKDAY_LABELS))
STAGE_OPTIONS = {t.value: t.label for t in InteractionType if t.is_outbound}
SAMPLE = {"nome": "Carlos", "empresa": "Barbearia do Zé", "servico": "criação de site", "cidade": "Osasco"}


def _show_errors(fields: dict[str, ui.element], exc: CatalogError) -> None:
    for key, element in fields.items():
        element.props.pop("error", None)
        element.props.pop("error-message", None)
        if key in exc.errors:
            element.props["error"] = True
            element.props["error-message"] = exc.errors[key]
        element.update()
    ui.notify("Corrija os campos destacados.", type="warning")


def _dialog_card(title: str) -> tuple[ui.dialog, ui.card]:
    dialog = ui.dialog().props(':maximized="$q.screen.lt.sm"')
    with dialog:
        card = ui.card().classes("w-full max-w-xl p-5 gap-3").style("background: var(--pf-surface)")
        with card:
            ui.label(title).classes("text-lg font-semibold")
    return dialog, card


# --------------------------------------------------------------------------- nichos


class NichesTab:
    @ui.refreshable_method
    def render(self) -> None:
        with session_scope() as session:
            counts = dict(session.execute(
                select(Lead.niche_id, func.count(Lead.id)).group_by(Lead.niche_id)).all())
            rows = [
                {"id": n.id, "name": n.name, "weekday": n.weekday, "color": safe_color(n.color),
                 "keywords": list(n.keywords or []), "active": n.active, "leads": counts.get(n.id, 0)}
                for n in session.scalars(select(Niche).order_by(Niche.weekday.is_(None), Niche.weekday, Niche.name))
            ]
        with ui.row().classes("w-full items-center"):
            ui.label("O nicho de cada dia define a fila da tela Hoje.").classes("text-sm pf-muted")
            ui.space()
            ui.button("Novo nicho", icon="add", on_click=lambda: self.edit(None)).props("unelevated no-caps")
        if not rows:
            empty_state("category", "Nenhum nicho", "Crie nichos para classificar e priorizar leads.")
            return
        with ui.element("div").classes("pf-card w-full divide-y"):
            for row in rows:
                with ui.row().classes("items-center gap-3 p-4 no-wrap"):
                    with ui.column().classes("gap-1 grow min-w-0"):
                        with ui.row().classes("items-center gap-2"):
                            ui.html(badge_html(row["name"], row["color"]), tag="span", sanitize=False)
                            if not row["active"]:
                                ui.html(badge_html("inativo", "#71717A", dot=False), tag="span", sanitize=False)
                        ui.label(
                            f"{WEEKDAY_OPTIONS[row['weekday']]} · {row['leads']} lead(s) · "
                            f"{len(row['keywords'])} palavra(s)-chave"
                        ).classes("text-sm pf-muted")
                    ui.button(icon="edit", on_click=lambda _, r=row: self.edit(r)).props("flat round dense")
                    ui.button(icon="delete", on_click=lambda _, r=row: self.delete(r)).props(
                        "flat round dense color=negative"
                    )

    async def edit(self, row: dict[str, Any] | None) -> None:
        dialog, card = _dialog_card("Editar nicho" if row else "Novo nicho")
        row = row or {"id": None, "name": "", "weekday": None, "color": "#6366F1", "keywords": [], "active": True}
        with card:
            fields: dict[str, ui.element] = {
                "name": ui.input("Nome *", value=row["name"]).props("outlined dense stack-label").classes("w-full"),
                "weekday": ui.select(WEEKDAY_OPTIONS, label="Dia da semana", value=row["weekday"]).props(
                    "outlined dense stack-label").classes("w-full"),
                "color": ui.color_input("Cor", value=row["color"]).props("outlined dense stack-label").classes("w-full"),
                "keywords": ui.textarea("Palavras-chave (separe por vírgula)", value=", ".join(row["keywords"])).props(
                    "outlined dense stack-label autogrow").classes("w-full"),
            }
            ui.label("Usadas na importação para classificar o lead pela categoria/nome.").classes("text-xs pf-muted")
            active = ui.switch("Ativo", value=row["active"])

            def save() -> None:
                form = NicheForm(
                    name=fields["name"].value, weekday=fields["weekday"].value,
                    color=fields["color"].value or "", keywords=parse_keywords(fields["keywords"].value),
                    active=active.value,
                )
                try:
                    with session_scope() as session:
                        _, warnings = CatalogService(session).save_niche(form, row["id"])
                except CatalogError as exc:
                    _show_errors(fields, exc)
                    return
                ui.notify(f"Nicho “{form.name.strip()}” salvo.", type="positive")
                for warning in warnings:
                    ui.notify(warning, type="warning")
                dialog.submit(True)

            with ui.row().classes("w-full justify-end gap-2 pt-2"):
                ui.button("Cancelar", on_click=lambda: dialog.submit(False)).props("flat no-caps")
                ui.button("Salvar", icon="check", on_click=save).props("unelevated no-caps").mark("niche-save")
        dialog.open()
        if await dialog:
            self.render.refresh()
        dialog.delete()

    async def delete(self, row: dict[str, Any]) -> None:
        if not await confirm("Excluir nicho?",
                             f"“{row['name']}” será removido. {row['leads']} lead(s) ficarão sem nicho.",
                             "Excluir", danger=True):
            return
        with session_scope() as session:
            CatalogService(session).delete_niche(row["id"])
        ui.notify(f"Nicho “{row['name']}” excluído.", type="positive")
        self.render.refresh()


# --------------------------------------------------------------------------- templates


class TemplatesTab:
    @ui.refreshable_method
    def render(self) -> None:
        with session_scope() as session:
            rows = [
                {"id": t.id, "name": t.name, "stage": t.stage, "body": t.body,
                 "active": t.active, "is_default": t.is_default}
                for t in session.scalars(select(MessageTemplate).order_by(MessageTemplate.stage, MessageTemplate.name))
            ]
        with ui.row().classes("w-full items-center"):
            ui.label("Variáveis: " + "  ".join("{" + v + "}" for v in TEMPLATE_VARIABLES)).classes(
                "text-sm pf-muted font-mono")
            ui.space()
            ui.button("Novo template", icon="add", on_click=lambda: self.edit(None)).props("unelevated no-caps")
        if not rows:
            empty_state("chat", "Nenhum template", "Crie mensagens prontas para cada etapa.")
            return
        with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 gap-4 w-full"):
            for row in rows:
                with ui.element("div").classes("pf-card p-4 flex flex-col gap-2"):
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        ui.label(row["name"]).classes("font-semibold grow truncate")
                        ui.button(icon="edit", on_click=lambda _, r=row: self.edit(r)).props("flat round dense")
                        ui.button(icon="delete", on_click=lambda _, r=row: self.delete(r)).props(
                            "flat round dense color=negative")
                    with ui.row().classes("gap-1"):
                        ui.html(badge_html(row["stage"].label, "#4F46E5", dot=False), tag="span", sanitize=False)
                        if row["is_default"]:
                            ui.html(badge_html("padrão", "#16A34A", dot=False), tag="span", sanitize=False)
                        if not row["active"]:
                            ui.html(badge_html("inativo", "#71717A", dot=False), tag="span", sanitize=False)
                    ui.label(row["body"]).classes("text-sm pf-muted whitespace-pre-line line-clamp-4")

    async def edit(self, row: dict[str, Any] | None) -> None:
        dialog, card = _dialog_card("Editar template" if row else "Novo template")
        row = row or {"id": None, "name": "", "stage": InteractionType.FIRST_CONTACT, "body": "",
                      "active": True, "is_default": False}
        with card:
            fields: dict[str, ui.element] = {
                "name": ui.input("Nome *", value=row["name"]).props("outlined dense stack-label").classes("w-full"),
                "stage": ui.select(STAGE_OPTIONS, label="Etapa", value=row["stage"].value).props(
                    "outlined dense stack-label").classes("w-full"),
            }
            with ui.row().classes("gap-1"):
                for var in TEMPLATE_VARIABLES:
                    ui.button("{" + var + "}", on_click=lambda _, v=var: insert(v)).props(
                        "outline dense no-caps size=sm")
            body = ui.textarea("Mensagem *", value=row["body"]).props(
                "outlined dense stack-label autogrow").classes("w-full")
            fields["body"] = body
            ui.label("Prévia").classes("text-xs pf-muted pt-1")
            preview = ui.label().classes("text-sm whitespace-pre-line p-3 rounded-lg w-full").style(
                "background: var(--pf-bg); border: 1px solid var(--pf-border)")
            warning = ui.label().classes("text-xs text-negative")

            def update_preview() -> None:
                text = body.value or ""
                preview.text = render(text, SAMPLE) or "—"
                unknown = unknown_variables(text)
                warning.text = ("Variáveis desconhecidas: " + ", ".join("{" + u + "}" for u in unknown)) if unknown else ""

            def insert(var: str) -> None:
                body.value = (body.value or "") + "{" + var + "}"

            body.on_value_change(update_preview)
            update_preview()
            with ui.row().classes("gap-4"):
                active = ui.switch("Ativo", value=row["active"])
                default = ui.switch("Padrão da etapa", value=row["is_default"])

            def save() -> None:
                form = TemplateForm(name=fields["name"].value, stage=InteractionType(fields["stage"].value),
                                    body=body.value, active=active.value, is_default=default.value)
                try:
                    with session_scope() as session:
                        CatalogService(session).save_template(form, row["id"])
                except CatalogError as exc:
                    _show_errors(fields, exc)
                    return
                ui.notify(f"Template “{form.name.strip()}” salvo.", type="positive")
                dialog.submit(True)

            with ui.row().classes("w-full justify-end gap-2 pt-2"):
                ui.button("Cancelar", on_click=lambda: dialog.submit(False)).props("flat no-caps")
                ui.button("Salvar", icon="check", on_click=save).props("unelevated no-caps")
        dialog.open()
        if await dialog:
            self.render.refresh()
        dialog.delete()

    async def delete(self, row: dict[str, Any]) -> None:
        if not await confirm("Excluir template?", f"“{row['name']}” será removido.", "Excluir", danger=True):
            return
        with session_scope() as session:
            CatalogService(session).delete_template(row["id"])
        ui.notify("Template excluído.", type="positive")
        self.render.refresh()


# --------------------------------------------------------------------------- metas


GOAL_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("daily_goal", "Meta de abordagens por dia", "Quantos leads novos entram na fila de Hoje."),
    ("followup_days", "Dias sem resposta até o follow-up", ""),
    ("max_followups", "Máximo de follow-ups", "Depois disso o lead é sugerido como perdido."),
)
SCORE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("score_weight_rating", "Peso da nota no Google", "Nota 5,0 = peso cheio."),
    ("score_weight_reviews", "Peso do nº de avaliações", "Escala logarítmica até o teto."),
    ("score_weight_website", "Peso de não ter site", "Sem site = cheio · site ruim = 2/3."),
    ("score_reviews_cap", "Teto de avaliações", "A partir daqui conta como peso cheio."),
)


def goals_tab() -> None:
    with session_scope() as session:
        values = SettingRepository(session).all()
    fields: dict[str, ui.element] = {}

    def number(key: str, label: str, hint: str) -> None:
        element = ui.number(label, value=values[key], precision=0, format="%d").props(
            "outlined dense stack-label").classes("w-full")
        if hint:
            element.props["hint"] = hint
        fields[key] = element

    with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-2 gap-4 w-full"):
        with ui.element("div").classes("pf-card p-5 flex flex-col gap-4"):
            ui.label("Rotina").classes("font-semibold")
            fields["service_name"] = ui.input("Serviço oferecido ({servico})", value=values["service_name"]).props(
                "outlined dense stack-label").classes("w-full")
            for key, label, hint in GOAL_FIELDS:
                number(key, label, hint)
        with ui.element("div").classes("pf-card p-5 flex flex-col gap-4"):
            ui.label("Score de prioridade").classes("font-semibold")
            for key, label, hint in SCORE_FIELDS:
                number(key, label, hint)

    def save() -> None:
        try:
            with session_scope() as session:
                weights_changed = CatalogService(session).save_settings(
                    {key: element.value for key, element in fields.items()})
                updated = LeadService(session).recalculate_scores() if weights_changed else 0
        except CatalogError as exc:
            _show_errors(fields, exc)
            return
        ui.notify("Configurações salvas.", type="positive")
        if weights_changed:
            ui.notify(f"Score recalculado para {updated} lead(s).", type="info")

    def recalc() -> None:
        with session_scope() as session:
            updated = LeadService(session).recalculate_scores()
        ui.notify(f"Score recalculado para {updated} lead(s).", type="positive")

    with ui.row().classes("w-full justify-end gap-2"):
        ui.button("Recalcular scores", icon="calculate", on_click=recalc).props("flat no-caps")
        ui.button("Salvar", icon="check", on_click=save).props("unelevated no-caps")


def settings_page() -> None:
    with page_frame("settings", "Configurações", "Nichos, templates de mensagem e metas."):
        with ui.tabs().props("no-caps align=left dense").classes("w-full") as tabs:
            niches = ui.tab("Nichos", icon="category")
            templates = ui.tab("Templates", icon="chat")
            goals = ui.tab("Metas", icon="flag")
        with ui.tab_panels(tabs, value=niches).classes("w-full bg-transparent"):
            with ui.tab_panel(niches).classes("px-0 flex flex-col gap-4"):
                NichesTab().render()
            with ui.tab_panel(templates).classes("px-0 flex flex-col gap-4"):
                TemplatesTab().render()
            with ui.tab_panel(goals).classes("px-0 flex flex-col gap-4"):
                goals_tab()
