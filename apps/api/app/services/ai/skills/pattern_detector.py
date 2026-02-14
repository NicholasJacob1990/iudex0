from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import re
import unicodedata
from typing import Any, Dict, Iterable, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.chat import Chat, ChatMessage


_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "que",
    "se",
    "um",
    "uma",
}

_INTENT_WORDS = {
    "preciso",
    "quero",
    "pode",
    "poderia",
    "buscar",
    "pesquisar",
    "encontrar",
    "analisar",
    "revisar",
    "fazer",
    "gostaria",
}


@dataclass(frozen=True)
class SkillPatternCandidate:
    user_id: str
    pattern_key: str
    occurrences: int
    confidence: float
    sample_prompts: List[str]
    suggested_skill_name: str
    suggested_triggers: List[str]
    suggested_tools: List[str]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", _normalize_text(text))
    return [token for token in tokens if token not in _STOPWORDS]


def _pattern_key(text: str, *, max_tokens: int = 8) -> str:
    tokens = _tokenize(text)
    if len(tokens) < 3:
        return ""
    return " ".join(tokens[:max_tokens]).strip()


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9\\s-]", "", _normalize_text(value))
    text = re.sub(r"[\\s_]+", "-", text).strip("-")
    text = re.sub(r"-+", "-", text)
    return text[:80] or "skill-custom"


def _suggest_tools(pattern: str) -> List[str]:
    selected = ["search_rag", "verify_citation"]
    if any(term in pattern for term in ("jurisprudencia", "precedente", "sumula", "acordao", "stj", "stf")):
        selected.append("search_jurisprudencia")
    if any(term in pattern for term in ("lei", "decreto", "cpc", "artigo", "norma")):
        selected.append("search_legislacao")
    if any(term in pattern for term in ("jusbrasil", "publicacao", "intimacao")):
        selected.append("search_jusbrasil")
    dedup: List[str] = []
    for tool in selected:
        if tool not in dedup:
            dedup.append(tool)
    return dedup


def _build_triggers(pattern: str, prompts: Iterable[str]) -> List[str]:
    triggers: List[str] = []
    if pattern:
        triggers.append(pattern)

    for prompt in prompts:
        normalized = _normalize_text(prompt)
        if normalized and normalized not in triggers:
            triggers.append(normalized[:120].strip())
        if len(triggers) >= 6:
            break

    if len(triggers) < 3 and pattern:
        words = pattern.split()
        if len(words) >= 3:
            triggers.append(" ".join(words[:3]))
        if len(words) >= 4:
            triggers.append(" ".join(words[:4]))

    dedup: List[str] = []
    for trigger in triggers:
        clean = trigger.strip()
        if clean and clean not in dedup:
            dedup.append(clean)
    return dedup[:6]


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a.intersection(b))
    union = len(a.union(b))
    if union == 0:
        return 0.0
    return intersection / union


def detect_skill_patterns(
    prompts: Iterable[str],
    *,
    user_id: str,
    min_occurrences: int = 3,
    max_patterns: int = 10,
) -> List[SkillPatternCandidate]:
    clusters: List[Dict[str, Any]] = []
    for prompt in prompts:
        text = str(prompt or "").strip()
        if len(text) < 20:
            continue
        token_set = set(_tokenize(text))
        if len(token_set) < 3:
            continue

        best_index = -1
        best_score = 0.0
        for index, cluster in enumerate(clusters):
            score = _jaccard_similarity(token_set, cluster["token_union"])
            if score > best_score:
                best_score = score
                best_index = index

        if best_index >= 0 and best_score >= 0.35:
            clusters[best_index]["prompts"].append(text)
            clusters[best_index]["token_union"].update(token_set)
            clusters[best_index]["token_sets"].append(token_set)
        else:
            clusters.append(
                {
                    "prompts": [text],
                    "token_union": set(token_set),
                    "token_sets": [token_set],
                }
            )

    candidates: List[SkillPatternCandidate] = []
    for cluster in clusters:
        examples = cluster["prompts"]
        count = len(examples)
        if count < min_occurrences:
            continue

        token_freq: Dict[str, int] = {}
        for token_set in cluster["token_sets"]:
            for token in token_set:
                token_freq[token] = token_freq.get(token, 0) + 1
        ranked_tokens = sorted(
            token_freq.items(),
            key=lambda item: (-item[1], item[0]),
        )
        key_tokens = [token for token, _ in ranked_tokens if token not in _INTENT_WORDS][:8]
        if not key_tokens:
            key_tokens = [token for token, _ in ranked_tokens][:8]
        key = " ".join(key_tokens).strip() or _pattern_key(examples[0])

        unique_examples: List[str] = []
        for item in examples:
            if item not in unique_examples:
                unique_examples.append(item)
            if len(unique_examples) >= 3:
                break

        confidence = min(0.99, 0.45 + min(count, 10) * 0.05 + min(len(key.split()), 8) * 0.02)
        candidates.append(
            SkillPatternCandidate(
                user_id=user_id,
                pattern_key=key,
                occurrences=count,
                confidence=round(confidence, 3),
                sample_prompts=unique_examples,
                suggested_skill_name=f"skill-{_slugify(key)}",
                suggested_triggers=_build_triggers(key, unique_examples),
                suggested_tools=_suggest_tools(key),
            )
        )

    candidates.sort(key=lambda item: (-item.occurrences, -item.confidence, item.pattern_key))
    return candidates[:max_patterns]


async def detect_user_skill_patterns(
    *,
    user_id: str,
    db: AsyncSession,
    lookback_days: int = 30,
    min_occurrences: int = 3,
    max_patterns: int = 5,
    max_messages: int = 400,
) -> List[SkillPatternCandidate]:
    if not user_id:
        return []

    since = utcnow() - timedelta(days=max(1, int(lookback_days)))
    stmt = (
        select(ChatMessage.content)
        .join(Chat, Chat.id == ChatMessage.chat_id)
        .where(
            Chat.user_id == user_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= since,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(max_messages)
    )
    result = await db.execute(stmt)
    prompts = [str(row[0] or "") for row in result.all()]
    return detect_skill_patterns(
        prompts,
        user_id=user_id,
        min_occurrences=min_occurrences,
        max_patterns=max_patterns,
    )


async def detect_all_users_skill_patterns(
    *,
    db: AsyncSession,
    lookback_days: int = 30,
    min_occurrences: int = 3,
    per_user_limit: int = 5,
) -> Dict[str, List[SkillPatternCandidate]]:
    since = utcnow() - timedelta(days=max(1, int(lookback_days)))
    users_stmt = (
        select(Chat.user_id)
        .join(ChatMessage, ChatMessage.chat_id == Chat.id)
        .where(
            ChatMessage.role == "user",
            ChatMessage.created_at >= since,
        )
        .distinct()
    )
    users_result = await db.execute(users_stmt)
    user_ids = [str(row[0]) for row in users_result.all() if row and row[0]]

    findings: Dict[str, List[SkillPatternCandidate]] = {}
    for user_id in user_ids:
        patterns = await detect_user_skill_patterns(
            user_id=user_id,
            db=db,
            lookback_days=lookback_days,
            min_occurrences=min_occurrences,
            max_patterns=per_user_limit,
        )
        if patterns:
            findings[user_id] = patterns

    return findings
