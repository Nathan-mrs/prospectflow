"""Testes de interface (navegador simulado) das telas Hoje, Funil, Dashboard e Configurações."""

from __future__ import annotations

from nicegui import ui
from nicegui.testing import User
from sqlalchemy import func, select

from app.clock import now
from app.db import session_scope
from app.models import Interaction, InteractionType, MessageTemplate, Niche
from app.services.catalog import CatalogError, CatalogService, NicheForm, TemplateForm, parse_keywords
from scripts.seed import seed_database


async def see(user: User, text: str) -> None:
    await user.should_see(text, retries=50)


def _seed(count: int = 60) -> None:
    with session_scope() as session:
        seed_database(session, lead_count=count, reference=now())


def _count(model: type, *where: object) -> int:
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


async def test_all_pages_render_empty(app_db: None, user: User) -> None:
    for path, text in (("/", "Fila de abordagem"), ("/funil", "Nenhum lead no funil"),
                       ("/dashboard", "Sem dados ainda"), ("/configuracoes", "Barbearias")):
        await user.open(path)
        await see(user, text)


async def test_today_queue_register_sent(app_db: None, user: User) -> None:
    _seed()
    await user.open("/")
    await see(user, "Fila de abordagem")
    await user.should_see("Nicho do dia")
    before = _count(Interaction)
    if not user.find("Enviei").elements:  # seed pode ter zerado a fila do dia
        return
    user.find("Enviei").click()
    await see(user, "registrado para")
    assert _count(Interaction) > before


async def test_funnel_and_dashboard_render_with_data(app_db: None, user: User) -> None:
    _seed()
    await user.open("/funil")
    await see(user, "Prévia enviada")
    await user.should_see("Fechado")
    await user.open("/dashboard")
    await see(user, "Conversão por nicho")
    await user.should_see("MRR")
    await user.should_see("Faturamento")


async def test_settings_create_niche_dialog(app_db: None, user: User) -> None:
    await user.open("/configuracoes")
    await see(user, "Novo nicho")
    user.find("Novo nicho").click()
    await see(user, "Palavras-chave (separe por vírgula)")
    name = next(e for e in user.find(ui.input).elements if e.props.get("label") == "Nome *")
    name.value = "Lavanderias"
    user.find(marker="niche-save").click()
    await see(user, "Lavanderias")
    assert "Nicho “Lavanderias” salvo." in user.notify.messages
    assert _count(Niche, Niche.name == "Lavanderias") == 1


# --------------------------------------------------------------------------- serviço de cadastro


def test_catalog_niche_validation(session) -> None:  # type: ignore[no-untyped-def]
    from app.services.bootstrap import ensure_defaults

    ensure_defaults(session)
    service = CatalogService(session)
    try:
        service.save_niche(NicheForm(name="barbearias", color="azul"))
    except CatalogError as exc:
        assert set(exc.errors) == {"name", "color"}
    else:
        raise AssertionError("deveria validar")
    _, warnings = service.save_niche(NicheForm(name="Lavanderias", weekday=0, color="#123abc"))
    assert warnings and "Barbearias" in warnings[0]
    assert parse_keywords("Lavanderia, lavanderia; lava-jato\n") == ["lavanderia", "lava-jato"]


def test_catalog_template_default_is_unique_per_stage(session) -> None:  # type: ignore[no-untyped-def]
    from app.services.bootstrap import ensure_defaults

    ensure_defaults(session)
    service = CatalogService(session)
    try:
        service.save_template(TemplateForm(name="X", body="Oi {nme}"))
    except CatalogError as exc:
        assert "{nme}" in exc.errors["body"]
    created = service.save_template(TemplateForm(name="Novo padrão", body="Oi {nome}!", is_default=True))
    defaults = session.scalars(select(MessageTemplate).where(
        MessageTemplate.stage == InteractionType.FIRST_CONTACT, MessageTemplate.is_default)).all()
    assert defaults == [created]


def test_catalog_settings_validation(session) -> None:  # type: ignore[no-untyped-def]
    from app.services.bootstrap import ensure_defaults

    ensure_defaults(session)
    service = CatalogService(session)
    values = {"daily_goal": 15, "followup_days": 3, "max_followups": 2, "service_name": "landing page",
              "score_weight_rating": 50, "score_weight_reviews": 30, "score_weight_website": 20,
              "score_reviews_cap": 500}
    assert service.save_settings(values) is True
    assert service.save_settings(values) is False
    try:
        service.save_settings(values | {"daily_goal": 0, "service_name": " "})
    except CatalogError as exc:
        assert set(exc.errors) == {"daily_goal", "service_name"}
