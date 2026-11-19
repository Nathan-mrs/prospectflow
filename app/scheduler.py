"""Tarefas em segundo plano (APScheduler).

Hoje há uma: gerar as mensalidades vencidas dos clientes recorrentes, para que
os lembretes de cobrança apareçam na tela "Hoje" sem ação manual.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.clock import now
from app.db import session_scope
from app.services.billing import ensure_monthly_payments

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def generate_payments() -> int:
    """Cria as mensalidades que já venceram e ainda não existem (idempotente)."""
    with session_scope() as session:
        created = ensure_monthly_payments(session, now())
    if created:
        log.info("%d mensalidade(s) gerada(s)", created)
    return created


def start_scheduler() -> BackgroundScheduler:
    """Roda a geração agora e depois a cada hora."""
    global _scheduler
    if _scheduler is None:
        generate_payments()
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(generate_payments, "interval", hours=1, id="monthly_payments",
                           replace_existing=True, coalesce=True, max_instances=1)
        _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
