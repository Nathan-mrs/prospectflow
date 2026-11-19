"""Funil: mudança de status, registro de interações ("enviei") e fechamento.

Regras principais:

* Toda mudança de status gera um :class:`StatusHistory`.
* Registrar uma mensagem enviada avança o status **só para frente**
  (ex.: "primeiro contato" leva ``Novo → Abordado``; nunca rebaixa).
* Mensagem enviada em etapa que aguarda resposta agenda o próximo follow-up
  (``followup_days`` depois); resposta do lead cancela o agendamento.
* Fechar (``WON``) cria a venda; sair de ``WON`` remove a venda.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.clock import now
from app.models import (
    AWAITING_REPLY,
    FUNNEL_ORDER,
    Interaction,
    InteractionType,
    Lead,
    LeadStatus,
    Sale,
    SalePlan,
    StatusHistory,
)
from app.repositories import SettingRepository

#: Para qual status cada mensagem enviada leva o lead.
STATUS_AFTER: dict[InteractionType, LeadStatus] = {
    InteractionType.FIRST_CONTACT: LeadStatus.CONTACTED,
    InteractionType.PREVIEW_SENT: LeadStatus.PREVIEW_SENT,
    InteractionType.PROPOSAL: LeadStatus.PROPOSAL,
    InteractionType.REPLY: LeadStatus.REPLIED,
}


class FunnelError(ValueError):
    """Operação inválida no funil (mensagem em português)."""


def _rank(status: LeadStatus) -> int:
    return FUNNEL_ORDER.index(status) if status in FUNNEL_ORDER else -1


class FunnelService:
    """Casos de uso do funil sobre uma sessão (sem commit)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        settings = SettingRepository(session).all()
        self.followup_days = int(settings["followup_days"])

    # -- status ----------------------------------------------------------------------

    def move(
        self,
        lead: Lead,
        to_status: LeadStatus,
        *,
        at: datetime | None = None,
        plan: SalePlan | None = None,
        lost_reason: str | None = None,
    ) -> bool:
        """Move o lead para ``to_status``. Retorna ``False`` se já estava lá.

        Raises:
            FunnelError: fechar sem informar o plano.
        """
        if lead.status is to_status:
            return False
        if to_status is LeadStatus.WON and plan is None and lead.sale is None:
            raise FunnelError("Informe o plano da venda para marcar como Fechado.")
        moment = at or now()

        if lead.status is LeadStatus.WON and lead.sale is not None:
            self.session.delete(lead.sale)
            lead.sale = None

        lead.status_history.append(
            StatusHistory(from_status=lead.status, to_status=to_status, changed_at=moment)
        )
        lead.status = to_status
        lead.status_changed_at = moment

        if to_status is LeadStatus.WON and plan is not None:
            lead.sale = Sale.for_plan(plan, closed_at=moment)
        if to_status is LeadStatus.LOST:
            lead.lost_reason = (lost_reason or "").strip() or None
            if lead.lost_reason:
                lead.interactions.append(
                    Interaction(type=InteractionType.NOTE, occurred_at=moment,
                                note=f"Perdido: {lead.lost_reason}")
                )
        else:
            lead.lost_reason = None

        # follow-up só existe em etapas que aguardam resposta
        if to_status in AWAITING_REPLY and lead.last_contact_at:
            lead.next_followup_at = max(lead.last_contact_at, moment) + timedelta(days=self.followup_days)
            lead.followup_count = 0
        else:
            lead.next_followup_at = None
        self.session.flush()
        return True

    # -- interações ------------------------------------------------------------------

    def register(
        self,
        lead: Lead,
        kind: InteractionType,
        *,
        message: str | None = None,
        note: str | None = None,
        template_id: int | None = None,
        at: datetime | None = None,
    ) -> Interaction:
        """Registra uma interação e aplica a automação correspondente.

        * ``FIRST_CONTACT``/``PREVIEW_SENT``/``PROPOSAL``: avança o status (só para frente).
        * ``FOLLOW_UP``: soma 1 ao contador de follow-ups.
        * ``REPLY``: lead abordado vira "Respondeu"; cancela o follow-up agendado.
        * Mensagens enviadas atualizam ``last_contact_at`` e reagendam o follow-up.
        """
        if lead.status.is_closed and kind is not InteractionType.NOTE:
            raise FunnelError(f"O lead está “{lead.status.label}”. Reabra-o no funil antes.")
        moment = at or now()
        interaction = Interaction(
            type=kind, occurred_at=moment, message=message, note=note, template_id=template_id
        )
        lead.interactions.append(interaction)

        target = STATUS_AFTER.get(kind)
        if kind is InteractionType.REPLY and lead.status is not LeadStatus.CONTACTED:
            target = None  # resposta em etapas avançadas não muda o status
        if target is not None and _rank(target) > _rank(lead.status):
            self.move(lead, target, at=moment)

        if kind is InteractionType.FOLLOW_UP:
            lead.followup_count += 1
        if kind.is_outbound:
            lead.last_contact_at = moment
            lead.next_followup_at = (
                moment + timedelta(days=self.followup_days) if lead.status in AWAITING_REPLY else None
            )
        if kind is InteractionType.REPLY:
            lead.next_followup_at = None
        self.session.flush()
        return interaction
