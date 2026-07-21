from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable

from app.models import Claim, ClaimEvidence, ClaimRelation, EvidenceUnit


_NEGATION_TERMS = {
    "不",
    "没有",
    "并非",
    "不是",
    "无",
    "not",
    "no",
    "never",
    "without",
    "false",
}


@dataclass(frozen=True)
class ClaimVerification:
    """Record whether available evidence supports, contradicts, or misses a claim."""

    claim_id: str
    claim_text: str
    relation: ClaimRelation
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    confidence: float
    explanation: str
    needs_human_review: bool


class ClaimGroundingVerifier:
    """Verify claim grounding with deterministic rules or an injected provider."""

    def __init__(self, llm_provider: Callable[..., Any] | None = None):
        """Use rule matching unless an optional LLM verification provider is supplied."""

        self._llm_provider = llm_provider

    def verify_claims(
        self,
        claims: list[Claim],
        evidence_units: list[EvidenceUnit],
        claim_evidence: list[ClaimEvidence],
    ) -> list[ClaimVerification]:
        """Verify every claim against linked evidence before report delivery."""

        evidence_by_id = {unit.id: unit for unit in evidence_units}
        links_by_claim: dict[str, list[ClaimEvidence]] = {}
        for link in claim_evidence:
            links_by_claim.setdefault(link.claim_id, []).append(link)

        results: list[ClaimVerification] = []
        for claim in claims:
            links = links_by_claim.get(claim.id, [])
            linked_units = [
                evidence_by_id[link.evidence_unit_id]
                for link in links
                if link.evidence_unit_id in evidence_by_id
            ]
            if not linked_units:
                linked_units = [
                    evidence_by_id[evidence_id]
                    for evidence_id in claim.evidence_unit_ids
                    if evidence_id in evidence_by_id
                ]
            if self._llm_provider is not None:
                results.append(self._llm_based_verify(claim, linked_units))
                continue
            results.append(self._rule_based_verify(claim, linked_units, links))
        return results

    def _rule_based_verify(
        self,
        claim: Claim,
        evidence: list[EvidenceUnit],
        links: list[ClaimEvidence] | None = None,
    ) -> ClaimVerification:
        """Use relationship labels, keyword overlap, polarity, and evidence count."""

        links = links or []
        support_ids = {
            link.evidence_unit_id
            for link in links
            if link.relation == "support"
        }
        contradict_ids = {
            link.evidence_unit_id
            for link in links
            if link.relation == "contradict"
        }
        claim_terms = _terms(claim.claim_text)
        claim_negative = _has_negation(claim.claim_text)
        overlap_scores: list[float] = []

        for unit in evidence:
            evidence_terms = _terms(unit.text)
            overlap = len(claim_terms & evidence_terms) / max(1, len(claim_terms))
            overlap_scores.append(overlap)
            if overlap < 0.3:
                continue
            if claim_negative == _has_negation(unit.text):
                support_ids.add(unit.id)
            else:
                contradict_ids.add(unit.id)

        max_overlap = max(overlap_scores, default=0.0)
        if support_ids and contradict_ids:
            relation = "contradict"
            confidence = min(0.9, 0.55 + 0.08 * (len(support_ids) + len(contradict_ids)))
            explanation = "Evidence is mixed: linked or lexically similar units both support and contradict the claim."
        elif contradict_ids:
            relation = "contradict"
            confidence = min(0.95, 0.62 + 0.08 * len(contradict_ids) + 0.15 * max_overlap)
            explanation = "Contradicting evidence has matching subject terms but opposing polarity."
        elif support_ids:
            relation = "support"
            confidence = min(0.95, 0.58 + 0.08 * len(support_ids) + 0.2 * max_overlap)
            explanation = "Supporting evidence shares the claim's key terms and polarity."
        else:
            relation = "insufficient"
            confidence = max(0.05, min(0.45, max_overlap))
            explanation = "No linked evidence has enough lexical overlap to ground the claim."

        needs_review = relation == "insufficient" or bool(support_ids and contradict_ids) or confidence < 0.65
        return ClaimVerification(
            claim_id=claim.id,
            claim_text=claim.claim_text,
            relation=relation,
            supporting_evidence_ids=tuple(sorted(support_ids)),
            contradicting_evidence_ids=tuple(sorted(contradict_ids)),
            confidence=round(confidence, 3),
            explanation=explanation,
            needs_human_review=needs_review,
        )

    def _llm_based_verify(self, claim: Claim, evidence: list[EvidenceUnit]) -> ClaimVerification:
        """Delegate semantic verification to an injected provider without direct network calls."""

        if self._llm_provider is None:
            return self._rule_based_verify(claim, evidence)
        result = self._llm_provider(claim, evidence)
        if inspect.isawaitable(result):
            raise TypeError("ClaimGroundingVerifier expects a synchronous llm_provider.")
        if isinstance(result, ClaimVerification):
            return result
        if isinstance(result, dict):
            return ClaimVerification(**result)
        raise TypeError("llm_provider must return ClaimVerification or a compatible dict.")


def _terms(text: str) -> set[str]:
    """Extract lightweight Latin tokens and Chinese bi-grams."""

    normalized = re.sub(r"\s+", " ", text.lower())
    terms = set(re.findall(r"[a-z0-9][a-z0-9+._-]*", normalized))
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[index:index + 2] for index in range(len(run) - 1))
    return terms


def _has_negation(text: str) -> bool:
    """Return whether text contains an explicit negative marker."""

    lowered = text.lower()
    return any(term in lowered for term in _NEGATION_TERMS)
