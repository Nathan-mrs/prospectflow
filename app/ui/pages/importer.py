"""Tela de importação: upload → mapeamento → pré-visualização → relatório."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from nicegui import events, run, ui

from app.config import BASE_DIR
from app.db import session_scope
from app.repositories import NicheRepository
from app.services.importing import (
    FIELDS_BY_KEY,
    TARGET_FIELDS,
    DuplicateStrategy,
    ImportPreview,
    ImportReport,
    MappingSuggestion,
    PreviewRow,
    RowStatus,
    SpreadsheetError,
    build_preview,
    commit_import,
    read_spreadsheet,
    suggest_mapping,
    validate_mapping,
)
from app.ui.components import stat_card
from app.ui.components.badges import badge_html, safe_color
from app.ui.formatting import format_phone
from app.ui.layout import page_frame

log = logging.getLogger(__name__)

SAMPLE_FILE = BASE_DIR / "samples" / "leads_exemplo.xlsx"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IGNORE = ""

PREVIEW_COLUMNS: list[dict[str, Any]] = [
    {"name": "row", "label": "Linha", "field": "row", "align": "left", "sortable": True},
    {"name": "company", "label": "Empresa", "field": "company", "align": "left", "sortable": True},
    {"name": "phone", "label": "Telefone", "field": "phone", "align": "left"},
    {"name": "city", "label": "Cidade", "field": "city", "align": "left", "sortable": True},
    {"name": "niche", "label": "Nicho", "field": "niche", "align": "left", "sortable": True},
    {"name": "score", "label": "Score", "field": "score", "align": "right", "sortable": True},
    {"name": "notes", "label": "Observações", "field": "notes", "align": "left"},
]

NICHE_SLOT = r"""
<q-td :props="props">
  <span class="pf-badge" :style="{background: props.row.niche_color + '1F', color: props.row.niche_color}">
    <span class="pf-dot" :style="{background: props.row.niche_color}"></span>{{ props.value }}
  </span>
</q-td>
"""

NOTES_SLOT = r"""
<q-td :props="props" style="white-space: normal; min-width: 220px">
  <div v-for="msg in props.row.errors" :key="'e'+msg" class="text-xs" style="color: var(--pf-danger)">● {{ msg }}</div>
  <div v-for="msg in props.row.warnings" :key="'w'+msg" class="text-xs" style="color: var(--pf-warning)">● {{ msg }}</div>
  <div v-if="props.row.duplicate" class="text-xs pf-muted">↺ {{ props.row.duplicate }}</div>
</q-td>
"""


# --------------------------------------------------------------------------- trabalho pesado (thread)


def _analyze(df: pd.DataFrame, mapping: dict[str, str], filename: str) -> tuple[ImportPreview, dict[int, str]]:
    with session_scope() as session:
        preview = build_preview(session, df, mapping, filename)
        colors = {n.id: safe_color(n.color) for n in NicheRepository(session).list()}
    return preview, colors


def _commit(preview: ImportPreview, strategy: DuplicateStrategy) -> ImportReport:
    with session_scope() as session:
        return commit_import(session, preview, strategy)


# --------------------------------------------------------------------------- assistente


class ImportWizard:
    """Estado e interface do assistente de importação (um por aba aberta)."""

    def __init__(self) -> None:
        self.filename = ""
        self.df: pd.DataFrame | None = None
        self.suggestions: list[MappingSuggestion] = []
        self.field_by_column: dict[str, str | None] = {}
        self.preview: ImportPreview | None = None
        self.niche_colors: dict[int, str] = {}
        self.strategy = DuplicateStrategy.SKIP
        self.report: ImportReport | None = None
        self._build()

    # -- estrutura -------------------------------------------------------------------

    def _build(self) -> None:
        with ui.stepper().props("flat animated alternative-labels").classes("w-full") as self.stepper:
            with ui.step("Arquivo", icon="upload_file"):
                self._upload_step()
            with ui.step("Colunas", icon="view_column"):
                self.mapping_view()
            with ui.step("Pré-visualização", icon="fact_check"):
                self.preview_view()
            with ui.step("Relatório", icon="task_alt"):
                self.report_view()

    # -- passo 1: upload -------------------------------------------------------------

    def _upload_step(self) -> None:
        with ui.column().classes("w-full gap-4"):
            with ui.element("div").classes("pf-dropzone w-full"):
                self.upload = (
                    ui.upload(
                        on_upload=self._on_upload,
                        on_rejected=lambda: ui.notify(
                            "Arquivo recusado: envie .xlsx ou .csv de até 10 MB.", type="warning"
                        ),
                        auto_upload=True,
                        max_file_size=MAX_UPLOAD_BYTES,
                        label="Arraste a planilha aqui ou clique no + para escolher",
                    )
                    .props('accept=".xlsx,.xlsm,.csv" flat')
                    .classes("w-full")
                )
            with ui.row().classes("w-full items-center justify-between gap-2"):
                ui.label(
                    "Aceita .xlsx e .csv. As colunas são detectadas automaticamente na próxima etapa."
                ).classes("text-sm pf-muted")
                if SAMPLE_FILE.exists():
                    ui.button(
                        "Usar planilha de exemplo", icon="science", on_click=self._load_sample
                    ).props("flat no-caps")

    async def _on_upload(self, e: events.UploadEventArguments) -> None:
        content = await e.file.read()
        self.upload.reset()
        await self._load(content, e.file.name)

    async def _load_sample(self) -> None:
        await self._load(Path(SAMPLE_FILE).read_bytes(), SAMPLE_FILE.name)

    async def _load(self, content: bytes, filename: str) -> None:
        try:
            df = await run.io_bound(read_spreadsheet, content, filename)
        except SpreadsheetError as exc:
            ui.notify(str(exc), type="negative", multi_line=True)
            return
        self.filename, self.df = filename, df
        self.suggestions = suggest_mapping(list(df.columns), df.head(50))
        self.field_by_column = {s.column: s.field for s in self.suggestions}
        auto = sum(1 for s in self.suggestions if s.field)
        ui.notify(
            f"{len(df)} linhas lidas · {auto} de {len(df.columns)} colunas reconhecidas",
            type="positive",
        )
        self.mapping_view.refresh()
        self.stepper.next()

    # -- passo 2: mapeamento ---------------------------------------------------------

    def _sample_values(self, column: str) -> str:
        if self.df is None:
            return ""
        values = [v for v in self.df[column].tolist() if str(v).strip()][:3]
        text = " · ".join(str(v)[:28] for v in values)
        return text or "(vazia)"

    def _on_field_change(self, column: str, value: str) -> None:
        new_field = value or None
        if new_field:
            for other, field in self.field_by_column.items():
                if other != column and field == new_field:
                    self.field_by_column[other] = None
                    ui.notify(
                        f"“{other}” deixou de ser {FIELDS_BY_KEY[new_field].label}.", type="info"
                    )
        self.field_by_column[column] = new_field
        self.mapping_view.refresh()

    @ui.refreshable_method
    def mapping_view(self) -> None:
        if self.df is None:
            ui.label("Envie uma planilha para continuar.").classes("pf-muted")
            return

        options = {IGNORE: "— Ignorar coluna —"} | {
            f.key: f.label + (" *" if f.required else "") for f in TARGET_FIELDS
        }
        confidence = {s.column: s for s in self.suggestions}

        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("description").classes("pf-muted")
            ui.label(self.filename).classes("font-medium")
            ui.label(f"· {len(self.df)} linhas · {len(self.df.columns)} colunas").classes("pf-muted")

        with ui.column().classes("w-full gap-2"):
            for column in self.df.columns:
                field = self.field_by_column.get(column)
                suggestion = confidence[column]
                with ui.element("div").classes(
                    "pf-card w-full px-4 py-3 grid grid-cols-1 md:grid-cols-12 gap-2 items-center"
                ):
                    with ui.column().classes("gap-0 md:col-span-5 min-w-0"):
                        ui.label(column).classes("font-medium truncate")
                        ui.label(self._sample_values(column)).classes("text-xs pf-muted truncate")
                    ui.icon("arrow_forward").classes("pf-muted hidden md:block md:col-span-1")
                    ui.select(
                        options,
                        value=field or IGNORE,
                        on_change=lambda e, c=column: self._on_field_change(c, e.value),
                    ).props("outlined dense options-dense").classes("md:col-span-4")
                    with ui.row().classes("md:col-span-2 md:justify-end"):
                        if field and field == suggestion.field and suggestion.confidence >= 0.9:
                            ui.html(badge_html("Automático", "#16A34A"), tag="span", sanitize=False)
                        elif field and field == suggestion.field:
                            ui.html(badge_html("Confira", "#D97706"), tag="span", sanitize=False).tooltip(
                                suggestion.reason
                            )
                        elif field:
                            ui.html(badge_html("Manual", "#4F46E5"), tag="span", sanitize=False)

        with ui.row().classes("w-full justify-between pt-2"):
            ui.button("Voltar", on_click=self.stepper.previous).props("flat no-caps")
            ui.button("Pré-visualizar", icon="arrow_forward", on_click=self._go_preview).props(
                "unelevated no-caps"
            )

    async def _go_preview(self) -> None:
        if self.df is None:
            ui.notify("Envie uma planilha primeiro.", type="warning")
            return
        mapping = {f: c for c, f in self.field_by_column.items() if f}
        errors = validate_mapping(mapping)
        if errors:
            ui.notify(" ".join(errors), type="warning")
            return
        notification = ui.notification("Analisando planilha…", spinner=True, timeout=None)
        try:
            self.preview, self.niche_colors = await run.io_bound(
                _analyze, self.df, mapping, self.filename
            )
        except Exception as exc:
            log.exception("Falha ao analisar a planilha")
            ui.notify(f"Não foi possível analisar a planilha: {exc}", type="negative")
            return
        finally:
            notification.dismiss()
        self.strategy = DuplicateStrategy.SKIP
        self.preview_view.refresh()
        self.stepper.next()

    # -- passo 3: pré-visualização ---------------------------------------------------

    def _table_rows(self, rows: list[PreviewRow]) -> list[dict[str, Any]]:
        return [
            {
                "row": r.row_number,
                "company": r.values.get("company_name") or "—",
                "phone": format_phone(r.values.get("phone")),
                "city": r.values.get("city") or "—",
                "niche": r.niche_name or "Sem nicho",
                "niche_color": self.niche_colors.get(r.niche_id or 0, "#71717A"),
                "score": r.score,
                "errors": r.errors,
                "warnings": r.warnings,
                "duplicate": r.duplicate.reason if r.duplicate else "",
            }
            for r in rows
        ]

    def _table(self, rows: list[PreviewRow], empty: str) -> None:
        if not rows:
            ui.label(empty).classes("pf-muted py-6")
            return
        table = ui.table(
            columns=PREVIEW_COLUMNS,
            rows=self._table_rows(rows),
            row_key="row",
            pagination={"rowsPerPage": 10, "sortBy": "row"},
        ).props("flat dense wrap-cells").classes("pf-table w-full")
        table.add_slot("body-cell-niche", NICHE_SLOT)
        table.add_slot("body-cell-notes", NOTES_SLOT)

    @ui.refreshable_method
    def preview_view(self) -> None:
        preview = self.preview
        if preview is None:
            ui.label("Confirme o mapeamento das colunas.").classes("pf-muted")
            return

        with ui.element("div").classes("grid grid-cols-2 md:grid-cols-4 gap-4 w-full"):
            stat_card("Novos", preview.new_count, "person_add", "var(--pf-success)")
            stat_card("Duplicados", preview.duplicate_count, "content_copy", "var(--pf-warning)")
            stat_card("Com erro", preview.error_count, "error_outline", "var(--pf-danger)")
            stat_card("Com avisos", preview.warning_count, "info", "#0EA5E9")

        by_status = {s: [r for r in preview.rows if r.status is s] for s in RowStatus}
        with ui.tabs().props("no-caps align=left inline-label").classes("w-full") as tabs:
            tab_new = ui.tab("new", f"Novos ({preview.new_count})", icon="person_add")
            tab_dup = ui.tab("dup", f"Duplicados ({preview.duplicate_count})", icon="content_copy")
            tab_err = ui.tab("err", f"Com erro ({preview.error_count})", icon="error_outline")
        with ui.tab_panels(tabs, value=tab_new).classes("w-full bg-transparent"):
            with ui.tab_panel(tab_new).classes("px-0"):
                self._table(by_status[RowStatus.NEW], "Nenhum lead novo nesta planilha.")
            with ui.tab_panel(tab_dup).classes("px-0"):
                self._table(by_status[RowStatus.DUPLICATE], "Nenhum duplicado encontrado. 🎉")
            with ui.tab_panel(tab_err).classes("px-0"):
                self._table(by_status[RowStatus.ERROR], "Nenhuma linha com erro. 🎉")

        if preview.updatable_count:
            with ui.element("div").classes("pf-card w-full p-4 flex flex-col gap-1"):
                ui.label("O que fazer com os duplicados que já estão no CRM?").classes("font-medium")
                ui.radio(
                    {
                        DuplicateStrategy.SKIP.value: "Ignorar (manter como está)",
                        DuplicateStrategy.UPDATE.value: (
                            f"Atualizar {preview.updatable_count} lead(s) com os dados novos"
                        ),
                    },
                    value=self.strategy.value,
                    on_change=lambda e: self._set_strategy(e.value),
                ).props("inline")
                ui.label(
                    "Atualizar preenche só os campos que vieram na planilha; status e histórico não mudam."
                ).classes("text-xs pf-muted")

        total = preview.new_count + (
            preview.updatable_count if self.strategy is DuplicateStrategy.UPDATE else 0
        )
        with ui.row().classes("w-full justify-between pt-2"):
            ui.button("Voltar", on_click=self.stepper.previous).props("flat no-caps")
            button = ui.button(
                f"Importar {preview.new_count} lead(s)" if total else "Nada para importar",
                icon="download_done",
                on_click=self._do_import,
            ).props("unelevated no-caps")
            if not total:
                button.disable()

    def _set_strategy(self, value: str) -> None:
        self.strategy = DuplicateStrategy(value)
        self.preview_view.refresh()

    async def _do_import(self) -> None:
        if self.preview is None:
            return
        try:
            self.report = await run.io_bound(_commit, self.preview, self.strategy)
        except Exception as exc:
            log.exception("Falha ao gravar a importação")
            ui.notify(f"Erro ao importar — nada foi gravado: {exc}", type="negative")
            return
        changed = self.report.created + self.report.updated
        ui.notify(f"{changed} lead(s) importado(s) com sucesso!", type="positive")
        self.report_view.refresh()
        self.stepper.next()

    # -- passo 4: relatório ----------------------------------------------------------

    @ui.refreshable_method
    def report_view(self) -> None:
        report = self.report
        if report is None:
            ui.label("O relatório aparece aqui após a importação.").classes("pf-muted")
            return

        with ui.row().classes("items-center gap-3"):
            ui.icon("check_circle", size="32px").style("color: var(--pf-success)")
            with ui.column().classes("gap-0"):
                ui.label("Importação concluída").classes("text-lg font-semibold")
                ui.label(f"{report.filename} · {report.total_rows} linhas analisadas").classes(
                    "text-sm pf-muted"
                )

        with ui.element("div").classes("grid grid-cols-2 md:grid-cols-4 gap-4 w-full"):
            stat_card("Criados", report.created, "person_add", "var(--pf-success)")
            stat_card("Atualizados", report.updated, "sync", "var(--pf-accent)")
            stat_card("Ignorados", report.skipped, "block", "var(--pf-warning)")
            stat_card("Com erro", len(report.errors), "error_outline", "var(--pf-danger)")

        with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 gap-4 w-full"):
            with ui.element("div").classes("pf-card p-4 flex flex-col gap-3"):
                ui.label("Leads novos por nicho").classes("pf-section")
                if report.by_niche:
                    with ui.row().classes("gap-2"):
                        for name, count in report.by_niche.items():
                            color = self._color_for(name)
                            ui.html(badge_html(f"{name} · {count}", color), tag="span", sanitize=False)
                else:
                    ui.label("Nenhum lead novo.").classes("pf-muted text-sm")
                if report.unclassified:
                    ui.label(
                        f"{report.unclassified} lead(s) ficaram sem nicho — ajuste as palavras-chave "
                        "em Configurações ou defina o nicho na tela de Leads."
                    ).classes("text-sm").style("color: var(--pf-warning)")

            with ui.element("div").classes("pf-card p-4 flex flex-col gap-2"):
                ui.label("Linhas não importadas por erro").classes("pf-section")
                if not report.errors:
                    ui.label("Nenhuma. 🎉").classes("pf-muted text-sm")
                for item in report.errors[:50]:
                    ui.label(f"Linha {item['row']}: {'; '.join(item['messages'])}").classes("text-sm")

        with ui.row().classes("w-full justify-end gap-2 pt-2"):
            ui.button("Importar outra planilha", icon="restart_alt", on_click=self._restart).props(
                "flat no-caps"
            )
            ui.button("Ver leads", icon="group", on_click=lambda: ui.navigate.to("/leads")).props(
                "unelevated no-caps"
            )

    def _color_for(self, niche_name: str) -> str:
        if self.preview:
            for row in self.preview.rows:
                if row.niche_name == niche_name and row.niche_id:
                    return self.niche_colors.get(row.niche_id, "#71717A")
        return "#71717A"

    def _restart(self) -> None:
        self.df, self.preview, self.report = None, None, None
        self.mapping_view.refresh()
        self.preview_view.refresh()
        self.report_view.refresh()
        self.stepper.set_value("Arquivo")  # volta ao passo 1


def import_page() -> None:
    """Tela de importação (rota ``/importar``)."""
    with page_frame(
        "import", "Importar planilha", "Traga os leads coletados no Google Maps (.xlsx ou .csv)."
    ):
        with ui.element("div").classes("pf-card w-full p-2 sm:p-4"):
            ImportWizard()
