"""Acesso às configurações chave/valor."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DEFAULT_SETTINGS, AppSetting


class SettingRepository:
    """Lê e grava configurações, caindo nos padrões quando a chave não existe."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def all(self) -> dict[str, Any]:
        """Todas as configurações (padrões sobrescritos pelos valores salvos)."""
        values = dict(DEFAULT_SETTINGS)
        values.update({s.key: s.value for s in self.session.scalars(select(AppSetting))})
        return values

    def get(self, key: str, default: Any = None) -> Any:
        setting = self.session.get(AppSetting, key)
        if setting is not None:
            return setting.value
        return DEFAULT_SETTINGS.get(key, default)

    def set(self, key: str, value: Any) -> None:
        setting = self.session.get(AppSetting, key)
        if setting is None:
            self.session.add(AppSetting(key=key, value=value))
        else:
            setting.value = value
