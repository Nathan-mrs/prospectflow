"""Testes da exportação (e reimportação do arquivo exportado)."""

from __future__ import annotations

import io

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.repositories import LeadQuery, LeadRepository
from app.services.bootstrap import ensure_defaults
from app.services.export import EXPORT_COLUMNS, leads_to_dataframe, to_csv_bytes, to_xlsx_bytes
from app.services.importing import (
    build_preview,
    mapping_from_suggestions,
    read_spreadsheet,
    suggest_mapping,
)
from app.services.leads import LeadForm, LeadService


@pytest.fixture
def db(session: Session) -> Session:
    ensure_defaults(session)
    service = LeadService(session)
    service.create(LeadForm(company_name="Barbearia do Zé", category="Barbearia",
                            phone="11987654321", google_rating="4,8", review_count="312",
                            city="São Paulo"))
    service.create(LeadForm(company_name="Pet Feliz", category="Pet shop", phone="11912345678",
                            city="Guarulhos"))
    return session


def test_dataframe_has_readable_values(db: Session) -> None:
    df = leads_to_dataframe(LeadRepository(db).search(LeadQuery(sort_by="company_name", descending=False)))
    assert list(df.columns) == EXPORT_COLUMNS
    row = df.iloc[0]
    assert row["Nome"] == "Barbearia do Zé"
    assert row["Status"] == "Novo"
    assert row["Site"] == "Não"
    assert row["Telefone"] == "5511987654321"


def test_csv_uses_brazilian_excel_format(db: Session) -> None:
    content = to_csv_bytes(leads_to_dataframe(LeadRepository(db).search(LeadQuery())))
    assert content.startswith(b"\xef\xbb\xbf")  # BOM
    text = content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Nome;Contato;Nicho")
    assert "4,8" in text


def test_xlsx_opens_with_pandas(db: Session) -> None:
    content = to_xlsx_bytes(leads_to_dataframe(LeadRepository(db).search(LeadQuery())))
    df = pd.read_excel(io.BytesIO(content), dtype=str)
    assert len(df) == 2 and "Score" in df.columns


@pytest.mark.parametrize(("fmt", "filename"), [("csv", "leads.csv"), ("xlsx", "leads.xlsx")])
def test_exported_file_reimports_as_duplicates(db: Session, fmt: str, filename: str) -> None:
    df = leads_to_dataframe(LeadRepository(db).search(LeadQuery()))
    content = to_csv_bytes(df) if fmt == "csv" else to_xlsx_bytes(df)
    reread = read_spreadsheet(content, filename)
    mapping = mapping_from_suggestions(suggest_mapping(list(reread.columns), reread))
    assert mapping["company_name"] == "Nome" and mapping["contact_name"] == "Contato"
    assert mapping["niche"] == "Nicho" and mapping["phone"] == "Telefone"
    preview = build_preview(db, reread, mapping, filename)
    assert preview.duplicate_count == 2 and preview.error_count == 0
    assert all(r.values["google_rating"] in (4.8, None) for r in preview.rows)
