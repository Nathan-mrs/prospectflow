"""Orquestra a importação: normaliza → classifica → deduplica → pré-visualiza → grava.

Fluxo usado pela tela de importação::

    df = read_spreadsheet(content, filename)
    suggestions = suggest_mapping(list(df.columns), df.head(50))
    preview = build_preview(session, df, mapping, filename)   # nada é gravado
    report = commit_import(session, preview, DuplicateStrategy.SKIP)
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ImportBatch, Lead, WebsiteStatus
from app.repositories import LeadRepository, NicheRepository, SettingRepository
from app.services.importing.classifier import NicheClassifier, NicheRule
from app.services.importing.deduplicator import DuplicateIndex, DuplicateMatch
from app.services.importing.normalizer import (
    normalize_instagram,
    normalize_name,
    normalize_phone,
    normalize_place,
    normalize_text,
    normalize_url,
    parse_rating,
    parse_review_count,
    parse_website,
)
from app.services.score import ScoreWeights, calculate_priority_score


class RowStatus(StrEnum):
    """Classificação de cada linha na pré-visualização."""

    NEW = "new"
    DUPLICATE = "duplicate"
    ERROR = "error"


class DuplicateStrategy(StrEnum):
    """O que fazer com linhas que já existem no CRM."""

    SKIP = "skip"
    UPDATE = "update"


@dataclass
class PreviewRow:
    """Uma linha da planilha já normalizada."""

    row_number: int
    status: RowStatus
    values: dict[str, Any]
    niche_id: int | None = None
    niche_name: str | None = None
    score: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicate: DuplicateMatch | None = None

    @property
    def can_update(self) -> bool:
        """Duplicata de um lead do banco (não de outra linha da planilha)."""
        return self.duplicate is not None and self.duplicate.lead_id is not None


@dataclass
class ImportPreview:
    """Resultado da análise, antes de gravar."""

    filename: str
    rows: list[PreviewRow]

    def _count(self, status: RowStatus) -> int:
        return sum(1 for r in self.rows if r.status is status)

    @property
    def new_count(self) -> int:
        return self._count(RowStatus.NEW)

    @property
    def duplicate_count(self) -> int:
        return self._count(RowStatus.DUPLICATE)

    @property
    def error_count(self) -> int:
        return self._count(RowStatus.ERROR)

    @property
    def updatable_count(self) -> int:
        return sum(1 for r in self.rows if r.status is RowStatus.DUPLICATE and r.can_update)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.rows if r.warnings and r.status is not RowStatus.ERROR)

    @property
    def unclassified_count(self) -> int:
        return sum(1 for r in self.rows if r.status is RowStatus.NEW and r.niche_id is None)


@dataclass
class ImportReport:
    """Relatório final exibido após a importação."""

    batch_id: int
    filename: str
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: list[dict[str, Any]]
    by_niche: dict[str, int]
    unclassified: int


# --------------------------------------------------------------------------- normalização


def normalize_row(
    raw: Mapping[str, Any], mapping: Mapping[str, str], default_ddd: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Converte uma linha bruta em campos do lead.

    Args:
        raw: valores da linha indexados pelo nome da coluna original.
        mapping: ``{campo: coluna}``.
        default_ddd: DDD usado para telefones sem DDD.

    Returns:
        ``(valores, avisos, erros)`` — ``valores`` contém só os campos mapeados.
    """

    def cell(key: str) -> Any:
        column = mapping.get(key)
        return raw.get(column) if column else None

    values: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []

    company = normalize_name(cell("company_name"))
    if not company:
        errors.append("Nome da empresa vazio")
    values["company_name"] = company

    if "contact_name" in mapping:
        values["contact_name"] = normalize_name(cell("contact_name"))

    if "phone" in mapping:
        phone = normalize_phone(cell("phone"), default_ddd)
        values["phone"] = phone.value
        warnings += phone.warnings
        errors += phone.errors
    else:
        values["phone"] = None
        warnings.append("Sem telefone")

    if "google_rating" in mapping:
        rating = parse_rating(cell("google_rating"))
        values["google_rating"] = rating.value
        warnings += rating.warnings
    if "review_count" in mapping:
        reviews = parse_review_count(cell("review_count"))
        values["review_count"] = reviews.value
        warnings += reviews.warnings

    values["website_status"] = (
        parse_website(cell("website")) if "website" in mapping else WebsiteStatus.NONE
    )

    simple_fields = {
        "category": normalize_text,
        "instagram": normalize_instagram,
        "neighborhood": normalize_place,
        "city": normalize_place,
        "maps_url": normalize_url,
        "notes": normalize_text,
    }
    for key, func in simple_fields.items():
        if key in mapping:
            values[key] = func(cell(key))

    return values, warnings, errors


# --------------------------------------------------------------------------- pré-visualização


def _classifier(session: Session) -> NicheClassifier:
    niches = NicheRepository(session).list(only_active=True)
    return NicheClassifier(NicheRule.build(n.id, n.name, n.keywords) for n in niches)


def build_preview(
    session: Session,
    df: pd.DataFrame,
    mapping: Mapping[str, str],
    filename: str,
    default_ddd: str | None = None,
) -> ImportPreview:
    """Analisa a planilha inteira sem gravar nada no banco."""
    ddd = default_ddd or get_settings().default_ddd
    classifier = _classifier(session)
    weights = ScoreWeights.from_settings(SettingRepository(session).all())
    index = DuplicateIndex.from_leads(LeadRepository(session).dedup_keys())
    niche_column = mapping.get("niche")

    rows: list[PreviewRow] = []
    for position, raw in enumerate(df.to_dict(orient="records")):
        row_number = position + 2  # linha 1 = cabeçalho
        values, warnings, errors = normalize_row(raw, mapping, ddd)

        rule = classifier.classify(
            category=values.get("category"),
            company_name=values.get("company_name"),
            explicit_niche=str(raw.get(niche_column, "")) if niche_column else None,
        )
        if rule is None and not errors:
            warnings.append("Nicho não identificado")

        row = PreviewRow(
            row_number=row_number,
            status=RowStatus.ERROR if errors else RowStatus.NEW,
            values=values,
            niche_id=rule.niche_id if rule else None,
            niche_name=rule.name if rule else None,
            score=calculate_priority_score(
                values.get("google_rating"),
                values.get("review_count"),
                values.get("website_status"),
                weights,
            ),
            warnings=warnings,
            errors=errors,
        )

        if not errors:
            match = index.check(values.get("phone"), values.get("company_name"), values.get("city"))
            if match:
                row.status = RowStatus.DUPLICATE
                row.duplicate = match
            else:
                index.remember(
                    row_number, values.get("phone"), values.get("company_name"), values.get("city")
                )
        rows.append(row)

    return ImportPreview(filename=filename, rows=rows)


# --------------------------------------------------------------------------- gravação


def _apply_update(lead: Lead, row: PreviewRow, weights: ScoreWeights) -> None:
    """Atualiza só campos que vieram preenchidos; não mexe em status/histórico."""
    for key, value in row.values.items():
        if value is None:
            continue
        if key == "website_status" and value is WebsiteStatus.NONE:
            continue  # "sem site" é o padrão; não rebaixa informação existente
        setattr(lead, key, value)
    if row.niche_id and lead.niche_id is None:
        lead.niche_id = row.niche_id
    lead.priority_score = calculate_priority_score(
        lead.google_rating, lead.review_count, lead.website_status, weights
    )


def commit_import(
    session: Session, preview: ImportPreview, strategy: DuplicateStrategy = DuplicateStrategy.SKIP
) -> ImportReport:
    """Grava a pré-visualização e registra o lote. Não faz commit da sessão."""
    weights = ScoreWeights.from_settings(SettingRepository(session).all())
    leads = LeadRepository(session)
    batch = ImportBatch(filename=preview.filename, total_rows=len(preview.rows))
    session.add(batch)

    created = updated = skipped = 0
    by_niche: Counter[str] = Counter()
    unclassified = 0
    error_rows: list[dict[str, Any]] = []

    for row in preview.rows:
        if row.status is RowStatus.ERROR:
            error_rows.append({"row": row.row_number, "messages": row.errors})
            continue

        if row.status is RowStatus.DUPLICATE:
            match = row.duplicate
            if strategy is DuplicateStrategy.UPDATE and match and match.lead_id is not None:
                lead = leads.get(match.lead_id)
                if lead is not None:
                    _apply_update(lead, row, weights)
                    updated += 1
                    continue
            skipped += 1
            continue

        lead = Lead(**row.values, niche_id=row.niche_id, priority_score=row.score)
        lead.import_batch = batch
        leads.add_new(lead)
        created += 1
        if row.niche_name:
            by_niche[row.niche_name] += 1
        else:
            unclassified += 1

    batch.created_count = created
    batch.updated_count = updated
    batch.skipped_count = skipped
    batch.error_count = len(error_rows)
    batch.errors = error_rows
    session.flush()

    return ImportReport(
        batch_id=batch.id,
        filename=preview.filename,
        total_rows=len(preview.rows),
        created=created,
        updated=updated,
        skipped=skipped,
        errors=error_rows,
        by_niche=dict(by_niche.most_common()),
        unclassified=unclassified,
    )
