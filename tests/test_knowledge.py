import pytest
from agent.knowledge import (
    load_playbook,
    load_rules,
    playbook_index,
    principles_summary,
)
from config import ConfigError


def test_load_rules_valid():
    rules = load_rules()
    assert set(rules.signal_weights) >= {
        "fundamental",
        "technical",
        "sentiment",
        "macro",
        "catalyst",
    }
    assert "rsi_overbought" in rules.alert_thresholds
    assert rules.cooldown_hours > 0


def test_load_rules_invalid_raises(tmp_path):
    bad = tmp_path / "rules.yaml"
    bad.write_text("alert_thresholds: {}\n")  # missing signal_weights
    with pytest.raises(ConfigError):
        load_rules(bad)


def test_load_playbook_and_unknown():
    txt = load_playbook("exit_rules")
    assert "stop" in txt.lower()
    with pytest.raises(ValueError):
        load_playbook("does_not_exist")


def test_playbook_index_lists_seeded():
    idx = playbook_index()
    assert "exit_rules" in idx and "investing_principles" in idx


def test_rules_drive_a_decision():
    rules = load_rules()
    overbought = rules.alert_thresholds["rsi_overbought"]
    assert (80 > overbought) is True
    assert (50 > overbought) is False


def test_principles_summary_nonempty():
    assert len(principles_summary()) > 50
