"""Prompt optimization for AutoReviewer using optimize_anything_for_agents."""

import json
import traceback
import jinja2
from litellm import completion

from optimize_anything_for_agents import optimize_anything_for_agents
from example_reviewer import ASSETS_DIR, MODEL, load_dataset, mse

_ENV = jinja2.Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)


def evaluator(candidate: dict[str, str], example: dict) -> tuple[float, dict]:
    """Score one candidate prompt against one review example."""
    raw = None
    y_pred = None
    y_true = None
    input_json = None
    # worse negative mse on 1-5 rating scale
    score = -16.0
    try:
        input_json = json.dumps(example)
        y_true = example["rating"]
        system_prompt = _ENV.from_string(source=candidate["system"]).render(**example)
        user_prompt = _ENV.from_string(source=candidate["user"]).render(**example)
        response = completion(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()
        y_pred = int(raw)
        # gepa scores are "higher is better"
        score = -mse(y_pred=y_pred, y_true=y_true)
        return score, {
            "Input": input_json,
            "Response": raw,
            "Parsed Response": y_pred,
            "Correct Answer": y_true,
            "Error": None,
        }
    except Exception:
        return score, {
            "Input": input_json,
            "Response": raw,
            "Parsed Response": y_pred,
            "Correct Answer": y_true,
            "Error": traceback.format_exc(),
        }


def main() -> None:
    trainset = load_dataset(path=ASSETS_DIR / "example_dataset_train.jsonl")
    valset = load_dataset(path=ASSETS_DIR / "example_dataset_dev.jsonl")
    print(f"Training examples : {len(trainset)}")
    print(f"Validation examples: {len(valset)}")

    seed_candidate = {
        "system": (ASSETS_DIR / "example_system.txt.jinja2").read_text(),
        "user": (ASSETS_DIR / "example_user.txt.jinja2").read_text(),
    }

    result = optimize_anything_for_agents(
        seed_candidate=seed_candidate,
        evaluator=evaluator,
        dataset=trainset,
        valset=valset,
        objective="Predict the star rating (1-5) of an Amazon product review from its text.",
        max_metric_calls=60,  # 20 train examples × 3
        reflection_minibatch_size=5,
        perfect_score=0.0,
    )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(result.summary)

    best = result.result.best_candidate
    val_scores = result.result.val_aggregate_scores
    best_idx = result.result.best_idx

    print("\n" + "=" * 60)
    print("BEST CANDIDATE")
    print("=" * 60)
    print(f"[system]\n{best['system']}\n")
    print(f"[user]\n{best['user']}")
    print(f"\nBest validation score: {val_scores[best_idx]:.4f}")

    (ASSETS_DIR / "example_system.txt.jinja2").write_text(best["system"])
    (ASSETS_DIR / "example_user.txt.jinja2").write_text(best["user"])
    print(f"\nWrote optimized prompts to {ASSETS_DIR}")


if __name__ == "__main__":
    main()
