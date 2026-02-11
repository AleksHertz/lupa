from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.services.query import build_name_preset_condition
from app.models import Item


def _fake_session():
    yield None


def test_top_returns_400_for_invalid_spring_subpreset():
    app.dependency_overrides[get_session] = _fake_session
    client = TestClient(app)

    response = client.get(
        "/top",
        params={
            "name_preset": "spring",
            "spring_subpreset": "invalid",
        },
    )

    assert response.status_code == 400
    assert "подпресет" in response.json().get("detail", "").lower()
    app.dependency_overrides.clear()


def test_build_name_preset_condition_raises_for_invalid_spring_subpreset():
    try:
        build_name_preset_condition(Item.name, "spring", "invalid")
    except ValueError as exc:
        assert "подпресет" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for invalid spring_subpreset")
