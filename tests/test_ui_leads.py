"""Testes de interface (navegador simulado) da tela de Leads."""

from __future__ import annotations

from typing import Any

from nicegui import ui
from nicegui.testing import User
from sqlalchemy import select

from app.db import session_scope
from app.models import Lead
from app.services.leads import LeadForm, LeadService


async def see(user: User, text: str) -> None:
    await user.should_see(text, retries=50)


def _create(**kwargs: Any) -> int:
    with session_scope() as session:
        lead, _ = LeadService(session).create(LeadForm(**kwargs))
        return lead.id


def _rows(user: User) -> list[dict[str, Any]]:
    table = next(iter(user.find(ui.table).elements))
    return table.rows


def _companies(user: User) -> list[str]:
    return [row["company"] for row in _rows(user)]


async def test_empty_state_when_no_leads(app_db: None, user: User) -> None:
    await user.open("/leads")
    await user.should_see("Nenhum lead ainda")
    await user.should_see("Importar planilha")


async def test_lists_leads_ordered_by_score(app_db: None, user: User) -> None:
    await user.open("/leads")  # inicializa o banco
    _create(company_name="Baixa Prioridade", website_status="yes")
    _create(company_name="Alta Prioridade", google_rating="4,9", review_count="400", phone="11987654321")
    await user.open("/leads")
    assert _companies(user) == ["Alta Prioridade", "Baixa Prioridade"]
    row = _rows(user)[0]
    assert row["phone"] == "(11) 98765-4321"
    assert row["wa_url"] == "https://wa.me/5511987654321"
    await user.should_see("2 lead(s)")


async def test_search_filters_rows(app_db: None, user: User) -> None:
    await user.open("/leads")
    _create(company_name="Salão Bella", city="São Paulo")
    _create(company_name="Pet Feliz", city="Guarulhos")
    await user.open("/leads")
    user.find(kind=ui.input, marker=None, content=None)  # garante que há inputs
    search = next(e for e in user.find(ui.input).elements if "Buscar" in str(e.props.get("placeholder")))
    search.value = "salao"
    await see(user, "1 de 2 lead(s)")
    assert _companies(user) == ["Salão Bella"]


async def test_create_lead_through_dialog(app_db: None, user: User) -> None:
    await user.open("/leads")
    user.find("Novo lead").click()
    await see(user, "Empresa *")
    user.find("Empresa *").type("barbearia nova era")
    user.find("WhatsApp").type("(11) 91234-5678")
    user.find("Salvar").click()
    await see(user, "“Barbearia Nova Era” salvo.")
    await see(user, "1 lead(s)")  # tabela recarregada após fechar o diálogo
    with session_scope() as session:
        lead = session.scalars(select(Lead)).one()
        assert lead.phone == "5511912345678"
    assert _companies(user) == ["Barbearia Nova Era"]


async def test_dialog_shows_validation_errors(app_db: None, user: User) -> None:
    await user.open("/leads")
    user.find("Novo lead").click()
    await see(user, "Empresa *")
    user.find("WhatsApp").type("123")
    user.find("Salvar").click()
    await see(user, "Corrija os campos destacados.")
    company = next(iter(user.find("Empresa *").elements))
    assert company.props.get("error-message") == "Informe o nome da empresa."
    with session_scope() as session:
        assert session.scalars(select(Lead)).first() is None


async def test_edit_lead_from_table_event(app_db: None, user: User) -> None:
    await user.open("/leads")
    lead_id = _create(company_name="Pet Feliz", city="Guarulhos")
    await user.open("/leads")
    user.find(ui.table).trigger("edit", lead_id)
    await see(user, "Editar lead")
    await user.should_see("Histórico (1)")
    user.find("Bairro").type("Centro")
    user.find("Salvar").click()
    await see(user, "“Pet Feliz” salvo.")
    with session_scope() as session:
        assert session.get(Lead, lead_id).neighborhood == "Centro"  # type: ignore[union-attr]


async def test_delete_lead_with_confirmation(app_db: None, user: User) -> None:
    await user.open("/leads")
    lead_id = _create(company_name="Para Excluir")
    await user.open("/leads")
    user.find(ui.table).trigger("remove", lead_id)
    await see(user, "Excluir lead(s)?")
    user.find(kind=ui.button, content="Excluir").click()
    await see(user, "1 lead(s) excluído(s).")
    with session_scope() as session:
        assert session.get(Lead, lead_id) is None


async def test_export_csv_downloads_filtered_leads(app_db: None, user: User) -> None:
    await user.open("/leads")
    _create(company_name="Salão Bella", city="São Paulo")
    await user.open("/leads")
    user.find(kind=ui.button, content="CSV").click()
    await see(user, "1 lead(s) exportado(s).")
    response = await user.download.next()
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Nome;Contato;Nicho")
    assert "Salão Bella" in text
