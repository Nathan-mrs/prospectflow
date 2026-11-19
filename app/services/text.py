"""Utilitários de texto compartilhados (normalização para comparação)."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    """Remove acentos: ``"Salão"`` → ``"Salao"``."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def simplify(text: str | None) -> str:
    """Minúsculas, sem acento, só letras/números separados por um espaço.

    ``"  Nº de Avaliações! "`` → ``"n de avaliacoes"``.
    """
    if not text:
        return ""
    lowered = strip_accents(str(text)).lower().replace("º", "o").replace("ª", "a")
    return _NON_ALNUM.sub(" ", lowered).strip()


def compact_key(text: str | None) -> str:
    """Chave de comparação sem espaços: ``"Barbearia do Zé"`` → ``"barbeariadoze"``."""
    return simplify(text).replace(" ", "")
