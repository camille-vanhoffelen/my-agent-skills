import json
from pathlib import Path

import jinja2
import numpy as np
from litellm import completion

ASSETS_DIR = Path(__file__).parent.parent / "assets"
MODEL = "anthropic/claude-sonnet-4-6"

_ENV = jinja2.Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)


class AutoReviewer:
    def __init__(self):
        system_prompt_template_text = (
            ASSETS_DIR / "example_system.txt.jinja2"
        ).read_text()
        user_prompt_template_text = (ASSETS_DIR / "example_user.txt.jinja2").read_text()
        self.system_prompt_template = _ENV.from_string(
            source=system_prompt_template_text
        )
        self.user_prompt_template = _ENV.from_string(source=user_prompt_template_text)

    def predict(self, review: str, reviewer: str) -> tuple[int, str]:
        system_prompt = self.system_prompt_template.render(
            review=review, reviewer=reviewer
        )
        user_prompt = self.user_prompt_template.render(review=review, reviewer=reviewer)

        response = completion(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        y_pred = int(content)
        return y_pred, content


def mse(y_pred: int | np.ndarray, y_true: int | np.ndarray) -> float:
    return float(np.mean(np.square(np.subtract(y_pred, y_true))))


def load_dataset(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
