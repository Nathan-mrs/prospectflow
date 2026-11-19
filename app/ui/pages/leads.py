"""Tela de Leads: tabela com busca, filtros, ações rápidas, ações em lote e exportação."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from nicegui import app, ui

from app.clock import now
from app.db import session_scope
from app.models import Lead, LeadStatus, WebsiteStatus
from app.repositories import NO_NICHE, LeadQuery, LeadRepository, NicheRepository
from app.services.export import leads_to_dataframe, to_csv_bytes, to_xlsx_bytes
from app.services.leads import LeadService
from app.services.score import score_label
from app.ui.components import empty_state
from app.ui.components.badges import STATUS_COLORS, safe_color, score_color
from app.ui.components.confirm import confirm
from app.ui.components.lead_dialog import LeadDialog
from app.ui.formatting import format_int, format_phone, format_rating, relative_time
from app.ui.layout import page_frame

MAX_ROWS = 5000
STORAGE_KEY = "leads_filters"

WEBSITE_COLORS = {WebsiteStatus.NONE: "#16A34A", WebsiteStatus.BAD: "#D97706", WebsiteStatus.YES: "#71717A"}

SCORE_OPTIONS = {0: "Qualquer score", 40: "Score ≥ 40", 60: "Score ≥ 60", 80: "Score ≥ 80"}

COLUMNS: list[dict[str, Any]] = [
    {"name": "company", "label": "Empresa", "field": "company", "align": "left", "sortable": True},
    {"name": "niche", "label": "Nicho", "field": "niche", "align": "left", "sortable": True},
    {"name": "status", "label": "Status", "field": "status_order", "align": "left", "sortable": True},
    {"name": "score", "label": "Score", "field": "score", "align": "left", "sortable": True},
    {"name": "phone", "label": "WhatsApp", "field": "phone", "align": "left"},
    {"name": "location", "label": "Local", "field": "location", "align": "left", "sortable": True},
    {"name": "rating", "label": "Google", "field": "rating_sort", "align": "left", "sortable": True},
    {"name": "website", "label": "Site", "field": "website", "align": "left", "sortable": True},
    {"name": "last_contact", "label": "Último contato", "field": "last_contact_iso",
     "align": "left", "sortable": True},
    {"name": "actions", "label": "", "field": "id", "align": "right"},
]

_BADGE = (
    '<span class="pf-badge" :style="{{background: props.row.{color} + \'1F\', color: props.row.{color}}}">'
    '<span class="pf-dot" :style="{{background: props.row.{color}}}"></span>{{{{ props.row.{text} }}}}</span>'
)


def _badge(text_key: str, color_key: str) -> str:
    return _BADGE.format(text=text_key, color=color_key)


ACTIONS = r"""
<q-btn v-if="props.row.wa_url" flat round dense icon="chat" color="positive" type="a"
       :href="props.row.wa_url" target="_blank" @click.stop><q-tooltip>Abrir WhatsApp</q-tooltip></q-btn>
<q-btn flat round dense icon="edit" @click.stop="$parent.$emit('edit', props.row.id)">
  <q-tooltip>Editar</q-tooltip></q-btn>
<q-btn flat round dense icon="delete_outline" color="negative"
       @click.stop="$parent.$emit('remove', props.row.id)"><q-tooltip>Excluir</q-tooltip></q-btn>
"""

SLOTS: dict[str, str] = {
    "body-cell-company": r"""
<q-td :props="props" class="cursor-pointer" @click="$parent.$emit('edit', props.row.id)">
  <div class="font-medium">{{ props.row.company }}</div>
  <div class="text-xs pf-muted">{{ props.row.subtitle }}</div>
</q-td>""",
    "body-cell-niche": f'<q-td :props="props">{_badge("niche", "niche_color")}</q-td>',
    "body-cell-status": f'<q-td :props="props">{_badge("status_label", "status_color")}</q-td>',
    "body-cell-score": f'<q-td :props="props">{_badge("score_label", "score_color")}</q-td>',
    "body-cell-rating": r"""
<q-td :props="props"><span v-if="props.row.rating">★ {{ props.row.rating }}</span>
  <span class="pf-muted text-xs"> {{ props.row.reviews }}</span></q-td>""",
    "body-cell-website": f'<q-td :props="props">{_badge("website", "website_color")}</q-td>',
    "body-cell-last_contact": r"""
<q-td :props="props"><span class="pf-muted">{{ props.row.last_contact }}</span></q-td>""",
    "body-cell-actions": f'<q-td :props="props" auto-width>{ACTIONS}</q-td>',
    # modo cartão (celular)
    "item": f"""
<div class="q-pa-xs col-12">
  <div class="pf-card p-3 flex flex-col gap-2">
    <div class="flex items-start justify-between gap-2 no-wrap">
      <div class="min-w-0 cursor-pointer" @click="$parent.$emit('edit', props.row.id)">
        <div class="font-medium">{{{{ props.row.company }}}}</div>
        <div class="text-xs pf-muted">{{{{ props.row.subtitle }}}}</div>
      </div>
      <q-checkbox dense v-model="props.selected" />
    </div>
    <div class="flex gap-1 flex-wrap">
      {_badge("status_label", "status_color")} {_badge("niche", "niche_color")}
      {_badge("score_label", "score_color")}
    </div>
    <div class="text-xs pf-muted">{{{{ props.row.phone }}}} · {{{{ props.row.location }}}}
      · último contato {{{{ props.row.last_contact }}}}</div>
    <div class="flex justify-end">{ACTIONS}</div>
  </div>
</div>""",
}

_STATUS_ORDER = {status: index for index, status in enumerate(LeadStatus)}


def lead_row(lead: Lead, reference: datetime) -> dict[str, Any]:
    """Converte um lead na linha da tabela (valores prontos para exibir)."""
    subtitle = " · ".join(p for p in (lead.contact_name, lead.category) if p)
    location = " · ".join(p for p in (lead.city, lead.neighborhood) if p)
    return {
        "id": lead.id,
        "company": lead.company_name,
        "subtitle": subtitle,
        "niche": lead.niche.name if lead.niche else "Sem nicho",
        "niche_color": safe_color(lead.niche.color if lead.niche else None),
        "status_label": lead.status.label,
        "status_color": STATUS_COLORS[lead.status],
        "status_order": _STATUS_ORDER[lead.status],
        "score": lead.priority_score,
        "score_label": f"{lead.priority_score} · {score_label(lead.priority_score)}",
        "score_color": score_color(lead.priority_score),
        "phone": format_phone(lead.phone),
        "wa_url": lead.whatsapp_url,
        "location": location or "—",
        "rating": format_rating(lead.google_rating) if lead.google_rating is not None else "",
        "reviews": f"({format_int(lead.review_count)})" if lead.review_count is not None else "",
        "rating_sort": (lead.google_rating or 0) * 100_000 + (lead.review_count or 0),
        "website": lead.website_status.label,
        "website_color": WEBSITE_COLORS[lead.website_status],
        "last_contact": relative_time(lead.last_contact_at, reference),
        "last_contact_iso": lead.last_contact_at.isoformat() if lead.last_contact_at else "",
    }


def _load_query() -> LeadQuery:
    """Filtros salvos neste navegador (conveniência por usuário)."""
    saved = app.storage.user.get(STORAGE_KEY) or {}
    try:
        return LeadQuery(
            search=saved.get("search", ""),
            niche_ids=list(saved.get("niche_ids", [])),
            statuses=[LeadStatus(s) for s in saved.get("statuses", [])],
            cities=list(saved.get("cities", [])),
            website=[WebsiteStatus(w) for w in saved.get("website", [])],
            min_score=int(saved.get("min_score", 0)),
        )
    except (ValueError, TypeError):
        return LeadQuery()


def _save_query(query: LeadQuery) -> None:
    data = asdict(query)
    data["statuses"] = [s.value for s in query.statuses]
    data["website"] = [w.value for w in query.website]
    data.pop("limit", None)
    app.storage.user[STORAGE_KEY] = data


class LeadsView:
    """Estado e interface da tela de leads."""

    def __init__(self) -> None:
        self.query = _load_query()
        self.query.limit = MAX_ROWS
        with session_scope() as session:
            self.niches = {n.id: n for n in NicheRepository(session).list()}
            self.city_options = LeadRepository(session).cities()
        self._build()
        self.reload()

    # -- estrutura -------------------------------------------------------------------

    def _build(self) -> None:
        with ui.row().classes("w-full items-center gap-2"):
            self.search = (
                ui.input(placeholder="Buscar empresa, contato, cidade, telefone…", value=self.query.search)
                .props("outlined dense clearable debounce=300")
                .classes("grow min-w-[220px]")
                .on_value_change(lambda e: self._update(search=e.value or ""))
            )
            with self.search.add_slot("prepend"):
                ui.icon("search")
            with ui.button_group().props("outline"):
                ui.button("CSV", icon="download", on_click=lambda: self._export("csv")).props(
                    "outline no-caps"
                ).tooltip("Exportar leads filtrados em CSV (Excel BR)")
                ui.button("Excel", on_click=lambda: self._export("xlsx")).props(
                    "outline no-caps"
                ).tooltip("Exportar leads filtrados em .xlsx")
            ui.button("Novo lead", icon="add", on_click=self._create).props("unelevated no-caps")

        with ui.row().classes("w-full items-center gap-2"):
            niche_options = {i: n.name for i, n in self.niches.items()} | {NO_NICHE: "Sem nicho"}
            self._multi(niche_options, "Nicho", self.query.niche_ids,
                        lambda v: self._update(niche_ids=list(v or [])))
            self._multi({s.value: s.label for s in LeadStatus}, "Status",
                        [s.value for s in self.query.statuses],
                        lambda v: self._update(statuses=[LeadStatus(x) for x in v or []]))
            self.city_select = self._multi({c: c for c in self.city_options}, "Cidade", self.query.cities,
                                           lambda v: self._update(cities=list(v or [])))
            self._multi({w.value: w.label for w in WebsiteStatus}, "Site",
                        [w.value for w in self.query.website],
                        lambda v: self._update(website=[WebsiteStatus(x) for x in v or []]))
            ui.select(SCORE_OPTIONS, value=self.query.min_score,
                      on_change=lambda e: self._update(min_score=int(e.value or 0))
                      ).props("outlined dense options-dense").classes("w-40")
            ui.button("Limpar", icon="filter_alt_off", on_click=self._clear).props("flat dense no-caps")

        self.toolbar()

        self.table = ui.table(
            columns=COLUMNS, rows=[], row_key="id", selection="multiple",
            pagination={"rowsPerPage": 25, "sortBy": None},
            on_select=lambda _: self.toolbar.refresh(),
        ).props(
            'flat wrap-cells :grid="$q.screen.lt.md" rows-per-page-label="Por página" '
            'no-data-label="Nenhum lead encontrado" :rows-per-page-options="[10,25,50,100,0]"'
        ).classes("pf-table w-full")
        for name, template in SLOTS.items():
            self.table.add_slot(name, template)
        self.table.on("edit", lambda e: self._edit(int(e.args)))
        self.table.on("remove", lambda e: self._delete([int(e.args)]))

        self.empty_box = ui.column().classes("w-full")

    def _multi(self, options: dict[Any, str], label: str, value: list[Any], handler: Any) -> ui.select:
        return (
            ui.select(options, label=label, value=value, multiple=True, clearable=True,
                      on_change=lambda e: handler(e.value))
            .props("outlined dense options-dense use-chips stack-label")
            .classes("min-w-[150px] max-w-[260px]")
        )

    # -- dados -----------------------------------------------------------------------

    def _update(self, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(self.query, key, value)
        _save_query(self.query)
        self.reload()

    def _clear(self) -> None:
        app.storage.user.pop(STORAGE_KEY, None)
        ui.navigate.reload()

    def reload(self) -> None:
        """Busca no banco e atualiza tabela, contadores e estado vazio."""
        with session_scope() as session:
            repo = LeadRepository(session)
            leads = repo.search(self.query)
            self.total = repo.count()
            reference = now()
            rows = [lead_row(lead, reference) for lead in leads]
        self.table.rows = rows
        visible_ids = {r["id"] for r in rows}
        self.table.selected = [r for r in self.table.selected if r["id"] in visible_ids]
        self.table.update()
        self.shown = len(rows)
        self.table.set_visibility(bool(rows))
        self._render_empty()
        self.toolbar.refresh()

    def _render_empty(self) -> None:
        self.empty_box.clear()
        if self.shown:
            return
        with self.empty_box:
            if self.total == 0:
                empty_state("group_add", "Nenhum lead ainda",
                            "Importe sua planilha do Google Maps ou cadastre o primeiro lead manualmente.",
                            "Importar planilha", lambda: ui.navigate.to("/importar"))
            else:
                empty_state("search_off", "Nenhum lead com esses filtros",
                            "Tente outro termo de busca ou limpe os filtros.", "Limpar filtros", self._clear)

    @ui.refreshable_method
    def toolbar(self) -> None:
        selected = getattr(self, "table", None) and self.table.selected
        with ui.row().classes("w-full items-center gap-3 min-h-[36px]"):
            if selected:
                ui.label(f"{len(selected)} selecionado(s)").classes("font-medium")
                with ui.button("Definir nicho", icon="sell").props("outline dense no-caps"):
                    with ui.menu():
                        for niche_id, niche in self.niches.items():
                            ui.menu_item(niche.name, on_click=lambda _, i=niche_id: self._bulk_niche(i))
                        ui.separator()
                        ui.menu_item("Sem nicho", on_click=lambda: self._bulk_niche(None))
                ui.button("Excluir", icon="delete_outline",
                          on_click=lambda: self._delete([r["id"] for r in self.table.selected])
                          ).props("outline dense no-caps color=negative")
                ui.button("Limpar seleção", on_click=self._clear_selection).props("flat dense no-caps")
            else:
                shown, total = getattr(self, "shown", 0), getattr(self, "total", 0)
                text = f"{shown} lead(s)" if shown == total else f"{shown} de {total} lead(s)"
                if shown >= MAX_ROWS:
                    text += f" — mostrando os {MAX_ROWS} primeiros; refine os filtros"
                ui.label(text).classes("text-sm pf-muted")

    def _clear_selection(self) -> None:
        self.table.selected = []
        self.table.update()
        self.toolbar.refresh()

    # -- ações -----------------------------------------------------------------------

    async def _create(self) -> None:
        if await LeadDialog().open():
            self._refresh_cities()
            self.reload()

    async def _edit(self, lead_id: int) -> None:
        if await LeadDialog(lead_id).open():
            self._refresh_cities()
            self.reload()

    def _refresh_cities(self) -> None:
        with session_scope() as session:
            self.city_options = LeadRepository(session).cities()
        self.city_select.set_options({c: c for c in self.city_options}, value=self.city_select.value)

    async def _delete(self, ids: list[int]) -> None:
        if not ids:
            return
        message = (
            "O lead, suas interações e venda serão excluídos. Esta ação não pode ser desfeita."
            if len(ids) == 1
            else f"{len(ids)} leads, com suas interações e vendas, serão excluídos. "
            "Esta ação não pode ser desfeita."
        )
        if not await confirm("Excluir lead(s)?", message, "Excluir", danger=True):
            return
        with session_scope() as session:
            deleted = LeadService(session).delete(ids)
        ui.notify(f"{deleted} lead(s) excluído(s).", type="positive")
        self.table.selected = []
        self.reload()

    def _bulk_niche(self, niche_id: int | None) -> None:
        ids = [r["id"] for r in self.table.selected]
        with session_scope() as session:
            changed = LeadService(session).set_niche(ids, niche_id)
        name = self.niches[niche_id].name if niche_id else "Sem nicho"
        ui.notify(f"{changed} lead(s) movido(s) para “{name}”.", type="positive")
        self.table.selected = []
        self.reload()

    def _export(self, fmt: str) -> None:
        query = LeadQuery(**{**asdict(self.query), "limit": None})
        with session_scope() as session:
            df = leads_to_dataframe(LeadRepository(session).search(query))
        if df.empty:
            ui.notify("Nada para exportar com os filtros atuais.", type="warning")
            return
        stamp = now().strftime("%Y%m%d-%H%M")
        if fmt == "csv":
            ui.download.content(to_csv_bytes(df), f"prospectflow-leads-{stamp}.csv", "text/csv")
        else:
            ui.download.content(
                to_xlsx_bytes(df), f"prospectflow-leads-{stamp}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ui.notify(f"{len(df)} lead(s) exportado(s).", type="positive")


def leads_page() -> None:
    """Tela de leads (rota ``/leads``)."""
    with page_frame("leads", "Leads", "Todos os negócios prospectados, com busca e filtros."):
        LeadsView()
