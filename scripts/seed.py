"""Popula o banco com dados fictícios para demonstração.

Uso::

    python -m scripts.seed            # adiciona dados (cria padrões se faltarem)
    python -m scripts.seed --reset    # apaga tudo e recria do zero
    python -m scripts.seed --leads 300 --seed 7
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import now
from app.db import create_db_engine, drop_db, init_db
from app.models import (
    AWAITING_REPLY,
    DEFAULT_SETTINGS,
    FUNNEL_ORDER,
    Interaction,
    InteractionType,
    Lead,
    LeadStatus,
    MessageTemplate,
    Niche,
    Payment,
    Sale,
    SalePlan,
    StatusHistory,
    WebsiteStatus,
)
from app.services.bootstrap import ensure_defaults
from app.services.score import calculate_priority_score

# --------------------------------------------------------------------------- dados base

BUSINESS_NAMES: dict[str, tuple[list[str], list[str]]] = {
    "Barbearias": (
        ["Barbearia", "Barber Shop", "Barbearia do", "Studio Barber", "Barbearia Dom"],
        ["Zé", "Navalha de Ouro", "Corte Fino", "Bigode", "Vintage", "Raiz", "King", "Estilo"],
    ),
    "Salões de Beleza": (
        ["Salão", "Espaço", "Studio", "Esmalteria", "Instituto de Beleza"],
        ["Bella", "Divas", "Glamour", "Lírio", "Encanto", "Mulher Bonita", "Charme", "Aurora"],
    ),
    "Pet Shops": (
        ["Pet Shop", "Banho e Tosa", "Clínica Veterinária", "Pet Center", "Casa do"],
        ["Amigo Fiel", "Patinhas", "Au Au", "Bichinho", "Focinho", "Pet Feliz", "Mascote"],
    ),
    "Oficinas Mecânicas": (
        ["Auto Center", "Oficina", "Mecânica", "Funilaria", "Borracharia"],
        ["do Carlão", "São Jorge", "Turbo", "Pit Stop", "Motor Forte", "Garagem 85", "Rota"],
    ),
    "Restaurantes": (
        ["Restaurante", "Pizzaria", "Hamburgueria", "Lanchonete", "Marmitaria", "Açaí"],
        ["da Vó", "Sabor Caseiro", "Bella Napoli", "Brasa", "Tempero Mineiro", "Ponto Certo"],
    ),
    "Clínicas de Estética": (
        ["Clínica", "Espaço", "Studio", "Estética", "Spa"],
        ["Renova", "Pele de Seda", "Bem Estar", "Essência", "Harmonia", "Lumière", "Vitta"],
    ),
    "Academias": (
        ["Academia", "Studio", "CrossFit", "Pilates", "Centro de Treinamento"],
        ["Força Total", "Corpo em Ação", "Iron", "Movimento", "Atitude", "Evolution", "Prime"],
    ),
}

CATEGORY_BY_NICHE = {
    "Barbearias": "Barbearia",
    "Salões de Beleza": "Salão de beleza",
    "Pet Shops": "Pet shop",
    "Oficinas Mecânicas": "Oficina mecânica",
    "Restaurantes": "Restaurante",
    "Clínicas de Estética": "Clínica de estética",
    "Academias": "Academia",
}

FIRST_NAMES = [
    "Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela",
    "João", "Karina", "Lucas", "Mariana", "Natália", "Otávio", "Paula", "Rafael", "Sabrina",
    "Thiago", "Vanessa", "Wesley", "Juliana", "Marcos", "Patrícia", "Rodrigo", "Camila",
]

LOCATIONS: list[tuple[str, list[str]]] = [
    ("São Paulo", ["Centro", "Moema", "Tatuapé", "Pinheiros", "Santana", "Vila Mariana", "Lapa"]),
    ("Guarulhos", ["Centro", "Vila Galvão", "Macedo", "Bonsucesso"]),
    ("Osasco", ["Centro", "Presidente Altino", "Km 18", "Jardim Bussocaba"]),
    ("Santo André", ["Centro", "Vila Assunção", "Jardim", "Campestre"]),
]

FINAL_STATUS_WEIGHTS: dict[LeadStatus, float] = {
    LeadStatus.NEW: 45,
    LeadStatus.CONTACTED: 18,
    LeadStatus.REPLIED: 7,
    LeadStatus.PREVIEW_ACCEPTED: 4,
    LeadStatus.PREVIEW_SENT: 5,
    LeadStatus.PROPOSAL: 4,
    LeadStatus.WON: 6,
    LeadStatus.LOST: 11,
}

LOST_REASONS = [
    "Sem resposta após 3 follow-ups",
    "Já tem alguém fazendo o site",
    "Achou caro",
    "Não tem interesse no momento",
]

REPLY_NOTES = {
    LeadStatus.REPLIED: "Respondeu perguntando como funciona.",
    LeadStatus.PREVIEW_ACCEPTED: "Aceitou receber a prévia.",
    LeadStatus.WON: "Fechou! Pediu para começar esta semana.",
}

OUTBOUND_BY_STATUS = {
    LeadStatus.CONTACTED: InteractionType.FIRST_CONTACT,
    LeadStatus.PREVIEW_SENT: InteractionType.PREVIEW_SENT,
    LeadStatus.PROPOSAL: InteractionType.PROPOSAL,
}


# --------------------------------------------------------------------------- geração


def _render(body: str, lead: Lead, service: str) -> str:
    """Substituição simples de variáveis (o serviço completo vem na etapa de templates)."""
    values = {
        "nome": lead.contact_name or lead.company_name,
        "empresa": lead.company_name,
        "servico": service,
        "cidade": lead.city or "",
    }
    return body.format_map(values)


def _month_iter(start: date, end: date) -> list[date]:
    months: list[date] = []
    current = date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return months


class FakeDataGenerator:
    """Gera leads fictícios com histórico coerente com o funil."""

    def __init__(self, session: Session, rng: random.Random, reference: datetime) -> None:
        self.session = session
        self.rng = rng
        self.ref = reference
        self.service = str(DEFAULT_SETTINGS["service_name"])
        self.followup_days = int(DEFAULT_SETTINGS["followup_days"])
        self.max_followups = int(DEFAULT_SETTINGS["max_followups"])
        self.templates = {
            t.stage: t
            for t in session.scalars(select(MessageTemplate).where(MessageTemplate.is_default))
        }
        self._phones: set[str] = set(session.scalars(select(Lead.phone).where(Lead.phone.isnot(None))))

    # -- atributos ----------------------------------------------------------------------

    def _phone(self) -> str:
        while True:
            phone = f"55119{self.rng.randint(10_000_000, 99_999_999)}"
            if phone not in self._phones:
                self._phones.add(phone)
                return phone

    def _base_lead(self, niche: Niche) -> Lead:
        rng = self.rng
        prefixes, suffixes = BUSINESS_NAMES.get(niche.name, (["Negócio"], ["Local"]))
        company = f"{rng.choice(prefixes)} {rng.choice(suffixes)}"
        city, neighborhoods = rng.choice(LOCATIONS)
        rating = round(min(5.0, max(3.2, rng.gauss(4.5, 0.35))), 1)
        reviews = int(rng.paretovariate(1.3) * 12)
        website = rng.choices(
            [WebsiteStatus.NONE, WebsiteStatus.BAD, WebsiteStatus.YES], weights=[75, 18, 7]
        )[0]
        slug = "".join(ch for ch in company.lower() if ch.isalnum())[:24]
        lead = Lead(
            company_name=company,
            contact_name=rng.choice(FIRST_NAMES) if rng.random() < 0.7 else None,
            niche=niche,
            phone=self._phone(),
            instagram=f"@{slug}" if rng.random() < 0.6 else None,
            category=CATEGORY_BY_NICHE.get(niche.name),
            google_rating=rating,
            review_count=reviews,
            website_status=website,
            neighborhood=rng.choice(neighborhoods),
            city=city,
            maps_url=f"https://maps.google.com/?q={company.replace(' ', '+')}+{city.replace(' ', '+')}",
        )
        lead.priority_score = calculate_priority_score(rating, reviews, website)
        return lead

    # -- histórico ----------------------------------------------------------------------

    def _path_to(self, final: LeadStatus) -> list[LeadStatus]:
        if final is LeadStatus.LOST:
            last_stage = self.rng.choice(FUNNEL_ORDER[1:6])  # CONTACTED..PROPOSAL
            return [*FUNNEL_ORDER[: FUNNEL_ORDER.index(last_stage) + 1], LeadStatus.LOST]
        return list(FUNNEL_ORDER[: FUNNEL_ORDER.index(final) + 1])

    def _days_since_last_event(self, final: LeadStatus) -> float:
        """Quanto tempo atrás aconteceu o último evento do lead (em dias)."""
        rng = self.rng
        if final in AWAITING_REPLY:
            # ~70% ainda dentro do prazo, ~30% com follow-up vencido
            return rng.uniform(0.05, 1.9) if rng.random() < 0.7 else rng.uniform(2.0, 4.5)
        if final in (LeadStatus.REPLIED, LeadStatus.PREVIEW_ACCEPTED):
            return rng.uniform(0.05, 4)  # a bola está comigo: evento recente
        if final is LeadStatus.NEW:
            return rng.uniform(0.2, 30)
        if final is LeadStatus.WON:
            return rng.uniform(1, 95)  # clientes antigos geram mensalidades
        return rng.uniform(0.5, 28)  # fechados / perdidos

    @staticmethod
    def _shift_timeline(lead: Lead, delta: timedelta) -> None:
        lead.created_at += delta
        for item in lead.status_history:
            item.changed_at += delta
        for interaction in lead.interactions:
            interaction.occurred_at += delta

    def _add_interaction(
        self, lead: Lead, kind: InteractionType, at: datetime, note: str | None = None
    ) -> None:
        template = self.templates.get(kind)
        lead.interactions.append(
            Interaction(
                type=kind,
                occurred_at=at,
                template=template if kind.is_outbound else None,
                message=_render(template.body, lead, self.service)
                if template and kind.is_outbound
                else None,
                note=note,
            )
        )

    def build_lead(self, niche: Niche) -> Lead:
        """Cria um lead completo (status, timeline, venda) sem gravar."""
        rng = self.rng
        lead = self._base_lead(niche)
        final = rng.choices(list(FINAL_STATUS_WEIGHTS), weights=list(FINAL_STATUS_WEIGHTS.values()))[0]
        path = self._path_to(final)

        # 1) monta a timeline a partir de uma origem arbitrária...
        created = self.ref
        lead.created_at = created
        lead.status_history.append(StatusHistory(from_status=None, to_status=LeadStatus.NEW, changed_at=created))

        moment = created
        last_outbound: datetime | None = None
        previous = LeadStatus.NEW
        for status in path[1:]:
            if status is LeadStatus.LOST and previous in AWAITING_REPLY and last_outbound:
                # perdido por falta de resposta: os follow-ups vêm antes do "perdido"
                last_outbound = self._add_followups(lead, last_outbound, self.max_followups)
                moment = last_outbound
            moment = moment + timedelta(hours=rng.uniform(6, 72))
            lead.status_history.append(
                StatusHistory(from_status=previous, to_status=status, changed_at=moment)
            )
            if status in OUTBOUND_BY_STATUS:
                self._add_interaction(lead, OUTBOUND_BY_STATUS[status], moment)
                last_outbound = moment
            elif status in REPLY_NOTES:
                self._add_interaction(lead, InteractionType.REPLY, moment, REPLY_NOTES[status])
            elif status is LeadStatus.LOST:
                lead.lost_reason = rng.choice(LOST_REASONS)
                self._add_interaction(lead, InteractionType.NOTE, moment, f"Perdido: {lead.lost_reason}")
            previous = status

        # ainda aguardando resposta: 0 a 2 follow-ups já enviados
        if final in AWAITING_REPLY and last_outbound:
            last_outbound = self._add_followups(lead, last_outbound, rng.randint(0, 2))

        # 2) ...e desloca tudo para que o último evento caia no passado recente desejado
        last_event = max(
            [h.changed_at for h in lead.status_history] + [i.occurred_at for i in lead.interactions]
        )
        target = self.ref - timedelta(days=self._days_since_last_event(final))
        delta = timedelta(seconds=int((target - last_event).total_seconds()))
        self._shift_timeline(lead, delta)
        if last_outbound:
            last_outbound += delta

        lead.status = final
        lead.status_changed_at = lead.status_history[-1].changed_at
        lead.last_contact_at = last_outbound
        if final in AWAITING_REPLY and last_outbound:
            lead.next_followup_at = last_outbound + timedelta(days=self.followup_days)
        lead.updated_at = max(lead.status_changed_at, last_outbound or lead.created_at)

        if final is LeadStatus.WON:
            self._attach_sale(lead)
        return lead

    def _add_followups(self, lead: Lead, since: datetime, wanted: int) -> datetime:
        """Adiciona até ``wanted`` follow-ups espaçados; retorna o último contato."""
        last = since
        for _ in range(wanted):
            last = last + timedelta(days=self.followup_days, hours=self.rng.uniform(0, 8))
            self._add_interaction(lead, InteractionType.FOLLOW_UP, last)
            lead.followup_count += 1
        return last

    def _attach_sale(self, lead: Lead) -> None:
        plan = SalePlan.ONE_TIME if self.rng.random() < 0.55 else SalePlan.RECURRING
        sale = Sale.for_plan(plan, closed_at=lead.status_changed_at)
        lead.sale = sale
        if plan is SalePlan.RECURRING and sale.billing_day:
            closed = sale.closed_at.date()
            for month in _month_iter(closed + timedelta(days=28), self.ref.date()):
                due = month.replace(day=sale.billing_day)
                if due <= closed or due > self.ref.date():
                    continue
                current_month = (month.year, month.month) == (self.ref.year, self.ref.month)
                paid = not current_month or self.rng.random() < 0.5
                sale.payments.append(
                    Payment(
                        reference_month=month.strftime("%Y-%m"),
                        amount=sale.monthly_amount,
                        paid_at=datetime.combine(due, datetime.min.time()).replace(hour=10) if paid else None,
                    )
                )


def seed_database(
    session: Session,
    lead_count: int = 175,
    rng_seed: int = 42,
    reference: datetime | None = None,
) -> dict[str, int]:
    """Cria padrões + ``lead_count`` leads fictícios distribuídos entre os nichos.

    Returns:
        Contagem de registros por tabela após o seed.
    """
    ensure_defaults(session)
    niches = list(session.scalars(select(Niche).where(Niche.active).order_by(Niche.weekday)))
    generator = FakeDataGenerator(session, random.Random(rng_seed), reference or now())
    for i in range(lead_count):
        session.add(generator.build_lead(niches[i % len(niches)]))
    session.flush()

    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
        for model in (Niche, Lead, Interaction, StatusHistory, Sale, Payment, MessageTemplate)
    }


def main() -> None:
    """Ponto de entrada da linha de comando."""
    parser = argparse.ArgumentParser(description="Popula o ProspectFlow com dados fictícios.")
    parser.add_argument("--reset", action="store_true", help="apaga todas as tabelas antes")
    parser.add_argument("--leads", type=int, default=175, help="quantidade de leads (padrão 175)")
    parser.add_argument("--seed", type=int, default=42, help="semente aleatória (padrão 42)")
    args = parser.parse_args()

    engine = create_db_engine()
    if args.reset:
        drop_db(engine)
    init_db(engine)
    with Session(engine) as session:
        counts = seed_database(session, lead_count=args.leads, rng_seed=args.seed)
        session.commit()

    print(f"Banco: {engine.url}")
    for table, total in counts.items():
        print(f"  {table:<18} {total:>5}")


if __name__ == "__main__":
    main()
