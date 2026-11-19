"""Testes de ponta a ponta da importação (pré-visualização + gravação)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportBatch, Lead, LeadStatus, Niche, StatusHistory, WebsiteStatus
from app.services.bootstrap import ensure_defaults
from app.services.importing import (
    DuplicateStrategy,
    RowStatus,
    build_preview,
    commit_import,
    mapping_from_suggestions,
    read_spreadsheet,
    suggest_mapping,
)

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

MAPPING = {
    "company_name": "Nome",
    "category": "Categoria",
    "phone": "Telefone",
    "google_rating": "Nota",
    "review_count": "Avaliações",
    "website": "Site",
    "city": "Cidade",
}


@pytest.fixture
def db(session: Session) -> Session:
    ensure_defaults(session)
    return session


def _df(*rows: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(list(rows)).fillna("")


def _row(name: str, phone: str = "", city: str = "São Paulo", **extra: str) -> dict[str, str]:
    base = {
        "Nome": name, "Categoria": "Barbearia", "Telefone": phone, "Nota": "4,8",
        "Avaliações": "120", "Site": "", "Cidade": city,
    }
    return base | extra


def test_preview_classifies_rows_without_writing(db: Session) -> None:
    df = _df(
        _row("BARBEARIA DO ZÉ", "(11) 98765-4321"),
        _row("", "(11) 91111-2222"),  # sem nome → erro
        _row("Barber King", "123"),  # telefone inválido → erro
        _row("Barbearia do Zé", "(11) 97777-6666"),  # mesmo nome+cidade da linha 2
    )
    preview = build_preview(db, df, MAPPING, "teste.csv")

    assert [r.status for r in preview.rows] == [
        RowStatus.NEW, RowStatus.ERROR, RowStatus.ERROR, RowStatus.DUPLICATE,
    ]
    first = preview.rows[0]
    assert first.row_number == 2
    assert first.values["company_name"] == "Barbearia do Zé"
    assert first.values["phone"] == "5511987654321"
    assert first.values["google_rating"] == 4.8
    assert first.niche_name == "Barbearias"
    assert first.score > 0
    assert preview.rows[3].duplicate is not None and preview.rows[3].duplicate.row_number == 2
    assert (preview.new_count, preview.error_count, preview.duplicate_count) == (1, 2, 1)
    assert db.scalars(select(Lead)).first() is None  # nada gravado


def test_commit_creates_leads_with_history_and_batch(db: Session) -> None:
    df = _df(_row("Barbearia do Zé", "11987654321"), _row("Pet Feliz", "11912345678", Categoria="Pet shop"))
    report = commit_import(db, build_preview(db, df, MAPPING, "leads.xlsx"))

    assert (report.created, report.updated, report.skipped) == (2, 0, 0)
    assert report.by_niche == {"Barbearias": 1, "Pet Shops": 1}
    leads = db.scalars(select(Lead).order_by(Lead.id)).all()
    assert all(lead.status is LeadStatus.NEW for lead in leads)
    assert all(lead.import_batch_id == report.batch_id for lead in leads)
    assert len(db.scalars(select(StatusHistory)).all()) == 2
    batch = db.get(ImportBatch, report.batch_id)
    assert batch is not None and batch.created_count == 2 and batch.filename == "leads.xlsx"


def test_reimport_skips_duplicates_by_default(db: Session) -> None:
    df = _df(_row("Barbearia do Zé", "11987654321"))
    commit_import(db, build_preview(db, df, MAPPING, "a.csv"))

    preview = build_preview(db, df, MAPPING, "a.csv")
    assert preview.duplicate_count == 1 and preview.updatable_count == 1
    report = commit_import(db, preview)
    assert (report.created, report.skipped) == (0, 1)
    assert len(db.scalars(select(Lead)).all()) == 1


def test_update_strategy_fills_fields_and_keeps_status(db: Session) -> None:
    commit_import(db, build_preview(db, _df(_row("Barbearia do Zé", "11987654321", Nota="")), MAPPING, "a.csv"))
    lead = db.scalars(select(Lead)).one()
    lead.status = LeadStatus.CONTACTED
    old_score = lead.priority_score

    newer = _df(_row("Barbearia do Zé", "11987654321", Nota="4,9", Site="ruim"))
    report = commit_import(db, build_preview(db, newer, MAPPING, "b.csv"), DuplicateStrategy.UPDATE)

    assert report.updated == 1
    db.refresh(lead)
    assert lead.google_rating == 4.9
    assert lead.website_status is WebsiteStatus.BAD
    assert lead.status is LeadStatus.CONTACTED  # status preservado
    assert lead.priority_score != old_score  # score recalculado


def test_update_does_not_erase_existing_values(db: Session) -> None:
    commit_import(db, build_preview(db, _df(_row("Pet Feliz", "11912345678", Site="Sim")), MAPPING, "a.csv"))
    blank = _df(_row("Pet Feliz", "11912345678", Nota="", Site=""))
    commit_import(db, build_preview(db, blank, MAPPING, "b.csv"), DuplicateStrategy.UPDATE)
    lead = db.scalars(select(Lead)).one()
    assert lead.google_rating == 4.8
    assert lead.website_status is WebsiteStatus.YES


def test_unknown_niche_is_reported(db: Session) -> None:
    df = _df(_row("Silva Contabilidade", "11955554444", Categoria="Contabilidade"))
    preview = build_preview(db, df, MAPPING, "a.csv")
    assert preview.unclassified_count == 1
    assert "Nicho não identificado" in preview.rows[0].warnings
    report = commit_import(db, preview)
    assert report.unclassified == 1
    assert db.scalars(select(Lead)).one().niche_id is None


def test_inactive_niche_is_not_used(db: Session) -> None:
    db.scalars(select(Niche).where(Niche.name == "Barbearias")).one().active = False
    preview = build_preview(db, _df(_row("Barbearia X", "11955554444")), MAPPING, "a.csv")
    assert preview.rows[0].niche_id is None


@pytest.mark.parametrize("filename", ["leads_exemplo.xlsx", "leads_exemplo.csv"])
def test_sample_spreadsheets_import_end_to_end(db: Session, filename: str) -> None:
    path = SAMPLES / filename
    df = read_spreadsheet(path.read_bytes(), filename)
    mapping = mapping_from_suggestions(suggest_mapping(list(df.columns), df.head(50)))

    assert {"company_name", "phone", "category", "city", "google_rating", "review_count"} <= set(mapping)
    preview = build_preview(db, df, mapping, filename)
    assert preview.new_count >= 20
    assert preview.duplicate_count >= 2  # a amostra tem duplicatas propositais
    assert preview.error_count >= 2  # e linhas com erro
    report = commit_import(db, preview)
    assert report.created == preview.new_count
    assert len(report.by_niche) == 7
