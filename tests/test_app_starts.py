from app.main import app


def test_app_loads() -> None:
    assert app.title == "BidExpert API"
