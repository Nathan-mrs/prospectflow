"""Normalização dos valores vindos da planilha.

Cada função recebe o valor bruto (string, número ou vazio) e devolve o valor
limpo. Funções que podem falhar devolvem um :class:`Parsed` com avisos/erros
em português, prontos para exibir na pré-visualização.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from app.models.enums import WebsiteStatus
from app.services.text import simplify

T = TypeVar("T")

_SMALL_WORDS = {"de", "da", "do", "das", "dos", "e", "em", "na", "no", "a", "o"}
_STATE_SUFFIX = re.compile(r"\s*(?:[-/,–]\s*|\()\s*[A-Za-z]{2}\)?\s*$")
_FLOAT_INT = re.compile(r"^\d+\.0+$")
_SOCIAL_HOSTS = ("facebook.com", "fb.com", "instagram.com", "linktr.ee", "wa.me", "whatsapp")

#: DDDs válidos no Brasil (Anatel).
VALID_DDDS: frozenset[str] = frozenset(
    "11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 "
    "51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 "
    "91 92 93 94 95 96 97 98 99".split()
)


@dataclass(slots=True)
class Parsed(Generic[T]):
    """Resultado de uma normalização: valor + mensagens."""

    value: T | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- genéricos


def clean_str(raw: Any) -> str:
    """Converte para string sem espaços extras; ``None``/NaN viram ``""``."""
    if raw is None:
        return ""
    if isinstance(raw, float):
        if math.isnan(raw):
            return ""
        if raw.is_integer():
            return str(int(raw))
    text = str(raw).strip()
    if text.lower() in {"nan", "none", "null", "-", "—", "n/a"}:
        return ""
    return re.sub(r"\s+", " ", text)


def smart_title(text: str) -> str:
    """Capitaliza nomes em CAIXA ALTA ou minúsculas, preservando caixa mista.

    ``"BARBEARIA DO ZÉ"`` → ``"Barbearia do Zé"``; ``"BarberKing"`` fica igual.
    """
    if not text:
        return text
    letters = [ch for ch in text if ch.isalpha()]
    if letters and not (all(ch.isupper() for ch in letters) or all(ch.islower() for ch in letters)):
        return text  # já tem formatação intencional
    words = text.lower().split(" ")
    result = [
        word if i > 0 and word in _SMALL_WORDS else word[:1].upper() + word[1:]
        for i, word in enumerate(words)
    ]
    return " ".join(result)


def normalize_name(raw: Any) -> str | None:
    """Nome de empresa/contato limpo e capitalizado."""
    text = clean_str(raw).strip(" .,-")
    return smart_title(text) or None


def normalize_place(raw: Any) -> str | None:
    """Cidade/bairro sem sufixo de UF: ``"SÃO PAULO - SP"`` → ``"São Paulo"``."""
    text = _STATE_SUFFIX.sub("", clean_str(raw)).strip(" .,-")
    return smart_title(text) or None


def normalize_text(raw: Any) -> str | None:
    """Texto livre (observações): só limpa espaços."""
    return clean_str(raw) or None


# --------------------------------------------------------------------------- telefone


def normalize_phone(raw: Any, default_ddd: str = "11") -> Parsed[str]:
    """Normaliza para o formato do WhatsApp ``55DDDNÚMERO``.

    Regras:
      * remove tudo que não é dígito e zeros à esquerda (``0xx11``);
      * 10–11 dígitos → acrescenta ``55``; 8–9 dígitos → acrescenta ``55`` + DDD padrão;
      * **não** inventa o 9º dígito: números de 8 dígitos geram aviso.
    """
    text = clean_str(raw)
    if not text:
        return Parsed(None, warnings=["Sem telefone"])
    if _FLOAT_INT.match(text):
        text = text.split(".")[0]

    digits = re.sub(r"\D", "", text)
    if len(digits) > 11 and digits.startswith("0"):
        digits = digits.lstrip("0")  # prefixo de discagem: "0 11 98765-4321"
    warnings: list[str] = []

    if len(digits) in (12, 13) and digits.startswith("55"):
        number = digits
    elif len(digits) in (10, 11):
        number = "55" + digits
    elif len(digits) in (8, 9):
        number = f"55{default_ddd}{digits}"
        warnings.append(f"Telefone sem DDD — usado {default_ddd}")
    else:
        return Parsed(None, errors=[f"Telefone inválido: {text!r}"])

    ddd, local = number[2:4], number[4:]
    if ddd not in VALID_DDDS:
        return Parsed(None, errors=[f"DDD inválido: {ddd}"])
    if len(local) == 9 and local[0] != "9":
        return Parsed(None, errors=[f"Celular de 9 dígitos deve começar com 9: {text!r}"])
    if len(local) == 8:
        if local[0] in "6789":
            warnings.append("Possível celular sem o 9º dígito")
        else:
            warnings.append("Telefone fixo — pode não ter WhatsApp")
    return Parsed(number, warnings=warnings)


# --------------------------------------------------------------------------- números


def _to_number(text: str) -> float | None:
    match = re.search(r"\d+(?:[.,]\d+)*", text)
    if not match:
        return None
    token = match.group(0)
    if "," in token and "." in token:  # 1.234,5
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:  # 4,8
        token = token.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", token):  # 1.234 (milhar)
        token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


def parse_rating(raw: Any) -> Parsed[float]:
    """Nota do Google entre 0 e 5: aceita ``"4,8"``, ``"4.8 estrelas"``, ``4.8``."""
    text = clean_str(raw)
    if not text:
        return Parsed(None)
    value = _to_number(text)
    if value is None or not 0 <= value <= 5:
        return Parsed(None, warnings=[f"Nota ignorada: {text!r}"])
    return Parsed(round(value, 1))


def parse_review_count(raw: Any) -> Parsed[int]:
    """Quantidade de avaliações: aceita ``"1.234"``, ``"(312)"``, ``"312 avaliações"``."""
    text = clean_str(raw)
    if not text:
        return Parsed(None)
    value = _to_number(text)
    if value is None or value < 0:
        return Parsed(None, warnings=[f"Nº de avaliações ignorado: {text!r}"])
    return Parsed(int(value))


# --------------------------------------------------------------------------- site / redes


def parse_website(raw: Any) -> WebsiteStatus:
    """Interpreta a coluna de site.

    Vazio/"não" → sem site; "ruim"/"desatualizado" → site ruim; link de rede social
    (Instagram, Facebook, Linktree, wa.me) → site ruim; "sim" ou URL → tem site.
    """
    text = clean_str(raw)
    simple = simplify(text)
    if not simple or simple in {"nao", "n", "no", "sem", "sem site", "nenhum", "false", "0"}:
        return WebsiteStatus.NONE
    if any(word in simple for word in ("ruim", "desatualizado", "fraco", "bad", "antigo")):
        return WebsiteStatus.BAD
    lowered = text.lower()
    if any(host in lowered for host in _SOCIAL_HOSTS):
        return WebsiteStatus.BAD
    return WebsiteStatus.YES


def normalize_instagram(raw: Any) -> str | None:
    """``"instagram.com/barber.king/"`` ou ``"barber.king"`` → ``"@barber.king"``."""
    text = clean_str(raw)
    if not text:
        return None
    match = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", text)
    handle = match.group(1) if match else text.lstrip("@").split("?")[0].strip("/ ")
    handle = handle.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", handle):
        return None
    return f"@{handle.lower()}"


def normalize_url(raw: Any) -> str | None:
    """URL com esquema ``https://`` quando faltar."""
    text = clean_str(raw)
    if not text or " " in text:
        return None
    if not re.match(r"^https?://", text, re.IGNORECASE):
        text = "https://" + text
    return text
