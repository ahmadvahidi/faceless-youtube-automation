#!/usr/bin/env python3
"""Multi-language metadata for uploads — the cheapest reach lever left on the table.

Verified 2026-10-16: the stored OAuth token CAN write `localizations` on a live video
(`videos.update?part=localizations`), and YouTube serves the localised title/description to
viewers whose player language matches — so ONE upload can compete in a second language
market with no second render, no second upload and no extra watch-time node (all views still
roll up into a single ranking signal).

What is NOT available through the API:
  * multi-language AUDIO tracks (the real retention lever: dubbed audio holds a viewer far
    better than subtitles) — Studio only, and the track file must be the video's exact
    duration;
  * `captions.insert` / `captions.list` — the API answers HTTP 403
    ACCESS_TOKEN_SCOPE_INSUFFICIENT because the stored refresh token carries `youtube`,
    `youtube.readonly` and `youtube.upload` but not `youtube.force-ssl`. Adding a translated
    CAPTION track therefore needs one owner action (re-run consent with the extra scope).
Both are recorded in the `faceless-youtube` skill; do not re-derive them.

Two gotchas that cost a round trip each:
  * `videos.update?part=localizations` fails with HTTP 400 "trying to add localized video
    details without specifying the default language" until the video's snippet carries
    `defaultLanguage`. Set it FIRST (it is also a targeting improvement: it tells YouTube
    which language the video is in).
  * the read-back of `part=localizations` lags a few seconds behind the write — the PUT
    response echoes the new set immediately, a `videos.list` right afterwards can still show
    the OLD set. Retry the read before concluding the write failed.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path


def _log(*a):
    print(*a, flush=True)


def _env_files(yt_mod):
    cands = []
    try:
        cands.append(Path(yt_mod.__file__).resolve().parent / ".env")
    except Exception:  # noqa: BLE001
        pass
    cands.append(Path(__file__).resolve().parent / ".env")   # this module's own project
    cands.append(Path("/opt/data/.env"))                     # the gateway copy, last resort
    return cands


def ensure_keys(yt_mod=None) -> str:
    """Make sure an LLM key is visible to `llm_client`, which reads os.environ WHEN CALLED.

    An entrypoint that parses its .env AFTER the modules that need it (math-videos loads it inside
    `notify_telegram`, i.e. after the upload) leaves every earlier LLM call with an EMPTY provider
    list — which surfaces as `[llm] ALL providers failed (last: )` with an empty reason. That is how
    a localisation step turns into a silent no-op, so this module loads its project's .env itself
    instead of trusting the caller's import order.

    ALL candidate files are merged, not just the first that yields a key: a project whose .env holds
    only `LLM_API_KEY` would otherwise pin the chain to the slow Ollama provider (whose reasoning
    models can return EMPTY content), while the Groq key sitting in the sibling project's .env is
    exactly what makes the chain fast and reliable.
    """
    if _key_visible():
        return "already in the environment"
    used, keys = [], []
    for f in _env_files(yt_mod):
        try:
            if not f.exists():
                continue
            for line in f.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()
            used.append(str(f))
            keys = [k for k in ("GROQ_API_KEY", "LLM_API_KEY", "OPENROUTER_API_KEY",
                                "MISTRAL_API_KEY") if os.environ.get(k)]
        except Exception:  # noqa: BLE001
            continue
    if not keys:
        return ""
    return f"keys {','.join(keys)} from {len(used)} file(s)"


def _key_visible() -> bool:
    return bool(os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY")
                or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("MISTRAL_API_KEY"))


def translate_de(title: str, desc: str, yt_mod=None) -> dict | None:
    """German title + description for a video. None if the LLM is unavailable/unsuitable."""
    src = ensure_keys(yt_mod)
    if not src:
        _log("[i18n] no LLM key visible — add it to the project .env")
        return None
    try:
        import llm_client
        prompt = (
            "Translate this YouTube Short metadata into natural, idiomatic GERMAN (du-Form, "
            "no literal word-for-word translation, keep any number). Reply with ONLY a JSON "
            "object with the keys title and description.\n\n"
            f"TITLE: {title}\n\nDESCRIPTION: {desc[:600]}\n\n"
            'Schema: {"title": "<=70 chars", "description": "<=1200 chars"}')
        raw = llm_client.chat(prompt, max_tokens=1200, temperature=0.4)
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        # A reasoning model that failed on every provider makes `chat()` hand back its REASONING
        # TRACE. A trace is not an answer: never burn its prose into a live video's metadata.
        if m.start() > 0 or len(raw) > 1500:
            _log("[i18n] reply looked like a reasoning trace — refused")
            return None
        out = json.loads(m.group(0))
        t = (out.get("title") or "").strip()
        if not t or len(t) > 100:
            return None
        return {"title": t, "description": (out.get("description") or "").strip()}
    except Exception as e:  # noqa: BLE001
        _log(f"[i18n] translation unavailable ({str(e)[:100]})")
        return None


def apply_de(vid: str, title: str, desc: str, yt_mod, lang: str = "de", force: bool = False):
    """Set `lang` localisation (+ defaultLanguage) on a live video. Returns (ok, message).

    `yt_mod` is the channel's own yt_uploader module — passed in on purpose, because two
    projects on this box hold yt_uploader copies bound to DIFFERENT channels and an import
    here could silently pick the wrong one.
    """
    tok = yt_mod.get_access_token()
    cur = yt_mod._api(tok, f"/youtube/v3/videos?part=snippet,localizations&id={vid}")
    if not cur.get("items"):
        return False, "video not found"
    it = cur["items"][0]
    sn = it["snippet"]

    # Idempotent: a second caller (the entrypoint AND yt_publish both offer to localise) must not
    # re-translate and re-write. An existing track with a title is done — unless the caller asks to
    # overwrite it (`force`, e.g. to replace a placeholder or a bad translation).
    have = it.get("localizations", {}).get(lang) or {}
    if have.get("title") and not force:
        return True, f"already localised: {have['title'][:60]!r}"

    tr = translate_de(title, desc, yt_mod=yt_mod)
    if tr is None:
        return False, "no translation"

    # `videos.update?part=localizations` answers HTTP 400 `defaultLanguageNotSet`
    # ("trying to add localized video details without specifying the default language of the video
    # details") until the video's SNIPPET carries `defaultLanguage` — which is the video's declared
    # language, so it is a targeting win on its own and is missing on uploads that never set it.
    # Setting it is best-effort and the localisation write is retried once after it, because the
    # API can report the same 400 for a write issued while the snippet change is still propagating.
    def _write():
        yt_mod._api(tok, "/youtube/v3/videos?part=localizations",
                    {"id": vid, "localizations": {lang: tr}}, method="PUT")

    def _set_default_language():
        """Re-commit the snippet with `defaultLanguage` set.

        The PUT is issued even when the field already reads "en": empirically that update is what
        makes the API accept localised details (`defaultLanguageNotSet` persists on videos whose
        snippet was never written after upload, and re-reading the snippet is not enough — a
        no-op rewrite is).
        """
        try:
            cur_sn = yt_mod._api(tok, f"/youtube/v3/videos?part=snippet&id={vid}")["items"][0]["snippet"]
            body = {"title": cur_sn["title"], "description": cur_sn["description"],
                    "categoryId": cur_sn.get("categoryId", "27"),
                    "defaultLanguage": cur_sn.get("defaultLanguage") or "en"}
            if cur_sn.get("tags"):
                body["tags"] = cur_sn["tags"]
            yt_mod._api(tok, "/youtube/v3/videos?part=snippet", {"id": vid, "snippet": body},
                        method="PUT")
            return True
        except Exception as e:  # noqa: BLE001
            _log(f"[i18n] defaultLanguage could not be set ({str(e)[:110]})")
            return False

    try:
        _write()
    except Exception as e:  # noqa: BLE001
        if "defaultLanguage" not in str(e):
            return False, f"write failed: {str(e)[:120]}"
        # The snippet change needs a few seconds to propagate before YouTube accepts localised
        # details — a single immediate retry still 400s. Back off and try again.
        _set_default_language()
        last = str(e)[:120]
        for wait in (4, 8, 12):
            time.sleep(wait)
            try:
                _write()
                last = ""
                break
            except Exception as e2:  # noqa: BLE001
                last = str(e2)[:120]
        if last:
            return False, f"write failed after setting defaultLanguage: {last}"

    # read back — the write is only real when the API says so, and the read LAGS the write by
    # seconds, so compare the TITLE we wrote (not merely the key): a stale track that still holds
    # the previous title would otherwise be reported as a success and then block every later
    # attempt behind the idempotency check.
    want = tr["title"]
    last_seen = ""
    for _ in range(5):
        try:
            back = yt_mod._api(tok, f"/youtube/v3/videos?part=localizations&id={vid}")
        except Exception as e:  # noqa: BLE001
            _log(f"[i18n] read-back failed ({str(e)[:100]})")
            return True, "written (read-back unavailable)"
        loc = (back.get("items") or [{}])[0].get("localizations", {})
        last_seen = (loc.get(lang) or {}).get("title", "")
        if last_seen == want:
            return True, f"{lang} title: {want[:60]!r}"
        time.sleep(3)
    if last_seen:
        return False, f"read-back still shows {last_seen[:60]!r} (wrote {want[:60]!r})"
    return False, "write did not appear on read-back"
