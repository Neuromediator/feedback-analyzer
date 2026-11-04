"""Minimal OpenRouter chat client with strict JSON-schema output."""

import json
from dataclasses import dataclass, field

import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
FATAL_STATUSES = {400, 401, 402, 403, 404}


class AnalyzerError(Exception):
    """A failed model call. Fatal errors (bad key, no credits) are not worth retrying."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


@dataclass
class ChatResult:
    data: dict
    model: str


@dataclass
class OpenRouterClient:
    api_key: str
    model: str
    reasoning: str | None = None
    timeout: float = 90
    client: httpx.AsyncClient | None = None
    total_cost: float = 0.0
    models_seen: set[str] = field(default_factory=set)

    async def aclose(self) -> None:
        if self.client:
            await self.client.aclose()

    def _payload(self, system: str, user: str, name: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            },
            "provider": {"require_parameters": True},
        }
        if self.reasoning:
            payload["reasoning"] = {"effort": self.reasoning}
        return payload

    async def chat_json(self, system: str, user: str, name: str, schema: dict) -> ChatResult:
        if not self.api_key:
            raise AnalyzerError(
                "OPENROUTER_API_KEY is not set. Add it to the .env file.", fatal=True
            )
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await self.client.post(
                URL,
                json=self._payload(system, user, name, schema),
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except httpx.HTTPError as e:
            raise AnalyzerError(f"Could not reach OpenRouter: {type(e).__name__}") from e
        if resp.status_code != 200:
            message = _error_message(resp)
            raise AnalyzerError(
                f"OpenRouter error {resp.status_code}: {message}",
                fatal=resp.status_code in FATAL_STATUSES,
            )
        body = resp.json()
        try:
            content = json.loads(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise AnalyzerError("The model returned an unusable response.") from None
        self.total_cost += (body.get("usage") or {}).get("cost") or 0.0
        served = body.get("model") or self.model
        self.models_seen.add(served)
        return ChatResult(data=content, model=served)


def _error_message(resp: httpx.Response) -> str:
    try:
        return str(resp.json()["error"]["message"])
    except (KeyError, TypeError, ValueError):
        return resp.text[:200]
