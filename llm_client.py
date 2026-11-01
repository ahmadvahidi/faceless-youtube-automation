#!/usr/bin/env python3
"""Shared LLM client with multi-provider fallback.

Why: the video pipeline used to talk to a single provider (Ollama Cloud). One
weekly-quota 429 there broke every video run. This module tries providers in
order — Groq, then Ollama Cloud, then Mistral — so a limit on any one of them
just moves to the next instead of killing the job.

Public API:
    chat(prompt, max_tokens=..., temperature=..., model=..., system=...) -> str
        Returns the assistant text ('' only if every provider fails).
    chat_json(prompt, ...) -> parsed JSON value (list/dict) or raises.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

# name, base_url (None = use LLM_BASE_URL), key env var, default model, extra body
_PROVIDER_SPECS = [
    ("groq",       "https://api.groq.com/openai/v1", "GROQ_API_KEY",
     "openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("ollama",     None,                             "LLM_API_KEY",
     "deepseek-v4.1-flash", {}),
    ("openrouter", "https://openrouter.ai/api/v1",   "OPENROUTER_API_KEY",
     "nvidia/nemotron-3-ultra-550b-a55b:free", {}),
    ("mistral",    "https://api.mistral.ai/v1",      "MISTRAL_API_KEY",
     "mistral-small-latest", {}),
]


def providers():
    """Resolved provider list for the current environment."""
    out = []
    for name, base, key_env, default_model, extra in _PROVIDER_SPECS:
        key = os.environ.get(key_env)
        if not key:
            continue
        if base is None:  # ollama: honour LLM_BASE_URL / LLM_MODEL overrides
            base = os.environ.get("LLM_BASE_URL", "https://ollama.com/v1")
            default_model = os.environ.get("LLM_MODEL", default_model)
        out.append((name, base, key, default_model, extra))
    return out


def _one_call(base, key, model, messages, max_tokens, temperature, timeout, extra):
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    payload.update(extra or {})
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 # Cloudflare in front of some providers 403s the default
                 # Python-urllib agent (error 1010); a normal UA gets through.
                 "User-Agent": "hermes-pipeline/1.0 (+https://hermes-agent.nousresearch.com)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    msg = d["choices"][0]["message"]
    return (msg.get("content") or "").strip(), (msg.get("reasoning") or "").strip()


_REFUSAL_RE = re.compile(
    r"\b(i can(?:no|')?t|i won(?:'|o)t|i'?m sorry|i am sorry|unable to (?:help|assist|comply)|"
    r"cannot (?:help|assist|comply|fulfill)|can(?:'|no)?t fulfill|as an ai)\b",
    re.I)


def looks_refusal(text):
    """True when a reply is a safety refusal rather than an answer.

    A refusal is NOT content: returning it stops the provider chain and the
    caller gets \"I'm sorry, but I can't fulfill this request.\" where it
    expected JSON. Long, structured replies are never refusals.
    """
    t = (text or "").strip()
    if not t or len(t) > 400:
        return False
    if t[:1] in "[{":  # any JSON-ish answer is an answer
        return False
    return bool(_REFUSAL_RE.search(t))


def _pick_model(name, model, default_model):
    """Only use a caller-supplied model hint on the provider it belongs to."""
    if not model:
        return default_model
    if name == "ollama":
        return model
    if name == "groq" and model.startswith(("openai/", "qwen/")):
        return model
    if name == "openrouter" and "/" in model:
        return model
    if name == "mistral" and model.startswith(
            ("mistral", "ministral", "magistral", "codestral")):
        return model
    return default_model


def chat(prompt, max_tokens=900, temperature=0.9, model=None, system=None,
         retries=2, timeout=120, verbose=True, require_json=False):
    """Return assistant text, trying each configured provider in order.

    ``model`` is an optional hint; a provider only uses it when it looks like
    one of its own models, otherwise the provider's default is used.

    ``require_json``: the caller is going to parse the reply as JSON. Then a
    reply with no bracket in it (a leaked reasoning trace, prose preamble, or
    an apology) is NOT an answer — keep walking the provider chain instead of
    returning it, and never fall back to ``reasoning`` at the end.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_err = ""
    fallback_reasoning = ""
    for name, base, key, default_model, extra in providers():
        use_model = _pick_model(name, model, default_model)
        for attempt in range(retries):
            try:
                content, reasoning = _one_call(base, key, use_model, messages,
                                               max_tokens, temperature, timeout, extra)
                if content and looks_refusal(content):
                    # Safety refusal is not an answer — falling through keeps the
                    # pipeline alive instead of shipping "I can't help with that"
                    # to a JSON parser.
                    last_err = f"refusal: {content[:80]}"
                    content = ""
                if content and require_json and "[" not in content and "{" not in content:
                    last_err = f"no JSON in reply: {content[:60]}"
                    content = ""
                if not content and require_json and reasoning and ("[" in reasoning or "{" in reasoning):
                    # Some providers (deepseek/nemotron on ollama & openrouter) put the ENTIRE
                    # answer in the reasoning channel and leave content empty. For a JSON
                    # consumer that trace is still usable — the array is in there.
                    content = reasoning
                    last_err = "recovered JSON from reasoning channel"
                if content:
                    return content
                # A reasoning-only reply is NOT an answer — remember it as a
                # last resort and try the next provider.
                if reasoning:
                    fallback_reasoning = reasoning
                last_err = "empty content"
            except urllib.error.HTTPError as e:
                try:
                    last_err = f"HTTP {e.code} {e.read().decode(errors='replace')[:90]}"
                except Exception:
                    last_err = f"HTTP {e.code}"
                if e.code in (401, 403):
                    break  # bad key: don't waste retries, move to next provider
                if e.code == 429:
                    # Groq's free tier limits TOKENS per minute; a 1.5s nap just burns the
                    # retry. Wait out a real window before trying the same provider again.
                    time.sleep(25 * (attempt + 1))
                    continue
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {str(e)[:90]}"
            time.sleep(1.5 * (attempt + 1))
        if verbose:
            print(f"[llm] provider '{name}' gave no content ({last_err}); next", flush=True)
    if verbose:
        print(f"[llm] ALL providers failed (last: {last_err})", flush=True)
    return "" if require_json else fallback_reasoning


def chat_json(prompt, **kw):
    """Call chat() and parse the first JSON array/object in the reply."""
    raw = chat(prompt, **kw)
    start = min([i for i in (raw.find("["), raw.find("{")) if i != -1], default=-1)
    if start == -1:
        raise ValueError(f"no JSON in LLM response: {raw[:300]}")
    end = max(raw.rfind("]"), raw.rfind("}"))
    return json.loads(raw[start:end + 1])
