from data.csv_import import import_holdings_csv


def test_standard_columns():
    csv = "ticker,shares,avg_cost\nNVDA,30,450\nVOO,50,400\n"
    assert import_holdings_csv(csv) == [("NVDA", 30.0, 450.0), ("VOO", 50.0, 400.0)]


def test_variant_columns_and_currency():
    csv = "Symbol,Quantity,Cost Basis\nAAPL,10,$150.50\n"
    assert import_holdings_csv(csv) == [("AAPL", 10.0, 150.5)]


def test_malformed_rows_skipped():
    csv = "ticker,shares,avg_cost\nNVDA,30,450\nBAD,notanumber,x\n,,\n"
    assert import_holdings_csv(csv) == [("NVDA", 30.0, 450.0)]


def test_injection_ticker_skipped():
    csv = "ticker,shares,avg_cost\n'); DROP TABLE holdings;--,1,1\n"
    assert import_holdings_csv(csv) == []
