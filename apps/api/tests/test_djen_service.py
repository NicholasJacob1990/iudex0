import pytest

from app.schemas.djen import DjenSearchParams
from app.services.djen_service import DataJudClient, get_datajud_alias, normalize_npu


def test_normalize_npu_digits_only():
    assert normalize_npu("1234567-12.2024.8.13.0000") == "12345671220248130000"
    assert normalize_npu("001.002-003") == "001002003"


def test_get_datajud_alias_lowercase():
    assert get_datajud_alias("TJMG") == "tjmg"
    assert get_datajud_alias("trf1") == "trf1"


def test_djen_search_params_requires_filter():
    with pytest.raises(ValueError):
        DjenSearchParams()


def test_djen_search_params_requires_uf_oab():
    with pytest.raises(ValueError):
        DjenSearchParams(numeroOab="12345")


@pytest.mark.asyncio
async def test_datajud_check_updates_returns_full_datetime(monkeypatch):
    class DummyResponse:
        status_code = 200
        headers = {}

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            return None

    class DummyAsyncClient:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return self._response

    data = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "movimentos": [
                            {"dataHora": "2024-01-01T10:20:30", "nome": "Publicacao"}
                        ]
                    }
                }
            ]
        }
    }

    response = DummyResponse(data)
    monkeypatch.setattr(
        "app.services.djen_service.httpx.AsyncClient",
        lambda *args, **kwargs: DummyAsyncClient(response),
    )

    client = DataJudClient(api_key="test-key", base_url="https://example.com")
    result = await client.check_updates("12345671220248130000", "TJMG", last_seen=None)
    assert result == "2024-01-01T10:20:30"
