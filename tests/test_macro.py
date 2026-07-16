import pandas as pd

from data.macro import get_commodity, get_macro


class FakeFred:
    def get_series(self, code):
        return pd.Series([1.0, 2.0, 3.5])


def test_get_macro_with_injected_client():
    out = get_macro(series={"x": "X", "y": "Y"}, client=FakeFred())
    assert out == {"x": 3.5, "y": 3.5}


def test_get_macro_handles_errors():
    class Boom:
        def get_series(self, code):
            raise RuntimeError("nope")

    assert get_macro(series={"x": "X"}, client=Boom()) == {"x": None}


def test_get_macro_default_series_includes_crude_and_spread():
    out = get_macro(client=FakeFred())  # default series
    assert "crude_oil" in out and out["crude_oil"] == 3.5
    assert "treasury_spread" in out and out["treasury_spread"] == 3.5
    # existing keys preserved
    for k in ("fed_funds", "cpi", "unemployment", "gdp"):
        assert k in out


def test_get_commodity_injected_fetch():
    assert get_commodity("CL=F", fetch=lambda t: 80.5) == 80.5
    assert (
        get_commodity("CL=F", fetch=lambda t: (_ for _ in ()).throw(RuntimeError()))
        is None
    )
