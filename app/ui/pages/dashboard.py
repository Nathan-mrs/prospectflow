"""Dashboard: KPIs, abordagens, funil de conversão, nichos e faturamento."""

from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from typing import Any

from nicegui import events, ui

from app.clock import now
from app.db import session_scope
from app.models import LeadStatus
from app.services.metrics import approaches_by_day, funnel_counts, kpis, niche_metrics, revenue_by_month
from app.ui.components import empty_state, stat_card
from app.ui.components.badges import STATUS_COLORS, badge_html
from app.ui.formatting import format_money, format_percent
from app.ui.layout import page_frame

ACCENT = "#4F46E5"
PERIODS = {30: "Últimos 30 dias", 90: "Últimos 90 dias", 0: "Todo o período"}
_AXIS = {"axisLine": {"lineStyle": {"color": "#A1A1AA"}}, "axisLabel": {"color": "#A1A1AA"},
         "splitLine": {"lineStyle": {"color": "rgba(161,161,170,.18)"}}}
_BASE: dict[str, Any] = {
    "textStyle": {"fontFamily": "Inter, sans-serif"},
    "grid": {"left": 8, "right": 12, "top": 30, "bottom": 8, "containLabel": True},
    "tooltip": {"trigger": "axis"},
}


def _chart(options: dict[str, Any], height: str = "280px") -> ui.echart:
    return ui.echart({**_BASE, **options}).classes("w-full").style(f"height: {height}")


def _card(title: str, subtitle: str | None = None) -> ui.element:
    card = ui.element("div").classes("pf-card p-5 w-full min-w-0 flex flex-col gap-2")
    with card:
        ui.label(title).classes("font-semibold")
        if subtitle:
            ui.label(subtitle).classes("text-xs pf-muted")
    return card


class Dashboard:
    def __init__(self) -> None:
        self.period = 30
        self.weekly = False

    def build(self) -> None:
        with ui.row().classes("w-full items-center gap-3"):
            ui.select(PERIODS, value=self.period, on_change=self._on_period).props(
                "outlined dense"
            ).classes("w-52")
            ui.label("O período filtra conversões pelos leads abordados nele.").classes(
                "text-sm pf-muted gt-xs"
            )
        self.render()

    def _on_period(self, e: events.ValueChangeEventArguments) -> None:
        self.period = int(e.value)
        self.render.refresh()

    def _toggle_weekly(self, e: events.ValueChangeEventArguments) -> None:
        self.weekly = e.value == "Semana"
        self.render.refresh()

    @ui.refreshable_method
    def render(self) -> None:
        at = now()
        since = at - timedelta(days=self.period) if self.period else None
        with session_scope() as session:
            k = kpis(session, at)
            days = approaches_by_day(session, at.date() - timedelta(days=83 if self.weekly else 29), at.date())
            funnel = funnel_counts(session, since)
            niches = niche_metrics(session, since)
            revenue = revenue_by_month(session, at, 6)

        if not any(n.leads for n in niches):
            empty_state("insights", "Sem dados ainda",
                        "Importe leads e comece a abordar para ver suas métricas aqui.",
                        "Importar planilha", lambda: ui.navigate.to("/importar"))
            return

        delta = k.approaches_week - k.approaches_prev_week
        with ui.element("div").classes("grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4 w-full"):
            stat_card("Abordagens na semana", k.approaches_week, "send",
                      hint=f"{'+' if delta >= 0 else ''}{delta} vs. semana anterior")
            stat_card("Taxa de resposta", format_percent(k.response_rate), "chat", "#0EA5E9")
            stat_card("Taxa de fechamento", format_percent(k.close_rate), "handshake", "#16A34A")
            stat_card("Faturado no mês", format_money(k.revenue_month), "payments", "#16A34A")
            stat_card("MRR", format_money(k.mrr), "autorenew", "#8B5CF6")
            stat_card("Clientes", k.clients, "storefront", "#D97706")

        with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-2 gap-4 w-full"):
            with _card("Abordagens", "Primeiros contatos enviados"):
                ui.toggle(["Dia", "Semana"], value="Semana" if self.weekly else "Dia",
                          on_change=self._toggle_weekly).props("dense no-caps unelevated size=sm")
                self._approaches_chart(days)
            with _card("Funil de conversão", "Leads que chegaram a cada etapa"):
                self._funnel_chart(funnel)

        with _card("Conversão por nicho", "Taxas sobre os leads abordados · ranking por fechamento"):
            self._niche_chart(niches)
            self._niche_table(niches)

        with _card("Faturamento", "Vendas fechadas + mensalidades recebidas (últimos 6 meses)"):
            self._revenue_chart(revenue)

    # -- gráficos --------------------------------------------------------------------

    def _approaches_chart(self, days: list) -> None:
        if self.weekly:
            weeks: OrderedDict[str, int] = OrderedDict()
            for day, count in days:
                start = day - timedelta(days=day.weekday())
                key = start.strftime("%d/%m")
                weeks[key] = weeks.get(key, 0) + count
            labels, values = list(weeks), list(weeks.values())
        else:
            labels = [d.strftime("%d/%m") for d, _ in days]
            values = [c for _, c in days]
        _chart({
            "xAxis": {"type": "category", "data": labels, **_AXIS},
            "yAxis": {"type": "value", "minInterval": 1, **_AXIS},
            "series": [{"type": "bar", "data": values, "name": "Abordagens",
                        "itemStyle": {"color": ACCENT, "borderRadius": [4, 4, 0, 0]}}],
        })

    @staticmethod
    def _funnel_chart(funnel: list[tuple[LeadStatus, int]]) -> None:
        data = [{"name": s.label, "value": c, "itemStyle": {"color": STATUS_COLORS[s]}}
                for s, c in funnel if s is not LeadStatus.LOST]
        _chart({
            "tooltip": {"trigger": "item", "formatter": "{b}: {c}"},
            "series": [{
                "type": "funnel", "sort": "none", "gap": 3, "minSize": "8%",
                "left": "5%", "width": "90%", "top": 10, "bottom": 10,
                "label": {"show": True, "position": "inside", "formatter": "{b}  {c}", "color": "#fff",
                          "fontWeight": 600},
                "data": data,
            }],
        })

    @staticmethod
    def _niche_chart(niches: list) -> None:
        names = [n.name for n in niches]
        series = [
            ("Resposta", "#0EA5E9", [round(n.response_rate * 100, 1) for n in niches]),
            ("Prévia", "#8B5CF6", [round(n.preview_rate * 100, 1) for n in niches]),
            ("Fechamento", "#16A34A", [round(n.close_rate * 100, 1) for n in niches]),
        ]
        _chart({
            "legend": {"top": 0, "textStyle": {"color": "#A1A1AA"}},
            "xAxis": {"type": "category", "data": names, **_AXIS,
                      "axisLabel": {"color": "#A1A1AA", "interval": 0, "rotate": 20}},
            "yAxis": {"type": "value", "axisLabel": {"color": "#A1A1AA", "formatter": "{value}%"},
                      "splitLine": _AXIS["splitLine"]},
            "series": [{"type": "bar", "name": name, "data": data, "itemStyle": {"color": color},
                        "barMaxWidth": 18} for name, color, data in series],
        }, "300px")

    @staticmethod
    def _niche_table(niches: list) -> None:
        with ui.element("div").classes("w-full overflow-x-auto pt-2"):
            with ui.element("table").classes("pf-rank w-full text-sm"):
                with ui.element("thead"), ui.element("tr"):
                    for head in ("#", "Nicho", "Abordados", "Resposta", "Prévia", "Fechamento", "Vendas", "Receita"):
                        with ui.element("th").classes("text-left"):
                            ui.label(head)
                with ui.element("tbody"):
                    for rank, n in enumerate(niches, start=1):
                        with ui.element("tr"):
                            cells = (
                                f"{rank}º", None, str(n.contacted), format_percent(n.response_rate),
                                format_percent(n.preview_rate), format_percent(n.close_rate),
                                str(n.won), format_money(n.revenue),
                            )
                            for value in cells:
                                with ui.element("td"):
                                    if value is None:
                                        ui.html(badge_html(n.name, n.color), tag="span", sanitize=False)
                                    else:
                                        ui.label(value)

    @staticmethod
    def _revenue_chart(revenue: list) -> None:
        labels = [f"{k[5:]}/{k[2:4]}" for k, _, _ in revenue]
        _chart({
            "legend": {"top": 0, "textStyle": {"color": "#A1A1AA"}},
            "xAxis": {"type": "category", "data": labels, **_AXIS},
            "yAxis": {"type": "value", **_AXIS,
                      "axisLabel": {"color": "#A1A1AA", "formatter": "R$ {value}"}},
            "series": [
                {"type": "bar", "stack": "r", "name": "Vendas", "data": [float(s) for _, s, _ in revenue],
                 "itemStyle": {"color": ACCENT}},
                {"type": "bar", "stack": "r", "name": "Mensalidades", "data": [float(r) for _, _, r in revenue],
                 "itemStyle": {"color": "#8B5CF6", "borderRadius": [4, 4, 0, 0]}},
            ],
        })


def dashboard_page() -> None:
    with page_frame("dashboard", "Dashboard", "Conversão por nicho, faturamento e MRR."):
        Dashboard().build()
