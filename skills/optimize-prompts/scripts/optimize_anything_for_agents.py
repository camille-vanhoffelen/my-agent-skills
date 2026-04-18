from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from gepa.core.result import GEPAResult
from gepa.optimize_anything import (
    EngineConfig,
    GEPAConfig,
    ReflectionConfig,
    make_litellm_lm,
    optimize_anything,
)
from gepa.strategies.instruction_proposal import InstructionProposalSignature

DEFAULT_LM = "anthropic/claude-sonnet-4-6"


@dataclass
class AgentOptimizationResult:
    """Extended result from optimize_anything_for_agents.

    Attributes:
        result: The underlying GEPAResult with all candidates, scores, and lineage.
        summary: LLM-generated narrative covering the optimization trajectory,
            key reflection insights, and why the best candidate works.
        reflection_log: Raw log of every reflection step — each entry holds the
            component name, the full prompt sent to the reflection LM, and its
            raw response.
    """

    result: GEPAResult
    summary: str
    reflection_log: list[dict[str, Any]]


def optimize_anything_for_agents(
    seed_candidate: str | dict[str, str] | None = None,
    *,
    evaluator: Callable[..., Any],
    dataset: list | None = None,
    valset: list | None = None,
    objective: str | None = None,
    background: str | None = None,
    lm: str = DEFAULT_LM,
    max_metric_calls: int = 30,
    reflection_minibatch_size: int = 3,
    perfect_score: float = 1.0,
) -> AgentOptimizationResult:
    """Opinionated, agent-friendly wrapper around GEPA's optimize_anything().

    Wraps optimize_anything() with a custom reflection callback that captures
    every LLM reflection step (prompt + raw response), then generates a
    narrative summary of both the optimization results and the reasoning
    behind each improvement.

    Args:
        seed_candidate: Starting candidate — a plain string or a dict of
            named components.  Pass ``None`` for seedless mode (requires
            ``objective``).
        evaluator: Callable ``(candidate, example) -> (score, side_info)``
            (or ``(candidate,) -> (score, side_info)`` for single-task mode).
        dataset: Training examples.  ``None`` for single-task search.
        valset: Validation examples.  ``None`` to skip generalization eval.
        objective: Plain-text description of what to optimize.  Required for
            seedless mode; optional but helpful otherwise.
        background: Additional context passed to the reflection LM.
        lm: LiteLLM model string used for both reflection proposals and the
            final summary.  Defaults to claude-sonnet-4-6.
        max_metric_calls: Total evaluation budget (default: 30).
        reflection_minibatch_size: Number of examples shown to the reflection
            LM per step (default: 3).  Smaller batches produce focused
            improvements; larger batches give the LM more context at once.
        perfect_score: Score threshold at which optimization stops early
            (default: 1.0).

    Returns:
        AgentOptimizationResult with the GEPAResult, a narrative summary,
        and the raw reflection log.
    """
    reflection_log: list[dict[str, Any]] = []

    def _log_reflection(component: str, prompt: str | list, raw: str) -> None:
        reflection_log.append({"component": component, "prompt": prompt, "raw": raw})

    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=max_metric_calls,
            candidate_selection_strategy="current_best",
            val_evaluation_policy="full_eval",
        ),
        reflection=ReflectionConfig(
            reflection_lm=None,  # handled by custom_candidate_proposer below
            custom_candidate_proposer=_make_proposer(lm, _log_reflection),
            reflection_minibatch_size=reflection_minibatch_size,
            skip_perfect_score=True,
            perfect_score=perfect_score,
        ),
    )

    result = optimize_anything(
        seed_candidate=seed_candidate,
        evaluator=evaluator,
        dataset=dataset,
        valset=valset,
        objective=objective,
        background=background,
        config=config,
    )

    summary = _summarize(result, reflection_log, lm)

    return AgentOptimizationResult(
        result=result,
        summary=summary,
        reflection_log=reflection_log,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_proposer(
    model_name: str,
    on_reflection: Callable[[str, str | list, str], None],
) -> Callable:
    """Return a candidate proposer identical to GEPA's default but with a
    callback fired before extraction so every reflection step is logged."""
    lm_fn = make_litellm_lm(model_name=model_name)

    def proposer(
        candidate: dict[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        new_texts: dict[str, str] = {}
        for name in components_to_update:
            if name not in reflective_dataset or not reflective_dataset[name]:
                continue
            input_dict = {
                "current_instruction_doc": candidate[name],
                "dataset_with_feedback": reflective_dataset[name],
            }
            prompt = InstructionProposalSignature.prompt_renderer(input_dict=input_dict)
            raw = lm_fn(prompt=prompt)
            on_reflection(component=name, prompt=prompt, raw=raw)
            new_texts[name] = InstructionProposalSignature.output_extractor(
                lm_out=raw.strip()
            )["new_instruction"]
        return new_texts

    return proposer


def _summarize(
    result: GEPAResult,
    reflection_log: list[dict[str, Any]],
    lm: str,
) -> str:
    """Ask the LM for a concise narrative covering results + reflection reasoning."""
    from litellm import completion

    scores = result.val_aggregate_scores
    seed_score = f"{scores[0]:.3f}" if scores else "n/a"
    best_score = f"{scores[result.best_idx]:.3f}" if scores else "n/a"

    trajectory_lines = [
        f"  Candidate {i} (parents={result.parents[i]}): val_score={s:.3f}"
        for i, s in enumerate(scores)
    ]
    trajectory = "\n".join(trajectory_lines) or "  (no candidates)"

    if reflection_log:
        reflection_sections = "\n\n".join(
            f"### Reflection {i + 1} — component={e['component']!r}\n{e['raw']}"
            for i, e in enumerate(reflection_log)
        )
    else:
        reflection_sections = "(no reflection steps were executed)"

    prompt = f"""You are summarizing the results of an automated prompt-optimization run powered by GEPA.

## Score trajectory
{trajectory}

Seed score : {seed_score}
Best score : {best_score}

## Best candidate
{result.best_candidate}

## Reflection log (raw LLM reasoning at each improvement step)
{reflection_sections}

Write a concise summary covering:
1. Optimization Trajectory: score improvement from seed to best, number of candidates explored.
2. Error Analysis: what errors the reflection LLM spotted throughout the optimization, and their root causes.
3. Improvements: updates made to the instructions that boosted scores.
4. Failures: updates made to the instructions that did not improve scores.
5. Final result: short overview of the new best instructions.
Keep the tone factual and analytical, use bullet points where appropriate.
"""

    try:
        response = completion(
            model=lm,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        return (
            f"Summary generation failed: {e}\n"
            f"Seed score: {seed_score}, Best score: {best_score}.\n"
            f"See result.result for raw optimization data."
        )
