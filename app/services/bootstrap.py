"""Dados padrão criados na primeira execução: configurações, nichos e templates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DEFAULT_SETTINGS, AppSetting, InteractionType, MessageTemplate, Niche

DEFAULT_NICHES: list[dict[str, Any]] = [
    {
        "name": "Barbearias",
        "weekday": 0,
        "color": "#6366F1",
        "keywords": ["barbearia", "barber", "barbeiro", "barbershop"],
    },
    {
        "name": "Salões de Beleza",
        "weekday": 1,
        "color": "#EC4899",
        "keywords": ["salão", "salao", "cabeleireir", "beleza", "manicure", "esmalteria", "nail"],
    },
    {
        "name": "Pet Shops",
        "weekday": 2,
        "color": "#F59E0B",
        "keywords": ["pet", "veterin", "banho e tosa", "tosa", "aquário", "aquario"],
    },
    {
        "name": "Oficinas Mecânicas",
        "weekday": 3,
        "color": "#64748B",
        "keywords": ["oficina", "mecânic", "mecanic", "auto center", "funilaria", "borracharia"],
    },
    {
        "name": "Restaurantes",
        "weekday": 4,
        "color": "#EF4444",
        "keywords": [
            "restaurante", "lanchonete", "pizzaria", "hamburgueria",
            "marmitaria", "churrascaria", "açaí", "acai",
        ],
    },
    {
        "name": "Clínicas de Estética",
        "weekday": 5,
        "color": "#8B5CF6",
        "keywords": ["estética", "estetica", "depilação", "depilacao", "sobrancelha", "spa"],
    },
    {
        "name": "Academias",
        "weekday": 6,
        "color": "#10B981",
        "keywords": ["academia", "crossfit", "pilates", "fitness", "musculação", "luta"],
    },
]

DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Primeiro contato",
        "stage": InteractionType.FIRST_CONTACT,
        "body": (
            "Oi, {nome}! Tudo bem? Encontrei a {empresa} no Google Maps e vi que vocês têm "
            "ótimas avaliações aqui em {cidade}, mas ainda não têm um site. Trabalho com "
            "{servico} para negócios locais e montei uma ideia pra vocês. Posso te mandar "
            "uma prévia gratuita, sem compromisso?"
        ),
    },
    {
        "name": "Follow-up",
        "stage": InteractionType.FOLLOW_UP,
        "body": (
            "Oi, {nome}! Passando só pra saber se você viu minha mensagem sobre o site da "
            "{empresa}. A prévia é gratuita e fica pronta rapidinho. Quer dar uma olhada?"
        ),
    },
    {
        "name": "Envio da prévia",
        "stage": InteractionType.PREVIEW_SENT,
        "body": (
            "{nome}, aqui está a prévia do site da {empresa}: [link]\n"
            "Me conta o que achou! Qualquer ajuste eu faço."
        ),
    },
    {
        "name": "Proposta",
        "stage": InteractionType.PROPOSAL,
        "body": (
            "{nome}, que bom que gostou! Para colocar o site da {empresa} no ar:\n"
            "• R$ 497 à vista, ou\n"
            "• R$ 297 + R$ 49/mês (hospedagem, domínio e manutenção inclusos).\n"
            "Qual opção fica melhor pra você?"
        ),
    },
]


def ensure_defaults(session: Session) -> None:
    """Cria configurações, nichos e templates padrão que ainda não existirem (idempotente)."""
    existing_keys = set(session.scalars(select(AppSetting.key)))
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing_keys:
            session.add(AppSetting(key=key, value=value))

    if session.scalar(select(Niche.id).limit(1)) is None:
        session.add_all(Niche(**data) for data in DEFAULT_NICHES)

    if session.scalar(select(MessageTemplate.id).limit(1)) is None:
        session.add_all(MessageTemplate(**data, is_default=True) for data in DEFAULT_TEMPLATES)

    session.flush()
