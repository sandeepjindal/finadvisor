from security.ratelimit import RateLimiter, TokenBudget


def test_rate_limiter_blocks_after_max():
    t = [0.0]
    rl = RateLimiter(max_calls=2, window_seconds=10, clock=lambda: t[0])
    assert rl.allow("u") is True
    assert rl.allow("u") is True
    assert rl.allow("u") is False  # third within window


def test_rate_limiter_resets_after_window():
    t = [0.0]
    rl = RateLimiter(max_calls=1, window_seconds=10, clock=lambda: t[0])
    assert rl.allow("u") is True
    assert rl.allow("u") is False
    t[0] = 11.0
    assert rl.allow("u") is True


def test_rate_limiter_per_key():
    t = [0.0]
    rl = RateLimiter(max_calls=1, window_seconds=10, clock=lambda: t[0])
    assert rl.allow("a") is True
    assert rl.allow("b") is True


def test_token_budget():
    b = TokenBudget(100)
    b.add(50)
    assert not b.over()
    assert b.remaining() == 50
    b.add(60)
    assert b.over()
    assert b.remaining() == 0


def test_token_budget_unlimited():
    b = TokenBudget(None)
    b.add(10**9)
    assert not b.over()
    assert b.remaining() == float("inf")
