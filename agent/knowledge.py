"""Load the editable "skills": markdown playbooks (knowledge/) + numeric thresholds
(rules.yaml). Tuning behavior is a config edit, not a code change. Step 1.6b.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from config import ConfigError

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"
RULES_PATH = ROOT / "rules.yaml"

REQUIRED_FAMILIES = {"fundamental", "technical", "sentiment", "macro", "catalyst"}


@dataclass(frozen=True)
class Rules:
    signal_weights: dict
    alert_thresholds: dict
    cooldown_hours: float
    max_position_weight: float
    raw: dict = field(default_factory=dict)


def load_rules(path: str | Path | None = None) -> Rules:
    p = Path(path) if path else RULES_PATH
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except FileNotFoundError as e:
        raise ConfigError(f"rules file not found: {p}") from e
    if not isinstance(data, dict):
        raise ConfigError("rules.yaml must be a mapping")

    weights = data.get("signal_weights")
    if not isinstance(weights, dict) or not REQUIRED_FAMILIES <= set(weights):
        raise ConfigError(
            f"signal_weights must include all of {sorted(REQUIRED_FAMILIES)}"
        )
    for k, v in weights.items():
        if not isinstance(v, (int, float)):
            raise ConfigError(f"signal weight {k!r} must be numeric")

    thresholds = data.get("alert_thresholds")
    if not isinstance(thresholds, dict):
        raise ConfigError("alert_thresholds must be a mapping")

    try:
        cooldown = float(data["cooldown_hours"])
        max_weight = float(data["max_position_weight"])
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigError(
            "cooldown_hours and max_position_weight are required numbers"
        ) from e

    return Rules(weights, thresholds, cooldown, max_weight, data)


def load_playbook(topic: str) -> str:
    p = KNOWLEDGE_DIR / f"{topic}.md"
    if not p.exists():
        raise ValueError(f"unknown playbook: {topic!r}")
    return p.read_text()


def playbook_index() -> list[str]:
    return sorted(p.stem for p in KNOWLEDGE_DIR.glob("*.md"))


def principles_summary(max_chars: int = 1500) -> str:
    parts = []
    for topic in ("investing_principles", "exit_rules"):
        try:
            parts.append(load_playbook(topic))
        except ValueError:
            pass
    return "\n\n".join(parts)[:max_chars]
