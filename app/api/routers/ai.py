import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = (
    "You are a healthcare data platform assistant for HealthAI. "
    "You help managers, analysts, and data engineers understand pipeline health, "
    "patient report processing, SLA status, and extraction quality. "
    "Keep responses concise and data-focused. Use bullet points for lists. "
    "Example context: 1,284 documents processed today, 97.3% extraction success, "
    "18 in DLQ, 5 tenants active. "
    "If asked about specific patients, remind users to use the Patients page for HIPAA-compliant access."
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1000,
        "system": SYSTEM_PROMPT,
        "messages": [m.model_dump() for m in body.messages],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            ANTHROPIC_URL,
            json=payload,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {resp.text}")

    data = resp.json()
    reply = data.get("content", [{}])[0].get("text", "No response generated.")
    return ChatResponse(reply=reply)
