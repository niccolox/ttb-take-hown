"""Hello-world for the Azure OpenAI / Foundry integration (openai SDK).

Reads AZ_OPENAI_URI / AZ_OPENAI_API_KEY / AZ_OPENAI_MODEL from the
environment or ../.env, derives the SDK base_url from the full
chat-completions URI, and asks the deployed model to say hello. Tries the
chat surface first, then the Responses API (Foundry gateways route some
deployments there — same behavior the in-app client handles).

Run: .venv/bin/python scripts/hello_azure_openai.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def load_env() -> None:
    env = Path(__file__).parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k, v.strip('"'))


def base_and_query(uri: str) -> tuple[str, dict]:
    # ".../models/chat/completions?api-version=…" (Foundry inference) or
    # ".../openai(/v1)/chat/completions" (Azure OpenAI) → SDK base_url,
    # preserving any api-version as a default query param
    from urllib.parse import parse_qsl, urlsplit
    parts = urlsplit(uri)
    path = parts.path
    for suffix in ("/chat/completions", "/responses"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    base = f"{parts.scheme}://{parts.netloc}{path}"
    return base, dict(parse_qsl(parts.query))


def main() -> int:
    load_env()
    if os.environ.get("OPENAI_DEBUG", "").lower() in ("1", "true", "yes", "on"):
        os.environ.setdefault("OPENAI_LOG", "debug")   # openai SDK's native debug
        import logging
        logging.basicConfig(level=logging.DEBUG)
    uri = os.environ.get("AZ_OPENAI_URI", "")
    key = os.environ.get("AZ_OPENAI_API_KEY", "")
    model = os.environ.get("AZ_OPENAI_MODEL", "gpt-4.1")
    if not uri or not key:
        print("Set AZ_OPENAI_URI and AZ_OPENAI_API_KEY (see .env).")
        return 1

    from openai import OpenAI
    base, query = base_and_query(uri)
    client = OpenAI(base_url=base, api_key=key,
                    default_headers={"api-key": key},
                    default_query=query or None)
    print(f"endpoint: {base}\nmodel:    {model}")

    prompt = "Say hello to the Label Check team in one short sentence."
    try:
        chat = client.chat.completions.create(
            model=model, max_tokens=2400,
            messages=[{"role": "user", "content": prompt}])
        text = chat.choices[0].message.content
        if text and text.strip():
            print("chat.completions ->", text.strip())
            return 0
        print("chat.completions -> (empty content; trying Responses API)")
    except Exception as e:  # noqa: BLE001 — fall through to responses
        print(f"chat.completions -> {type(e).__name__}: trying Responses API")

    resp = client.responses.create(model=model, input=prompt,
                                   max_output_tokens=2400)
    print("responses       ->", (resp.output_text or "").strip() or "(empty)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
