"""Testes da leitura de planilhas."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services.importing.reader import SpreadsheetError, read_spreadsheet


def test_reads_semicolon_csv_in_cp1252() -> None:
    content = "Nome;Telefone;Cidade\nSalão Bella;(11) 98765-4321;São Paulo\n".encode("cp1252")
    df = read_spreadsheet(content, "leads.csv")
    assert list(df.columns) == ["Nome", "Telefone", "Cidade"]
    assert df.iloc[0]["Nome"] == "Salão Bella"


def test_reads_comma_csv_with_bom_and_drops_blank_rows() -> None:
    content = "﻿Nome,Fone\nA,1\n,\nB,2\n".encode()
    df = read_spreadsheet(content, "x.CSV")
    assert df["Nome"].tolist() == ["A", "B"]


def test_reads_xlsx_keeping_phone_as_text() -> None:
    buffer = io.BytesIO()
    pd.DataFrame({"Empresa": ["Pet Feliz"], "Fone": [11987654321], "Nota": [4.8]}).to_excel(
        buffer, index=False
    )
    df = read_spreadsheet(buffer.getvalue(), "planilha.xlsx")
    assert df.iloc[0]["Fone"] == "11987654321"
    assert df.iloc[0]["Nota"] == "4.8"


def test_strips_headers_and_drops_unnamed_columns() -> None:
    content = b" Nome ,,Cidade\nA,,SP\n"
    df = read_spreadsheet(content, "a.csv")
    assert list(df.columns) == ["Nome", "Cidade"]


@pytest.mark.parametrize(
    ("content", "filename", "message"),
    [
        (b"x", "leads.pdf", "não suportado"),
        (b"", "leads.csv", "vazio"),
        (b"Nome,Fone\n", "leads.csv", "não tem linhas"),
        (b"isto nao e um xlsx", "leads.xlsx", "Não foi possível ler"),
    ],
)
def test_friendly_errors(content: bytes, filename: str, message: str) -> None:
    with pytest.raises(SpreadsheetError, match=message):
        read_spreadsheet(content, filename)
