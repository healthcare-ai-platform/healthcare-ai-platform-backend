"""
POST /api/v1/ai/chat
Anthropic API call is mocked — no real API key needed.
"""
from unittest.mock import patch, AsyncMock, MagicMock
import httpx


CHAT_PAYLOAD = {
    "messages": [{"role": "user", "content": "How many documents were processed today?"}]
}


async def test_chat_no_api_key_returns_503(unit_client):
    # The module-level ANTHROPIC_API_KEY is already loaded from .env.
    # Patch the module variable directly, not os.environ.
    with patch("app.api.routers.ai.ANTHROPIC_API_KEY", ""):
        r = await unit_client.post("/api/v1/ai/chat", json=CHAT_PAYLOAD)
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


async def test_chat_anthropic_error_returns_502(unit_client):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_response)

    with (
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}),
        patch("app.api.routers.ai.ANTHROPIC_API_KEY", "sk-test"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        r = await unit_client.post("/api/v1/ai/chat", json=CHAT_PAYLOAD)
    assert r.status_code == 502


async def test_chat_success_returns_reply(unit_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"text": "1,284 documents were processed today with 97.3% extraction success."}]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_response)

    with (
        patch("app.api.routers.ai.ANTHROPIC_API_KEY", "sk-test"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        r = await unit_client.post("/api/v1/ai/chat", json=CHAT_PAYLOAD)

    assert r.status_code == 200
    body = r.json()
    assert "reply" in body
    assert "1,284" in body["reply"]


async def test_chat_sends_system_prompt(unit_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": [{"text": "ok"}]}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_response)

    with (
        patch("app.api.routers.ai.ANTHROPIC_API_KEY", "sk-test"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        await unit_client.post("/api/v1/ai/chat", json=CHAT_PAYLOAD)

    call_json = mock_client.post.call_args.kwargs["json"]
    assert "system" in call_json
    assert "healthcare" in call_json["system"].lower()
    assert call_json["model"] == "claude-sonnet-4-6"


async def test_chat_empty_messages_accepted_by_fastapi(unit_client):
    # FastAPI accepts an empty messages list (no schema constraint on length).
    # Mock Anthropic so the request completes without a real API call.
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": [{"text": "ok"}]}
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_response)
    with (
        patch("app.api.routers.ai.ANTHROPIC_API_KEY", "sk-test"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        r = await unit_client.post("/api/v1/ai/chat", json={"messages": []})
    assert r.status_code == 200


async def test_chat_missing_messages_field_422(unit_client):
    r = await unit_client.post("/api/v1/ai/chat", json={})
    assert r.status_code == 422
