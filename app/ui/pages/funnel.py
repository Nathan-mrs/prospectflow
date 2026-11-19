"""Funil em Kanban com arrastar e soltar (SortableJS).

O SortableJS move o card no DOM; nós desfazemos esse movimento no navegador e
avisamos o servidor (``pf_move``). O servidor aplica a regra de negócio
(plano ao fechar, motivo ao perder) e redesenha o quadro — assim o Vue
continua dono do DOM e o quadro nunca mostra um estado que não foi salvo.
"""

from __future__ import annotations

from typing import Any

from nicegui import events, ui
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.clock import now
from app.db import session_scope
from app.models import BOARD_ORDER, Lead, LeadStatus
from app.repositories import NicheRepository
from app.ui.components import empty_state
from app.ui.components.badges import STATUS_COLORS, badge_html, safe_color, score_color
from app.ui.components.funnel_actions import move_lead
from app.ui.components.lead_dialog import LeadDialog
from app.ui.formatting import relative_time
from app.ui.layout import page_frame

SORTABLE_CDN = "https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"
CARDS_PER_COLUMN = 60  # colunas grandes (ex.: "Novo") mostram só os de maior score

KANBAN_JS = """
<script>
window.pfInitKanban = function () {
  if (!window.Sortable) { return setTimeout(window.pfInitKanban, 100); }
  document.querySelectorAll('.pf-kanban-list').forEach((el) => {
    if (el._pfSortable) el._pfSortable.destroy();
    el._pfSortable = Sortable.create(el, {
      group: 'pf-kanban', sort: false, animation: 150,
      draggable: '.pf-kcard', ghostClass: 'pf-kghost', delay: 120, delayOnTouchOnly: true,
      onEnd: (evt) => {
        if (evt.from === evt.to) return;
        const item = evt.item;
        evt.from.insertBefore(item, evt.from.children[evt.oldIndex] || null);  // devolve ao Vue
        emitEvent('pf_move', { id: Number(item.dataset.lead), to: evt.to.dataset.status });
      },
    });
  });
};
</script>
<style>
.pf-kanban { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(260px, 1fr);
  gap: 12px; overflow-x: auto; padding-bottom: 8px; }
.pf-kanban-col { background: var(--pf-surface-2, var(--pf-bg)); border: 1px solid var(--pf-border);
  border-radius: 14px; padding: 10px; display: flex; flex-direction: column; min-height: 200px; }
.pf-kanban-list { display: flex; flex-direction: column; gap: 8px; flex: 1; min-height: 80px; }
.pf-kcard { background: var(--pf-surface); border: 1px solid var(--pf-border); border-radius: 10px;
  padding: 10px 12px; cursor: grab; box-shadow: var(--pf-shadow); transition: transform .12s; }
.pf-kcard:hover { transform: translateY(-1px); }
.pf-kghost { opacity: .35; }
</style>
"""


def _card_data(lead: Lead, reference: Any) -> dict[str, Any]:
    return {
        "id": lead.id,
        "company": lead.company_name,
        "city": lead.city or "",
        "score": lead.priority_score,
        "niche": lead.niche.name if lead.niche else None,
        "niche_color": safe_color(lead.niche.color if lead.niche else None),
        "when": relative_time(lead.status_changed_at or lead.created_at, reference),
        "plan": lead.sale.plan.label if lead.sale else None,
        "followups": lead.followup_count,
    }


class FunnelBoard:
    """Quadro Kanban com filtro por nicho."""

    def __init__(self) -> None:
        with session_scope() as session:
            self.niche_options = {0: "Todos os nichos"} | {
                n.id: n.name for n in NicheRepository(session).list()
            }
        self.niche_id = 0
        self.search = ""

    def load(self) -> tuple[dict[LeadStatus, list[dict[str, Any]]], dict[LeadStatus, int]]:
        reference = now()
        columns: dict[LeadStatus, list[dict[str, Any]]] = {s: [] for s in BOARD_ORDER}
        totals: dict[LeadStatus, int] = dict.fromkeys(BOARD_ORDER, 0)
        with session_scope() as session:
            stmt = select(Lead).options(selectinload(Lead.niche), selectinload(Lead.sale))
            if self.niche_id:
                stmt = stmt.where(Lead.niche_id == self.niche_id)
            if self.search:
                stmt = stmt.where(Lead.company_name.ilike(f"%{self.search}%"))
            stmt = stmt.order_by(Lead.priority_score.desc(), Lead.id)
            for lead in session.scalars(stmt):
                totals[lead.status] += 1
                if len(columns[lead.status]) < CARDS_PER_COLUMN:
                    columns[lead.status].append(_card_data(lead, reference))
        return columns, totals

    def build(self) -> None:
        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            ui.input(placeholder="Buscar empresa…", on_change=self._on_search).props(
                "outlined dense clearable debounce=300"
            ).classes("w-64")
            ui.select(self.niche_options, value=0, on_change=self._on_niche).props(
                "outlined dense"
            ).classes("w-56")
            ui.space()
            ui.label("Arraste os cards entre as colunas · clique para abrir").classes(
                "text-sm pf-muted gt-xs"
            )
        self.board()

    @ui.refreshable_method
    def board(self) -> None:
        columns, totals = self.load()
        if not any(totals.values()):
            empty_state("view_kanban", "Nenhum lead no funil",
                        "Importe uma planilha ou ajuste os filtros.",
                        "Importar planilha", lambda: ui.navigate.to("/importar"))
            return
        with ui.element("div").classes("pf-kanban w-full"):
            for status in BOARD_ORDER:
                color = STATUS_COLORS[status]
                with ui.element("div").classes("pf-kanban-col"):
                    with ui.row().classes("items-center justify-between px-1 pb-2"):
                        ui.html(badge_html(status.label, color), tag="span", sanitize=False)
                        ui.label(str(totals[status])).classes("text-sm pf-muted font-medium")
                    with ui.element("div").classes("pf-kanban-list").props(
                        f"data-status={status.value}"
                    ):
                        for card in columns[status]:
                            self._card(card)
                    hidden = totals[status] - len(columns[status])
                    if hidden > 0:
                        ui.label(f"+ {hidden} com score menor").classes("text-xs pf-muted px-1 pt-2")
        ui.timer(0.05, lambda: ui.run_javascript("window.pfInitKanban && window.pfInitKanban()"),
                 once=True)

    def _card(self, card: dict[str, Any]) -> None:
        with ui.element("div").classes("pf-kcard").props(f"data-lead={card['id']}").on(
            "click", lambda _, i=card["id"]: self._open(i)
        ):
            with ui.row().classes("items-start justify-between gap-2 no-wrap"):
                ui.label(card["company"]).classes("text-sm font-semibold leading-snug")
                ui.label(str(card["score"])).classes("text-xs font-bold").style(
                    f"color: {score_color(card['score'])}"
                )
            with ui.row().classes("items-center gap-1 pt-1 flex-wrap"):
                if card["niche"]:
                    ui.html(badge_html(card["niche"], card["niche_color"]), tag="span", sanitize=False)
                if card["plan"]:
                    ui.html(badge_html(card["plan"], "#16A34A", dot=False), tag="span", sanitize=False)
            meta = " · ".join(
                part for part in (
                    card["city"], card["when"],
                    f"{card['followups']} follow-up(s)" if card["followups"] else "",
                ) if part
            )
            ui.label(meta).classes("text-xs pf-muted pt-1")

    async def _open(self, lead_id: int) -> None:
        if await LeadDialog(lead_id).open():
            self.board.refresh()

    async def on_move(self, e: events.GenericEventArguments) -> None:
        try:
            lead_id, to_status = int(e.args["id"]), LeadStatus(e.args["to"])
        except (KeyError, TypeError, ValueError):
            return
        await move_lead(lead_id, to_status)
        self.board.refresh()

    def _on_search(self, e: events.ValueChangeEventArguments) -> None:
        self.search = (e.value or "").strip()
        self.board.refresh()

    def _on_niche(self, e: events.ValueChangeEventArguments) -> None:
        self.niche_id = int(e.value or 0)
        self.board.refresh()


def funnel_page() -> None:
    ui.add_head_html(f'<script src="{SORTABLE_CDN}"></script>' + KANBAN_JS)
    with page_frame("funnel", "Funil", "Arraste os leads entre as etapas da negociação."):
        board = FunnelBoard()
        board.build()
        ui.on("pf_move", board.on_move)
