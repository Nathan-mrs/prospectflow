"""Exportação de leads para CSV/Excel.

Os cabeçalhos são os mesmos que a importação reconhece, então um arquivo
exportado pode ser reimportado (ex.: para outro computador).
"""

from __future__ import annotations

import io
from collections.abc import Sequence

import pandas as pd

from app.models import Lead

EXPORT_COLUMNS = [
    "Nome", "Contato", "Nicho", "Categoria", "Telefone", "Instagram", "Nota",
    "Nº de avaliações", "Site", "Bairro", "Cidade", "Link Maps", "Status", "Score",
    "Último contato", "Criado em", "Observações",
]

_WEBSITE_EXPORT = {"none": "Não", "bad": "Ruim", "yes": "Sim"}


def leads_to_dataframe(leads: Sequence[Lead]) -> pd.DataFrame:
    """Tabela com uma linha por lead, valores em formato legível."""
    rows = [
        {
            "Nome": lead.company_name,
            "Contato": lead.contact_name or "",
            "Nicho": lead.niche.name if lead.niche else "",
            "Categoria": lead.category or "",
            "Telefone": lead.phone or "",
            "Instagram": lead.instagram or "",
            "Nota": lead.google_rating,
            "Nº de avaliações": lead.review_count,
            "Site": _WEBSITE_EXPORT[lead.website_status.value],
            "Bairro": lead.neighborhood or "",
            "Cidade": lead.city or "",
            "Link Maps": lead.maps_url or "",
            "Status": lead.status.label,
            "Score": lead.priority_score,
            "Último contato": lead.last_contact_at.strftime("%d/%m/%Y %H:%M")
            if lead.last_contact_at
            else "",
            "Criado em": lead.created_at.strftime("%d/%m/%Y"),
            "Observações": lead.notes or "",
        }
        for lead in leads
    ]
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV no padrão do Excel brasileiro (``;`` e UTF-8 com BOM, decimal com vírgula)."""
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Leads") -> bytes:
    """Planilha .xlsx com largura de colunas ajustada e cabeçalho congelado."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        sheet = writer.sheets[sheet_name]
        sheet.freeze_panes = "A2"
        for column_cells in sheet.columns:
            width = max(len(str(c.value or "")) for c in column_cells) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(width, 8), 45)
        # telefone como texto, para o Excel não converter em notação científica
        phone_col = EXPORT_COLUMNS.index("Telefone") + 1
        for row in sheet.iter_rows(min_row=2, min_col=phone_col, max_col=phone_col):
            for cell in row:
                cell.number_format = "@"
    return buffer.getvalue()
