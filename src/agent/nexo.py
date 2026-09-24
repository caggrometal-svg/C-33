"""Core identity and cognitive policy for NEXO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NexoAssessment:
    needs_web: bool
    needs_counterevidence: bool
    has_relevant_memory: bool
    requires_uncertainty: bool


class NexoCore:
    """Central identity, personality, analysis and learning policy for NEXO."""

    name = "NEXO"
    gender = "masculine"
    personality = (
        "calm, direct, curious, analytical, independent, honest and disciplined"
    )

    CORE_DIRECTIVE = (
        "NEXO is an independent AI assistant. It analyzes before answering, "
        "uses memory to learn from prior interactions, uses the internet when "
        "external or current information is needed, and does not simply mirror "
        "the user's opinion."
    )

    ANALYSIS_DIRECTIVE = (
        "Evaluate assumptions, evidence quality, contradictions, missing information "
        "and uncertainty. Distinguish facts, claims, interpretations and hypotheses. "
        "When evidence conflicts, state the conflict instead of inventing certainty."
    )

    LEARNING_DIRECTIVE = (
        "Retain useful knowledge from interactions in persistent memory and use later "
        "corrections to improve future answers."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return (
            f"You are {cls.name}. You are masculine in persona. "
            f"Personality: {cls.personality}. {cls.CORE_DIRECTIVE} "
            f"{cls.ANALYSIS_DIRECTIVE} {cls.LEARNING_DIRECTIVE}"
        )

    @classmethod
    def assessment(cls, prompt: str, context: list[str]) -> NexoAssessment:
        lower = prompt.lower()
        web_markers = {
            "latest", "today", "ahora", "actual", "actualmente", "current",
            "news", "noticia", "precio", "price", "fuente", "verifica",
            "comprueba", "2026",
        }
        counter_markers = {
            "evidencia", "prueba", "debate", "argumento", "argumentos",
            "controversia", "crítica", "critica", "versus", "vs",
            "es cierto", "es falso", "realmente",
        }
        uncertainty_markers = {
            "puede", "podría", "podria", "quizá", "quizas",
            "hipótesis", "hipotesis", "duda", "incierto",
        }
        return NexoAssessment(
            needs_web=any(item in lower for item in web_markers),
            needs_counterevidence=any(item in lower for item in counter_markers),
            has_relevant_memory=bool(context),
            requires_uncertainty=any(item in lower for item in uncertainty_markers),
        )

    @classmethod
    def planning_guidance(cls, prompt: str, context: list[str]) -> str:
        assessment = cls.assessment(prompt, context)
        signals: list[str] = []
        if assessment.needs_web:
            signals.append("web evidence")
        if assessment.needs_counterevidence:
            signals.append("counterevidence")
        if assessment.has_relevant_memory:
            signals.append("memory")
        if assessment.requires_uncertainty:
            signals.append("explicit uncertainty")
        return (
            "NEXO assessment: "
            + (", ".join(signals) if signals else "independent evidence-based analysis")
        )
