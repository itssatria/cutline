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
MAX_IMAGES = {OLLAMA: 24}
DEFAULT_MAX_IMAGES = 100

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


def _ollama(_key, model, imgs, prompt):
    r = _post("http://127.0.0.1:11434/api/chat", {},
              {"model": model, "stream": False,
               "messages": [{"role": "user", "images": imgs,
                             "content": "The images are numbered 0 to %d in the order given. %s" % (len(imgs) - 1, prompt)}]})
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


def refine(engine, api_key, model_name, paths, order, progress=lambda f, m: None):
    """Ask a vision model to improve `order`. Returns the new order (list of indexes into paths)."""
    if engine == LOCAL_ONLY:
        return order
    n = len(order)
    limit = MAX_IMAGES.get(engine, DEFAULT_MAX_IMAGES)
    if n > limit:
        raise ValueError(f"{engine} handles up to {limit} images per run (you have {n}). "
                         "Use Local only, or sort a smaller folder.")
    key = (api_key or "").strip() or os.environ.get(ENV_KEYS.get(engine, ""), "")
    if engine != OLLAMA and not key:
        raise ValueError(f"Enter an API key for {engine}.")
    model = (model_name or "").strip() or DEFAULT_MODELS[engine]
    imgs = []
    for k, i in enumerate(order):
        progress(0.1 + 0.5 * k / n, "Preparing pictures")
        imgs.append(_jpeg_b64(paths[i]))
    progress(0.7, f"Asking {engine} to arrange the story...")
    text = CALLERS[engine](key, model, imgs, PROMPT.format(n=n, last=n - 1))
    return [order[k] for k in parse_order(text, n)]
