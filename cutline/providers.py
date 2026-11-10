"""Optional AI pass: a vision model looks at the pictures and fixes the narrative order.

No SDKs needed - plain HTTPS via `requests`. API keys are used for the request only,
never saved to disk or logged.
"""
import base64
import io
import json
import os
import re

import requests

from . import ordering
from .files import load_rgb

LOCAL_ONLY = "Local only (CLIP, offline)"
OLLAMA = "Ollama (local vision model)"
CLOUD = ["Gemini", "OpenAI", "Claude", "OpenRouter"]
ENGINES = [LOCAL_ONLY, *CLOUD, OLLAMA]
PRIVATE_ENGINES = [LOCAL_ONLY, OLLAMA]          # nothing leaves the PC

# Editable in the UI because model names change often.
DEFAULT_MODELS = {
    "Gemini": "gemini-2.5-flash",
    "OpenAI": "gpt-4o",
    "Claude": "claude-sonnet-5-5",
    "OpenRouter": "google/gemini-2.5-flash",
    OLLAMA: "qwen2.5vl:7b",
}
ENV_KEYS = {"Gemini": "GEMINI_API_KEY", "OpenAI": "OPENAI_API_KEY",
            "Claude": "ANTHROPIC_API_KEY", "OpenRouter": "OPENROUTER_API_KEY"}
# Largest folder sent to the model in ONE request. Bigger folders are handled in two steps (describe the images a
# few at a time, then order the descriptions as text), so there is no limit on the number of images.
DIRECT_LIMIT = {OLLAMA: 12}
DEFAULT_DIRECT_LIMIT = 100
DESCRIBE_CHUNK = {OLLAMA: 4}
DEFAULT_DESCRIBE_CHUNK = 12

PROMPT = ("These {n} images are shots for ONE storyboard, currently in a rough visual-similarity order. "
          "Reorder them so the sequence tells a coherent story from first shot to last: establishing shots "
          "before close-ups, cause before effect, continuity of subject, location and lighting, a clear "
          "beginning and ending. Reply with ONLY a JSON array containing every image number 0-{last} "
          "exactly once, in the new order.")


def _jpeg_b64(path):
    buf = io.BytesIO()
    load_rgb(path, 512).save(buf, "JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode()


def _post(url, headers, payload):
    r = requests.post(url, headers=headers, json=payload, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"{url.split('/')[2]} returned {r.status_code}: {r.text[:300]}")
    return r.json()


def _claude(key, model, imgs, prompt):
    content = []
    for k, b in enumerate(imgs):
        content += [{"type": "text", "text": f"Image {k}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}}]
    content.append({"type": "text", "text": prompt})
    r = _post("https://api.anthropic.com/v1/messages",
              {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
              {"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": content}]})
    return "".join(b.get("text", "") for b in r["content"])


def _openai_like(url, key, model, imgs, prompt):
    content = []
    for k, b in enumerate(imgs):
        content += [{"type": "text", "text": f"Image {k}:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}}]
    content.append({"type": "text", "text": prompt})
    r = _post(url, {"Authorization": f"Bearer {key}"},
              {"model": model, "messages": [{"role": "user", "content": content}]})
    return r["choices"][0]["message"]["content"]


def _gemini(key, model, imgs, prompt):
    parts = []
    for k, b in enumerate(imgs):
        parts += [{"text": f"Image {k}:"}, {"inline_data": {"mime_type": "image/jpeg", "data": b}}]
    parts.append({"text": prompt})
    r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
              {"x-goog-api-key": key}, {"contents": [{"parts": parts}]})
    return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])


def ollama_base():
    """Ollama address: honours the OLLAMA_HOST environment variable, default http://127.0.0.1:11434."""
    h = os.environ.get("OLLAMA_HOST", "").strip() or "127.0.0.1:11434"
    if not h.startswith("http"):
        h = "http://" + h
    h = h.replace("0.0.0.0", "127.0.0.1").rstrip("/")
    if re.match(r"^http://[^/:]+$", h):
        h += ":11434"
    return h


def list_ollama_models(timeout=4):
    """Models installed in the local Ollama, as [(name, is_vision)] with is_vision True / False / None (unknown).
    Raises ConnectionError if Ollama is not reachable."""
    base = ollama_base()
    try:
        r = requests.get(base + "/api/tags", timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Could not reach Ollama at {base}. Is it running?") from e
    out = []
    for m in r.json().get("models", []):
        name = m.get("name") or m.get("model")
        if not name:
            continue
        vision = None
        try:
            info = requests.post(base + "/api/show", json={"model": name, "name": name}, timeout=timeout).json()
            caps = info.get("capabilities")
            if caps is not None:
                vision = "vision" in caps
            elif "clip" in (info.get("details", {}).get("families") or []) or \
                    any(".vision." in k for k in (info.get("model_info") or {})):
                vision = True
        except Exception:
            pass
        out.append((name, vision))
    return out


def _ollama(_key, model, imgs, prompt):
    base = ollama_base()
    content = prompt
    if imgs:
        content = "The images are numbered 0 to %d in the order given. %s" % (len(imgs) - 1, prompt)
    msg = {"role": "user", "content": content}
    if imgs:
        msg["images"] = imgs
    ctx = int(os.environ.get("CUTLINE_OLLAMA_CTX", "8192"))       # Ollama's default window is small
    try:
        r = _post(base + "/api/chat", {}, {"model": model, "stream": False, "messages": [msg],
                                            "options": {"num_ctx": ctx}})
    except requests.ConnectionError as e:
        raise RuntimeError(f"Could not reach Ollama at {base}. Is it running?") from e
    except RuntimeError as e:
        if " 404" in str(e):
            raise RuntimeError(f"Ollama does not have the model '{model}'. Run: ollama pull {model}") from e
        raise
    return r["message"]["content"]


CALLERS = {
    "Claude": _claude,
    "Gemini": _gemini,
    "OpenAI": lambda k, m, i, p: _openai_like("https://api.openai.com/v1/chat/completions", k, m, i, p),
    "OpenRouter": lambda k, m, i, p: _openai_like("https://openrouter.ai/api/v1/chat/completions", k, m, i, p),
    OLLAMA: _ollama,
}


def parse_order(text, n):
    """Pull a JSON list out of the reply; repair it if the model dropped or repeated numbers."""
    m = re.search(r"\[[\d,\s]*\]", text)
    if not m:
        raise ValueError("The AI did not return an order. Try again or use another engine.")
    seen, out = set(), []
    for v in json.loads(m.group(0)):
        if isinstance(v, int) and 0 <= v < n and v not in seen:
            seen.add(v)
            out.append(v)
    out += [i for i in range(n) if i not in seen]
    return out


def _resolve(engine, api_key, model_name):
    key = (api_key or "").strip() or os.environ.get(ENV_KEYS.get(engine, ""), "")
    if engine != OLLAMA and not key:
        raise ValueError(f"Enter an API key for {engine}.")
    return key, (model_name or "").strip() or DEFAULT_MODELS[engine]


def _extras(story_prompt, locked):
    out = ""
    if (story_prompt or "").strip():
        out += ('\nThe user describes the story they want: "%s". Let it guide the order.'
                % story_prompt.strip()[:1500].replace('"', "'"))
    if locked:
        out += ("\nThese shot numbers are pinned and must keep exactly their own number: %s. "
                "Arrange all the other shots around them." % sorted(locked))
    return out


DESCRIBE_PROMPT = ("Describe each of the {m} images (numbered 0 to {last}) in one short sentence of at most 20 words: "
                   "subject, setting, action and mood. Reply with ONLY a JSON array of exactly {m} strings, in image order.")
TEXT_ORDER_PROMPT = ("Below are short descriptions of {n} shots for ONE storyboard, numbered 0 to {last}, currently in a "
                     "rough visual-similarity order:\n{lines}\nReorder the shots so the sequence tells a coherent story "
                     "from first shot to last: establishing shots before close-ups, cause before effect, continuity of "
                     "subject, location and lighting, a clear beginning and ending. Reply with ONLY a JSON array "
                     "containing every number 0-{last} exactly once, in the new order.")


def _refine_by_captions(engine, key, model, paths, order, progress, story_prompt, locked):
    """Any number of images: describe them a few at a time, then order the descriptions as text."""
    n = len(order)
    chunk = DESCRIBE_CHUNK.get(engine, DEFAULT_DESCRIBE_CHUNK)
    caps = []
    for s in range(0, n, chunk):
        part = order[s:s + chunk]
        progress(0.05 + 0.8 * s / n, f"Describing images ({s + 1}-{s + len(part)} of {n})")
        imgs = [_jpeg_b64(paths[i]) for i in part]
        prompt = DESCRIBE_PROMPT.format(m=len(part), last=len(part) - 1)
        caps += parse_captions(CALLERS[engine](key, model, imgs, prompt), len(part))
    progress(0.9, f"Asking {engine} to arrange the story from the descriptions...")
    lines = "\n".join(f"{k}: {c or '(no description)'}" for k, c in enumerate(caps))
    prompt = TEXT_ORDER_PROMPT.format(n=n, last=n - 1, lines=lines) + _extras(story_prompt, locked)
    new = [order[k] for k in parse_order(CALLERS[engine](key, model, [], prompt), n)]
    return ordering.enforce_locks(new, locked or {})


def refine(engine, api_key, model_name, paths, order, progress=lambda f, m: None, story_prompt="", locked=None):
    """Ask a vision model to improve `order`. Returns the new order (list of indexes into paths).
    story_prompt: what story the user wants. locked: {position: image_index} frames that must not move.
    Small folders are sent in one request; bigger ones are handled in two steps, so there is no size limit."""
    if engine == LOCAL_ONLY:
        return order
    n = len(order)
    key, model = _resolve(engine, api_key, model_name)
    if n > DIRECT_LIMIT.get(engine, DEFAULT_DIRECT_LIMIT):
        return _refine_by_captions(engine, key, model, paths, order, progress, story_prompt, locked)
    prompt = PROMPT.format(n=n, last=n - 1) + _extras(story_prompt, locked)
    imgs = []
    for k, i in enumerate(order):
        progress(0.1 + 0.5 * k / n, "Preparing pictures")
        imgs.append(_jpeg_b64(paths[i]))
    progress(0.7, f"Asking {engine} to arrange the story...")
    new = [order[k] for k in parse_order(CALLERS[engine](key, model, imgs, prompt), n)]
    return ordering.enforce_locks(new, locked or {})


CAPTION_PROMPT = ("You are writing the script for an animatic. The {m} images below are consecutive shots, numbered "
                  "0 to {last}. {story}{context}For each image write ONE or TWO short sentences saying what happens "
                  "in that shot and how it moves the story forward (present tense, plain language). "
                  "Reply with ONLY a JSON array of exactly {m} strings, in image order.")


def parse_captions(text, m):
    """Pull a list of strings out of the reply; pad / trim to m items."""
    s, e = text.find("["), text.rfind("]")
    caps = None
    if s != -1 and e > s:
        try:
            v = json.loads(text[s:e + 1])
            if isinstance(v, list):
                caps = [str(x).strip() for x in v]
        except ValueError:
            pass
    if caps is None:                                   # fall back to numbered / plain lines
        lines = [re.sub(r"^\s*(?:image\s*)?\d+[.):\-]\s*", "", ln).strip() for ln in text.splitlines()]
        caps = [ln for ln in lines if ln]
    if not caps:
        raise ValueError("The AI did not return any story text. Try again or use another engine.")
    return (caps + [""] * m)[:m]


def write_story(engine, api_key, model_name, paths, order, texts, targets, story_prompt="",
                progress=lambda f, m: None):
    """Write a short story caption for each target image. Returns {image_index: caption}."""
    if engine == LOCAL_ONLY:
        raise ValueError("Pick an AI engine (Ollama, Gemini, ...) to write story text.")
    key, model = _resolve(engine, api_key, model_name)
    chunk = 8 if engine == OLLAMA else 12
    wanted = set(targets)
    seq = [i for i in order if i in wanted]
    texts, new = dict(texts or {}), {}
    story = ('The user wants this story: "%s". ' % story_prompt.strip()[:1500].replace('"', "'")
             if (story_prompt or "").strip() else "")
    pos_of = {img: k for k, img in enumerate(order)}
    for s in range(0, len(seq), chunk):
        part = seq[s:s + chunk]
        progress(0.05 + 0.9 * s / max(len(seq), 1), f"Writing story text ({s + 1}-{s + len(part)} of {len(seq)})")
        first = pos_of[part[0]]
        before = [texts.get(order[k], "").strip() for k in range(max(0, first - 6), first)]
        before = [c for c in before if c]
        context = ("Story so far: " + " ".join(before) + " ") if before else ""
        prompt = CAPTION_PROMPT.format(m=len(part), last=len(part) - 1, story=story, context=context)
        imgs = [_jpeg_b64(paths[i]) for i in part]
        caps = parse_captions(CALLERS[engine](key, model, imgs, prompt), len(part))
        for i, c in zip(part, caps):
            new[i] = texts[i] = c
    progress(1.0, "Done")
    return new
