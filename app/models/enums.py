"""Enums de domínio com rótulos em português para a interface."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def str_enum(enum_cls: type[StrEnum]) -> SAEnum:
    """Coluna Enum armazenada como VARCHAR com os *values* (não os nomes)."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class LeadStatus(StrEnum):
    """Etapas do funil de prospecção."""

    NEW = "new"
    CONTACTED = "contacted"
    REPLIED = "replied"
    PREVIEW_ACCEPTED = "preview_accepted"
    PREVIEW_SENT = "preview_sent"
    PROPOSAL = "proposal"
    WON = "won"
    LOST = "lost"

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]

    @property
    def is_closed(self) -> bool:
        """Etapa final (fechado ou perdido)."""
        return self in (LeadStatus.WON, LeadStatus.LOST)


_STATUS_LABELS = {
    LeadStatus.NEW: "Novo",
    LeadStatus.CONTACTED: "Abordado",
    LeadStatus.REPLIED: "Respondeu",
    LeadStatus.PREVIEW_ACCEPTED: "Aceitou prévia",
    LeadStatus.PREVIEW_SENT: "Prévia enviada",
    LeadStatus.PROPOSAL: "Proposta",
    LeadStatus.WON: "Fechado",
    LeadStatus.LOST: "Perdido",
}

#: Ordem linear do funil (``LOST`` fica de fora: pode ocorrer a partir de qualquer etapa).
FUNNEL_ORDER: tuple[LeadStatus, ...] = (
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.REPLIED,
    LeadStatus.PREVIEW_ACCEPTED,
    LeadStatus.PREVIEW_SENT,
    LeadStatus.PROPOSAL,
    LeadStatus.WON,
)

#: Colunas do Kanban: o funil + Perdido no fim.
BOARD_ORDER: tuple[LeadStatus, ...] = (*FUNNEL_ORDER, LeadStatus.LOST)

#: Etapas em que estamos aguardando resposta do lead (elegíveis a follow-up).
AWAITING_REPLY: frozenset[LeadStatus] = frozenset(
    {LeadStatus.CONTACTED, LeadStatus.PREVIEW_SENT, LeadStatus.PROPOSAL}
)


class WebsiteStatus(StrEnum):
    """Situação do site atual do negócio."""

    NONE = "none"
    BAD = "bad"
    YES = "yes"

    @property
    def label(self) -> str:
        return {"none": "Sem site", "bad": "Site ruim", "yes": "Tem site"}[self.value]


class InteractionType(StrEnum):
    """Tipos de interação registrados na timeline do lead."""

    FIRST_CONTACT = "first_contact"
    FOLLOW_UP = "follow_up"
    PREVIEW_SENT = "preview_sent"
    PROPOSAL = "proposal"
    REPLY = "reply"
    NOTE = "note"

    @property
    def label(self) -> str:
        return {
            "first_contact": "Primeiro contato",
            "follow_up": "Follow-up",
            "preview_sent": "Prévia enviada",
            "proposal": "Proposta",
            "reply": "Resposta do lead",
            "note": "Anotação",
        }[self.value]

    @property
    def is_outbound(self) -> bool:
        """Mensagem enviada por mim (conta como abordagem/contato)."""
        return self in (
            InteractionType.FIRST_CONTACT,
            InteractionType.FOLLOW_UP,
            InteractionType.PREVIEW_SENT,
            InteractionType.PROPOSAL,
        )


class SalePlan(StrEnum):
    """Planos de venda."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"

    @property
    def label(self) -> str:
        return {"one_time": "À vista", "recurring": "Mensal"}[self.value]
