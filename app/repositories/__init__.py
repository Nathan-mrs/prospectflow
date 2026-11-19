"""Camada de acesso a dados."""

from app.repositories.lead_repo import NO_NICHE, LeadQuery, LeadRepository
from app.repositories.niche_repo import NicheRepository
from app.repositories.setting_repo import SettingRepository

__all__ = ["NO_NICHE", "LeadQuery", "LeadRepository", "NicheRepository", "SettingRepository"]
