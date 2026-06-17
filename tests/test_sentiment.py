from data.news import news_sentiment


def test_positive_sentiment():
    assert news_sentiment("Stellar earnings, record profit, strong growth!") > 0


def test_negative_sentiment():
    assert news_sentiment("Disastrous quarter, massive losses, bankruptcy fears") < 0


def test_neutral_emptyish():
    assert news_sentiment("") == 0.0
