"""Leitura de planilhas .xlsx/.csv para um DataFrame de strings."""

from __future__ import annotations

import csv
import io
from pathlib import PurePath

import pandas as pd

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".csv")
MAX_ROWS = 20_000


class SpreadsheetError(ValueError):
    """Planilha ilegível ou em formato não suportado (mensagem amigável)."""


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SpreadsheetError("Não foi possível identificar a codificação do CSV.")


def _read_csv(content: bytes) -> pd.DataFrame:
    text = _decode(content)
    sample = text[:5000]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return pd.read_csv(
        io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False, skip_blank_lines=True
    )


def _read_excel(content: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False, engine="openpyxl")


def read_spreadsheet(content: bytes, filename: str) -> pd.DataFrame:
    """Lê o arquivo e devolve um DataFrame só com strings, sem linhas/colunas vazias.

    Raises:
        SpreadsheetError: extensão não suportada, arquivo vazio ou corrompido.
    """
    extension = PurePath(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise SpreadsheetError(
            f"Formato “{extension or '?'}” não suportado. Envie um arquivo .xlsx ou .csv."
        )
    if not content:
        raise SpreadsheetError("O arquivo está vazio.")
    try:
        df = _read_csv(content) if extension == ".csv" else _read_excel(content)
    except SpreadsheetError:
        raise
    except Exception as exc:  # pandas/openpyxl levantam vários tipos
        raise SpreadsheetError(f"Não foi possível ler a planilha: {exc}") from exc

    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed:")]]
    df = df.map(lambda v: v.strip() if isinstance(v, str) else v)
    df = df[(df != "").any(axis=1)].reset_index(drop=True)

    if df.empty:
        raise SpreadsheetError("A planilha não tem linhas com dados.")
    if len(df) > MAX_ROWS:
        raise SpreadsheetError(f"A planilha tem {len(df)} linhas; o limite é {MAX_ROWS}.")
    return df
