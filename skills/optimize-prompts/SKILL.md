---
name: optimize-prompts
description: Use this skill whenever the user wants to make their prompts better — whether they say "optimize my prompt", "tune this system prompt", "improve accuracy", or "my prompt isn't working well enough". Also trigger when they ask about writing evaluators, preparing datasets, or any part of the prompt optimization workflow. This skill covers the full loop end-to-end using an evaluator-driven feedback loop (optimize_anything_for_agents): writing evaluators, preparing datasets, calling the function, reading results, and troubleshooting. Trigger it even if the user only asks about one component (e.g. just the evaluator or just the dataset) — the full context helps give better answers.
version: 1.1.0
allowed-tools: Bash(python*)
---

# Optimizing Prompts with `optimize_anything_for_agents()`

`optimize_anything_for_agents()` is the main entry point in `auto_prompter` for automated prompt optimization. It wraps GEPA's `optimize_anything()` with agent-friendly defaults: a structured reflection log and a narrative summary at the end.

## Workflow at a glance

Prompt optimization has four moving parts. Get these right and everything else falls into place:

1. **Write an evaluator** — a function that runs your prompt against one example and returns a `(score, side_info_dict)` where higher score is better. This is the most important part; it identifies mistakes, and ideally how to fix them.
2. **Prepare a dataset** — a list of `dict` examples for training (>5) and a held-out validation set (5-1000).
3. **Call the function** — pass the seed prompts, evaluator, and data; read `result.summary` and `result.result.best_candidate`.
4. **Write the changelog** — append an entry to `PROMPT_CHANGELOG.md` recording what changed and why. Use it as `background` in the next round.

---

## Installation and running

### Dependencies

This skill bundles `scripts/optimize_anything_for_agents.py` directly — no additional package needed beyond two dependencies:

```bash
pip install gepa litellm
```

### LLM authentication

Before calling `optimize_anything_for_agents()`, confirm that LLM credentials are configured — litellm reads them from environment variables (e.g. `ANTHROPIC_API_KEY` for the default Claude model). See the [litellm provider docs](https://docs.litellm.ai/docs/providers) for the full list.

### Using the bundled file

Copy `scripts/optimize_anything_for_agents.py` from this skill directory into your project, then import it directly:

```python
from optimize_anything_for_agents import optimize_anything_for_agents
```

### Running scripts

```bash
python my_optimization.py
```

Or in a Jupyter notebook, make sure the kernel has `gepa` and `litellm` installed.

---

## Worked example

The skill bundles a complete, runnable example in `assets/` and `scripts/`. Read these files when writing new optimization code — they show every pattern you'll encounter.

### The task

Predict Amazon product review ratings (1–5 stars) from review text. The prompts being optimized are Jinja2 templates; the evaluator scores by MSE between the model's predicted rating and the ground-truth rating.

### Files

| File | Role |
|------|------|
| `assets/example_system.txt.jinja2` | Seed system prompt (template, rendered with `review` and `reviewer` variables) — intentionally bad |
| `assets/example_user.txt.jinja2` | Seed user prompt (template, same variables) — intentionally bad |
| `assets/example_dataset_train.jsonl` | Training examples — one JSON object per line with `rating`, `review`, `reviewer` |
| `assets/example_dataset_dev.jsonl` | Validation (held-out) examples — same schema |
| `scripts/example_reviewer.py` | The LLM workflow being optimized: `AutoReviewer` runs Claude on a review and returns a predicted rating |
| `scripts/example_optimizer.py` | The optimization script: wires up the evaluator, loads datasets, calls `optimize_anything_for_agents()`, and writes the best prompts back to `assets/` |

The seed prompts are intentionally bad — they ask for a rating out of 100 in JSON format, but the dataset uses 1–5 star ratings and the evaluator expects a bare integer. This demonstrates that `optimize_anything_for_agents()` can fix broken prompts through error introspection: the evaluator captures the failure in `side_info`, the reflection LM reads it, and subsequent candidates correct the mistakes.

Read `scripts/example_optimizer.py` first — it's the thing this skill helps users write. Then read `scripts/example_reviewer.py` to understand the workflow it wraps.

### Key patterns illustrated

- **Multi-component seed candidate** — `{"system": ..., "user": ...}` lets the optimizer improve each template independently.
- **Jinja2-templated prompts** — render with `jinja2.Environment(...).from_string(candidate[key]).render(**example)` inside the evaluator.
- **Negative MSE as score** — when the metric is "lower is better", negate it so GEPA sees a "higher is better" signal. Set `perfect_score=0.0` accordingly.
- **Evaluator error handling** — the evaluator catches all exceptions, returns a worst-case score, and puts the traceback in `side_info["Error"]` so the reflection LM sees what went wrong.
- **Budget sizing** — `max_metric_calls = len(dataset) * 3` is a reasonable starting point.

---

## Parameters

Read `scripts/optimize_anything_for_agents.py` for the full signature and docstring. The things that matter most:

**`seed_candidate`** — a dict of named prompt components (e.g. `{"system": "...", "user": "..."}`). Each key is optimized independently. Pass `None` with an `objective` string for seedless mode (the LM generates the first candidate from scratch).

**`evaluator`** *(required)* — `(candidate: dict[str, str], example: dict) -> (score: float, side_info: dict)`. The score can be any float — higher is better. The `side_info` dict is shown to the reflection LM — use descriptive keys like `"Error"`, `"Response"`, `"Expected"` so it understands why a candidate failed. Always catch exceptions and return `(0.0, {"Error": traceback})` rather than raising. See `scripts/example_optimizer.py` for a concrete implementation.

**`dataset` / `valset`** — lists of example dicts passed to `evaluator`. `dataset` is the training set (10–30 examples); `valset` is the held-out validation set (5–20 examples). Pass `dataset=None` for single-task mode (no varying inputs).

**`max_metric_calls`** — total evaluation budget. Good default: `len(dataset) * 3`.

### Cost awareness

Each metric call invokes the evaluator once — and if the evaluator itself calls an LLM, that's one LLM call per metric call. On top of that, the reflection LM makes several calls to propose improved candidates. For example, with `max_metric_calls=60` and a Claude-based evaluator, expect roughly 60 evaluator LLM calls plus 5–10 reflection calls. To keep costs down during iteration, use a smaller `dataset`, lower `max_metric_calls`, or switch `lm` to a cheaper model — then do a final pass with a stronger model and fuller dataset.

**`background`** — pass the last few entries from `PROMPT_CHANGELOG.md` here so the reflection LM knows what was already tried.

---

## Evaluator design patterns

The evaluator is the most important part of the optimization — it defines what "better" means. It produces two things: a numerical score and a `side_info` dict. Both matter, and they serve different purposes.

### Numerical score

Higher is better. The score should be **informative** — meaning the reflection LM can distinguish "almost right" from "completely wrong." Prefer partial credit over binary pass/fail whenever possible.

Examples of informative scores:
- **Classification**: accuracy, F1, or weighted agreement (e.g. Cohen's kappa) rather than a bare 0/1
- **Regression**: negative MSE or negative MAE — negate because GEPA maximizes. Near-misses score higher than wild misses, giving the optimizer useful gradient.
- **LLM-as-judge**: ask a second model to rate on a rubric (1-5 or 0-100) across criteria you define. More expensive per call, but often the only option for open-ended generation tasks.

The key principle: if two wrong answers are wrong in different ways, the score should reflect that. A flat 0.0 for all failures tells the reflection LM nothing about which direction to move.

### `side_info` dict

This is what the reflection LM actually *reads* to understand the results. The score tells it *how good*; `side_info` tells it *what happened*, *how the evaluator arrived at the score*, and *why the candidate succeeded or failed*.

Return as much information as you can — even (especially) when the evaluator fails. Include:
- **The input** that was evaluated
- **The model's raw response** before any parsing
- **The parsed/extracted answer** and the expected answer
- **Error tracebacks** when exceptions occur — a stack trace tells the reflection LM exactly what broke

Use descriptive key names (`"Response"`, `"Expected"`, `"Error"`) rather than abbreviations. Always catch exceptions and return a worst-case score with the traceback in `side_info["Error"]` rather than raising — a crashed evaluator gives the reflection LM zero signal. The worked example in `scripts/example_optimizer.py` demonstrates this pattern.

## Return value

`optimize_anything_for_agents()` returns an `AgentOptimizationResult`:

- **`result.best_candidate`** — the optimized prompt dict. Use this going forward.
- **`result.val_aggregate_scores[result.best_idx]`** — best validation score.
- **`summary`** — LLM-generated narrative: score trajectory, what improved, what didn't, why.
- **`reflection_log`** — list of dicts `{"component": str, "prompt": ..., "raw": str}`, useful for debugging why specific changes were made.

---

## Prompt changelog

After every optimization run, append an entry to `PROMPT_CHANGELOG.md` in the project root. This file is the institutional memory of the optimization process — it lets the next round start with context about what was already tried and why.

### When to write

Write the entry immediately after inspecting `result.summary`. Do it before ending the conversation so nothing is lost.

### Entry format

```markdown
### <date> — <description> | <seed_score:.2f>→<best_score:.2f>
**+** <what changed and why it improved — one or two sentences>
**−** <what failed — omit if nothing notable>
**→** <next steps — omit if none>
```

- Do not include the prompt text — the optimized prompt should be saved to its file and tracked with version control, not duplicated in the changelog.
- Merge "what changed" and "why it improved" into `+`: they describe the same thing.
- Skip `−` and `→` lines entirely when there is nothing useful to say.

Populate from `result.summary` and `result.reflection_log`. The `+` line is the most important — it gives the next round's reflection LM actionable signal about what direction worked.

**Example entry:**
```markdown
### 2026-04-12 — extraction prompt | 0.45→0.78
**+** added explicit output format and empty-case instruction; reflection LM identified missing format spec as the main failure mode
**−** chain-of-thought preamble tried in round 3 — no score gain, added latency
**→** test stricter validation: reject dates outside plausible range
```

### Using the changelog in the next run

Pass only the last few entries as `background` — not the entire file — to keep token cost bounded as the changelog grows:

```python
import re

def last_n_entries(path: str, n: int = 3) -> str:
    text = open(path).read()
    entries = re.split(r"(?=^### \d{4}-\d{2}-\d{2})", text, flags=re.MULTILINE)
    return "".join(entries[-n:])

result = optimize_anything_for_agents(
    seed_candidate=last_best_candidate,
    evaluator=my_evaluator,
    dataset=trainset,
    valset=valset,
    background=last_n_entries("PROMPT_CHANGELOG.md"),
)
```

Three entries is usually enough — older history has diminishing value and the reflection LM only has a finite context window.

---

## Troubleshooting

**Score stuck at 0.0** — Check that `evaluator` returns `(float, dict)` and that the `side_info` dict has an `"Error"` key explaining what went wrong. The reflection LM needs error descriptions to propose improvements.

**Optimizer makes no progress** — Increase `max_metric_calls` to try more candidates, or increase `reflection_minibatch_size` so the reflection LM sees more examples and gets richer signal per step.

**`KeyError` in evaluator** — Verify that the keys used in `candidate["key"]` match the keys in `seed_candidate`.

**Costs too high** — Reduce `len(dataset)`, `max_metric_calls`, or switch `lm` to a cheaper model for iteration, then re-run with a stronger model for a final pass.
