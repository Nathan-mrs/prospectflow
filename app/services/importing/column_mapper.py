"""Detecção automática do mapeamento coluna da planilha → campo do lead.

Estratégia (em ordem de confiança):

1. **Nome exato** — cabeçalho simplificado igual a um apelido (``"fone"`` → telefone).
2. **Contém apelido** — todas as palavras do apelido aparecem no cabeçalho
   (``"Link do Google Maps"`` contém ``"google maps"``). Apelidos mais longos vencem.
3. **Conteúdo** — para colunas sem nome reconhecível, olha os valores
   (ex.: coluna onde a maioria parece telefone).

Cada campo é atribuído a no máximo uma coluna e vice-versa.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

from app.services.text import simplify


@dataclass(frozen=True, slots=True)
class TargetField:
    """Campo do lead que pode receber uma coluna."""

    key: str
    label: str
    aliases: tuple[str, ...]
    required: bool = False


TARGET_FIELDS: tuple[TargetField, ...] = (
    TargetField(
        "company_name", "Empresa",
        ("empresa", "nome da empresa", "nome empresa", "nome", "estabelecimento", "negocio",
         "razao social", "nome fantasia", "loja", "title", "name", "business", "titulo"),
        required=True,
    ),
    TargetField(
        "contact_name", "Contato",
        ("contato", "nome do contato", "responsavel", "dono", "proprietario", "nome contato"),
    ),
    TargetField(
        "phone", "Telefone",
        ("telefone", "fone", "whatsapp", "whats", "zap", "celular", "tel", "phone",
         "numero", "telefone whatsapp", "contato telefone"),
    ),
    TargetField(
        "category", "Categoria",
        ("categoria", "segmento", "ramo", "tipo", "atividade", "category", "categorias"),
    ),
    TargetField("niche", "Nicho", ("nicho", "niche")),
    TargetField(
        "google_rating", "Nota Google",
        ("nota", "nota google", "avaliacao", "rating", "estrelas", "media", "nota media"),
    ),
    TargetField(
        "review_count", "Nº avaliações",
        ("avaliacoes", "n avaliacoes", "no avaliacoes", "qtd avaliacoes", "numero de avaliacoes",
         "total avaliacoes", "reviews", "qtd reviews", "review count", "quantidade avaliacoes"),
    ),
    TargetField("website", "Site", ("site", "website", "tem site", "url do site", "pagina", "web")),
    TargetField("instagram", "Instagram", ("instagram", "insta", "ig")),
    TargetField("neighborhood", "Bairro", ("bairro", "regiao", "neighborhood")),
    TargetField("city", "Cidade", ("cidade", "municipio", "city", "localidade")),
    TargetField(
        "maps_url", "Link Maps",
        ("link maps", "google maps", "maps", "link", "url", "link do maps", "url maps"),
    ),
    TargetField(
        "notes", "Observações",
        ("observacoes", "observacao", "obs", "notas", "anotacoes", "comentarios", "notes"),
    ),
)

FIELDS_BY_KEY: dict[str, TargetField] = {f.key: f for f in TARGET_FIELDS}

_PHONE_LIKE = re.compile(r"^\+?[\d\s().-]{8,20}$")


@dataclass(frozen=True, slots=True)
class MappingSuggestion:
    """Sugestão para uma coluna da planilha."""

    column: str
    field: str | None  # None = ignorar coluna
    confidence: float  # 0..1
    reason: str


def _match_by_name(header: str) -> list[tuple[float, str, str]]:
    """Candidatos (confiança, campo, motivo) para um cabeçalho."""
    simple = simplify(header)
    if not simple:
        return []
    tokens = set(simple.split())
    candidates: list[tuple[float, str, str]] = []
    for target in TARGET_FIELDS:
        for alias in target.aliases:
            if simple == alias:
                candidates.append((1.0, target.key, "nome exato"))
            elif set(alias.split()) <= tokens:
                # mais palavras do apelido = mais específico (até 0.9)
                score = 0.6 + min(len(alias.split()), 3) * 0.1
                candidates.append((score, target.key, f"contém “{alias}”"))
    return candidates


def _match_by_values(values: Iterable[object]) -> tuple[float, str, str] | None:
    sample = [str(v).strip() for v in values if str(v).strip()][:50]
    if len(sample) < 3:
        return None

    def ratio(predicate: Callable[[str], bool]) -> float:
        return sum(1 for v in sample if predicate(v)) / len(sample)

    if ratio(lambda v: bool(_PHONE_LIKE.match(v)) and 8 <= len(re.sub(r"\D", "", v)) <= 13) >= 0.7:
        return (0.5, "phone", "valores parecem telefones")
    if ratio(lambda v: "maps" in v.lower() or "goo.gl" in v.lower()) >= 0.6:
        return (0.5, "maps_url", "valores parecem links do Maps")
    if ratio(lambda v: v.startswith("@") or "instagram.com" in v.lower()) >= 0.6:
        return (0.5, "instagram", "valores parecem perfis do Instagram")
    return None


def suggest_mapping(
    columns: Sequence[str], sample: pd.DataFrame | None = None
) -> list[MappingSuggestion]:
    """Sugere um campo para cada coluna (na ordem original das colunas)."""
    candidates: list[tuple[float, int, str, str]] = []  # (confiança, idx coluna, campo, motivo)
    for idx, column in enumerate(columns):
        for score, field_key, reason in _match_by_name(column):
            candidates.append((score, idx, field_key, reason))

    assigned_fields: set[str] = set()
    result: dict[int, MappingSuggestion] = {}
    # maior confiança primeiro; em empate, coluna mais à esquerda
    for score, idx, field_key, reason in sorted(candidates, key=lambda c: (-c[0], c[1])):
        if idx in result or field_key in assigned_fields:
            continue
        result[idx] = MappingSuggestion(columns[idx], field_key, score, reason)
        assigned_fields.add(field_key)

    if sample is not None:
        for idx, column in enumerate(columns):
            if idx in result or column not in sample.columns:
                continue
            guess = _match_by_values(sample[column].tolist())
            if guess and guess[1] not in assigned_fields:
                result[idx] = MappingSuggestion(column, guess[1], guess[0], guess[2])
                assigned_fields.add(guess[1])

    return [
        result.get(idx, MappingSuggestion(column, None, 0.0, "não reconhecida"))
        for idx, column in enumerate(columns)
    ]


def mapping_from_suggestions(suggestions: Iterable[MappingSuggestion]) -> dict[str, str]:
    """Converte sugestões em ``{campo: coluna}`` (apenas colunas mapeadas)."""
    return {s.field: s.column for s in suggestions if s.field}


def validate_mapping(mapping: dict[str, str]) -> list[str]:
    """Erros que impedem a importação (campos obrigatórios / colunas repetidas)."""
    errors = [
        f"Mapeie a coluna de “{f.label}”."
        for f in TARGET_FIELDS
        if f.required and not mapping.get(f.key)
    ]
    columns = [c for c in mapping.values() if c]
    repeated = {c for c in columns if columns.count(c) > 1}
    errors.extend(f"A coluna “{c}” foi usada em mais de um campo." for c in sorted(repeated))
    return errors
