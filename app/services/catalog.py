"""Cadastros da tela de Configurações: nichos, templates e metas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import InteractionType, Lead, MessageTemplate, Niche
from app.repositories import SettingRepository
from app.services.templates import unknown_variables
from app.services.text import simplify

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CatalogError(ValueError):
    """Erro de validação com mensagens por campo."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("; ".join(errors.values()))
        self.errors = errors


@dataclass
class NicheForm:
    name: str = ""
    weekday: int | None = None
    color: str = "#6366F1"
    keywords: list[str] = field(default_factory=list)
    active: bool = True


@dataclass
class TemplateForm:
    name: str = ""
    stage: InteractionType = InteractionType.FIRST_CONTACT
    body: str = ""
    active: bool = True
    is_default: bool = False


def parse_keywords(text: str) -> list[str]:
    """``"barbearia, Barber; barbeiro"`` → ``["barbearia", "barber", "barbeiro"]`` (sem repetir)."""
    seen: dict[str, None] = {}
    for part in re.split(r"[,;\n]", text or ""):
        word = part.strip().lower()
        if word:
            seen.setdefault(word, None)
    return list(seen)


class CatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- nichos ------------------------------------------------------------------------

    def save_niche(self, form: NicheForm, niche_id: int | None = None) -> tuple[Niche, list[str]]:
        """Cria/atualiza um nicho. Retorna avisos (ex.: dia da semana repetido)."""
        name = " ".join((form.name or "").split())
        errors: dict[str, str] = {}
        if not name:
            errors["name"] = "Informe o nome."
        elif any(simplify(n.name) == simplify(name) and n.id != niche_id
                 for n in self.session.scalars(select(Niche))):
            errors["name"] = "Já existe um nicho com esse nome."
        if form.weekday is not None and not 0 <= form.weekday <= 6:
            errors["weekday"] = "Dia inválido."
        if not _HEX.match(form.color or ""):
            errors["color"] = "Use uma cor no formato #RRGGBB."
        if errors:
            raise CatalogError(errors)

        niche = self.session.get(Niche, niche_id) if niche_id else Niche(name=name)
        if niche is None:
            raise CatalogError({"name": "Nicho não encontrado."})
        niche.name, niche.weekday, niche.color = name, form.weekday, form.color.upper()
        niche.keywords, niche.active = list(form.keywords), form.active
        self.session.add(niche)
        self.session.flush()

        warnings = []
        if form.weekday is not None and form.active:
            clash = self.session.scalars(select(Niche.name).where(
                Niche.weekday == form.weekday, Niche.active, Niche.id != niche.id)).all()
            if clash:
                warnings.append(f"Mesmo dia da semana que: {', '.join(clash)}.")
        return niche, warnings

    def delete_niche(self, niche_id: int) -> int:
        """Remove o nicho; os leads dele ficam "sem nicho". Retorna quantos leads foram afetados."""
        affected = self.session.scalar(select(func.count(Lead.id)).where(Lead.niche_id == niche_id)) or 0
        self.session.execute(update(Lead).where(Lead.niche_id == niche_id).values(niche_id=None))
        niche = self.session.get(Niche, niche_id)
        if niche is not None:
            self.session.delete(niche)
        self.session.flush()
        return affected

    # -- templates ---------------------------------------------------------------------

    def save_template(self, form: TemplateForm, template_id: int | None = None) -> MessageTemplate:
        errors: dict[str, str] = {}
        name, body = (form.name or "").strip(), (form.body or "").strip()
        if not name:
            errors["name"] = "Informe o nome."
        if not body:
            errors["body"] = "Escreva a mensagem."
        elif unknown := unknown_variables(body):
            errors["body"] = "Variáveis desconhecidas: " + ", ".join("{" + u + "}" for u in unknown)
        if errors:
            raise CatalogError(errors)

        template = (self.session.get(MessageTemplate, template_id) if template_id
                    else MessageTemplate(name=name, stage=form.stage, body=body))
        if template is None:
            raise CatalogError({"name": "Template não encontrado."})
        template.name, template.stage, template.body = name, form.stage, body
        template.active, template.is_default = form.active, form.is_default
        self.session.add(template)
        self.session.flush()
        if form.is_default:  # só um padrão por etapa
            self.session.execute(
                update(MessageTemplate)
                .where(MessageTemplate.stage == form.stage, MessageTemplate.id != template.id)
                .values(is_default=False)
            )
        return template

    def delete_template(self, template_id: int) -> None:
        template = self.session.get(MessageTemplate, template_id)
        if template is not None:
            self.session.delete(template)
            self.session.flush()

    # -- metas -------------------------------------------------------------------------

    LIMITS: dict[str, tuple[int, int]] = {
        "daily_goal": (1, 200),
        "followup_days": (1, 30),
        "max_followups": (0, 10),
        "score_weight_rating": (0, 100),
        "score_weight_reviews": (0, 100),
        "score_weight_website": (0, 100),
        "score_reviews_cap": (10, 100000),
    }

    def save_settings(self, values: dict[str, Any]) -> bool:
        """Valida e grava as metas. Retorna ``True`` se algum peso do score mudou."""
        errors: dict[str, str] = {}
        clean: dict[str, Any] = {}
        for key, (low, high) in self.LIMITS.items():
            try:
                number = int(float(values[key]))
            except (KeyError, TypeError, ValueError):
                errors[key] = "Informe um número."
                continue
            if not low <= number <= high:
                errors[key] = f"Entre {low} e {high}."
            clean[key] = number
        service = str(values.get("service_name") or "").strip()
        if not service:
            errors["service_name"] = "Informe o serviço."
        clean["service_name"] = service
        if not errors and not clean["score_weight_rating"] + clean["score_weight_reviews"] + clean["score_weight_website"]:
            errors["score_weight_rating"] = "Algum peso precisa ser maior que zero."
        if errors:
            raise CatalogError(errors)

        repo = SettingRepository(self.session)
        old = repo.all()
        for key, value in clean.items():
            repo.set(key, value)
        self.session.flush()
        return any(old.get(k) != clean[k] for k in clean if k.startswith("score_"))
