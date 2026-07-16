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
SECTOR_MAP_PATH = KNOWLEDGE_DIR / "sector_map.yaml"

REQUIRED_FAMILIES = {"fundamental", "technical", "sentiment", "macro", "catalyst"}
_VALID_DIRECTIONS = {"up", "down"}


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


def load_sector_map(path: str | Path | None = None) -> dict:
    """Load & validate the editable theme->sector map (knowledge/sector_map.yaml).

    Each theme must have a non-empty ``keywords`` list and an ``impacts`` mapping of
    sector -> {direction: up|down, etf: <TICKER>, why?: <str>}. Returns the ``themes``
    mapping. Raises ``ConfigError`` on any schema violation.
    """
    p = Path(path) if path else SECTOR_MAP_PATH
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except FileNotFoundError as e:
        raise ConfigError(f"sector map file not found: {p}") from e
    if not isinstance(data, dict):
        raise ConfigError("sector_map.yaml must be a mapping")

    themes = data.get("themes")
    if not isinstance(themes, dict) or not themes:
        raise ConfigError("sector_map.yaml must have a non-empty 'themes' mapping")

    for theme, spec in themes.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"theme {theme!r} must be a mapping")
        keywords = spec.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ConfigError(f"theme {theme!r} must have a non-empty 'keywords' list")
        impacts = spec.get("impacts")
        if not isinstance(impacts, dict) or not impacts:
            raise ConfigError(f"theme {theme!r} must have a non-empty 'impacts' mapping")
        for sector, impact in impacts.items():
            if not isinstance(impact, dict):
                raise ConfigError(
                    f"impact for {theme!r}/{sector!r} must be a mapping"
                )
            direction = impact.get("direction")
            if direction not in _VALID_DIRECTIONS:
                raise ConfigError(
                    f"impact {theme!r}/{sector!r} direction must be one of "
                    f"{sorted(_VALID_DIRECTIONS)}"
                )
            if not impact.get("etf"):
                raise ConfigError(
                    f"impact {theme!r}/{sector!r} must specify an 'etf'"
                )

    return themes
