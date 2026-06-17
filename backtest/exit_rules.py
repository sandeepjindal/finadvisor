"""Backtest exit rules in pure pandas (no vectorbt dependency required) so the stack stays
installable everywhere. Validates exit discipline before trusting it with real money.
Step 4.4.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    total_return: float
    buy_hold_return: float
    max_drawdown: float
    exit_index: int
    exited_early: bool


def max_drawdown(equity: pd.Series) -> float:
    if len(equity) == 0:
        return 0.0
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    return float(dd.min())


def backtest_trailing_stop(close, stop_pct: float = 12.0) -> BacktestResult:
    """Buy at the first bar; exit when price falls stop_pct below the running peak."""
    s = pd.Series(list(close), dtype=float).reset_index(drop=True)
    entry = s.iloc[0]
    peak = entry
    exit_price = s.iloc[-1]
    exit_idx = len(s) - 1
    for i, p in enumerate(s):
        peak = max(peak, p)
        if p <= peak * (1 - stop_pct / 100.0):
            exit_price = p
            exit_idx = i
            break
    strat_ret = (exit_price - entry) / entry
    bh_ret = (s.iloc[-1] - entry) / entry
    equity = s.iloc[: exit_idx + 1]
    return BacktestResult(
        total_return=strat_ret,
        buy_hold_return=bh_ret,
        max_drawdown=max_drawdown(equity),
        exit_index=exit_idx,
        exited_early=exit_idx < len(s) - 1,
    )
