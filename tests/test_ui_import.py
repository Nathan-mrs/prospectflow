"""Testes de interface (navegador simulado) da tela de importação."""

from __future__ import annotations

from nicegui.testing import User
from sqlalchemy import func, select

from app.db import session_scope
from app.models import ImportBatch, Lead


async def see(user: User, text: str) -> None:
    """``should_see`` com mais paciência (até 5 s) para passos que rodam em thread."""
    await user.should_see(text, retries=50)


def _lead_count() -> int:
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(Lead)) or 0


async def _import_sample(user: User) -> None:
    user.find("Usar planilha de exemplo").click()
    await see(user, "leads_exemplo.xlsx")
    user.find("Pré-visualizar").click()
    await see(user, "Importar 26 lead(s)")
    user.find("Importar 26 lead(s)").click()
    await see(user, "Importação concluída")


async def test_import_sample_spreadsheet_end_to_end(app_db: None, user: User) -> None:
    await user.open("/importar")
    await user.should_see("Importar planilha")

    user.find("Usar planilha de exemplo").click()
    await see(user, "leads_exemplo.xlsx")
    await user.should_see("Automático")

    user.find("Pré-visualizar").click()
    await see(user, "Importar 26 lead(s)")
    await user.should_see("Duplicados")

    user.find("Importar 26 lead(s)").click()
    await see(user, "Importação concluída")
    await user.should_see("Leads novos por nicho")

    assert _lead_count() == 26
    with session_scope() as session:
        batch = session.scalars(select(ImportBatch)).one()
        assert (batch.created_count, batch.skipped_count, batch.error_count) == (26, 2, 3)


async def test_reimport_shows_duplicates_and_imports_nothing(app_db: None, user: User) -> None:
    await user.open("/importar")
    await _import_sample(user)

    user.find("Importar outra planilha").click()
    await see(user, "Envie uma planilha para continuar.")  # tela voltou ao início

    user.find("Usar planilha de exemplo").click()
    await see(user, "leads_exemplo.xlsx")
    user.find("Pré-visualizar").click()
    await see(user, "Nada para importar")
    await user.should_see("O que fazer com os duplicados")
    assert _lead_count() == 26
