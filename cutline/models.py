"""
Cutline model manager.

Downloads the chosen vision model the first time it is used (with progress), caches it under
~/.cutline/models, and returns an `embed(images) -> np.ndarray` function for the sorter.

Progress callback signature: progress(fraction_0_to_1, message_str)
"""
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CACHE = Path(os.environ.get("CUTLINE_MODELS", Path.home() / ".cutline" / "models"))


@dataclass(frozen=True)
class VisionModel:
    key: str
    label: str
    repo: str          # Hugging Face repo id
    kind: str          # "open_clip" or "dino"
    approx_gb: float   # rough download size shown before downloading
    note: str


MODELS = {m.key: m for m in [
    VisionModel("clip-b32", "CLIP ViT-B/32 (fast, default)", "laion/CLIP-ViT-B-32-laion2B-s34B-b79K",
                "open_clip", 0.6, "Good all-round speed/quality."),
    VisionModel("clip-l14", "CLIP ViT-L/14 (better)", "laion/CLIP-ViT-L-14-laion2B-s32B-b82K",
                "open_clip", 1.7, "Understands scenes more precisely; slower."),
    VisionModel("siglip-b16", "SigLIP ViT-B/16", "timm/ViT-B-16-SigLIP",
                "open_clip", 0.8, "Strong alternative to CLIP."),
    VisionModel("dinov2-base", "DINOv2 base (same-scene structure)", "facebook/dinov2-base",
                "dino", 0.4, "Best for shots from one scene (renders, camera moves). Needs `transformers`."),
]}
DEFAULT_MODEL = "clip-b32"


def _marker(m: VisionModel) -> Path:
    return CACHE / f"{m.key}.ok"


def is_downloaded(m: VisionModel) -> bool:
    """True only if a previous download finished completely."""
    try:
        from huggingface_hub import snapshot_download
        if not _marker(m).exists():
            return False
        snapshot_download(m.repo, cache_dir=CACHE, local_files_only=True)
        return True
    except Exception:
        return False


def choices():
    """Dropdown entries: (label shown to the user, model key)."""
    return [(f"{m.label} · " + ("ready" if is_downloaded(m) else f"~{m.approx_gb} GB"), m.key)
            for m in MODELS.values()]


def _patterns(m: VisionModel):
    """Fetch only one copy of the weights (repos often hold several formats)."""
    from huggingface_hub import HfApi
    files = set(HfApi().list_repo_files(m.repo))
    if m.kind == "dino":
        return ["*.json", "model.safetensors" if "model.safetensors" in files else "pytorch_model.bin"]
    weight = "open_clip_model.safetensors" if "open_clip_model.safetensors" in files else "open_clip_pytorch_model.bin"
    return [weight, "open_clip_config.json", "*.txt", "tokenizer*.json", "special_tokens_map.json", "vocab*"]


def download(m: VisionModel, progress=None):
    """Download with one combined progress bar (bytes across all files)."""
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm

    state = {"done": 0, "total": 0}

    def report():
        if progress and state["total"]:
            f = min(state["done"] / state["total"], 1.0)
            progress(f, f"Downloading {m.label}: {state['done'] / 1e6:.0f} / {state['total'] / 1e6:.0f} MB")

    class ByteBar(tqdm):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._is_bytes = self.unit == "B"
            if self._is_bytes and self.total:
                state["total"] += self.total

        def update(self, n=1):
            r = super().update(n)
            if self._is_bytes and n:
                state["done"] += n
                report()
            return r

    CACHE.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0.0, f"Preparing download of {m.label} (~{m.approx_gb} GB, first use only)...")
    snapshot_download(m.repo, cache_dir=CACHE, tqdm_class=ByteBar, allow_patterns=_patterns(m))
    _marker(m).write_text("ok")
    if progress:
        progress(1.0, f"{m.label} ready.")


def load(key: str = DEFAULT_MODEL, progress=None):
    """Return embed(list_of_PIL_RGB_images) -> L2-normalised float32 array. Downloads on first use."""
    import torch

    m = MODELS[key]
    if not is_downloaded(m):
        download(m, progress)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    if m.kind == "open_clip":
        import open_clip
        model, _, preprocess = open_clip.create_model_and_transforms(f"hf-hub:{m.repo}", cache_dir=str(CACHE))
        model.eval().to(device)

        @torch.no_grad()
        def embed(images):
            x = torch.stack([preprocess(im) for im in images]).to(device)
            return torch.nn.functional.normalize(model.encode_image(x), dim=-1).cpu().numpy().astype(np.float32)
    else:
        from transformers import AutoImageProcessor, AutoModel
        proc = AutoImageProcessor.from_pretrained(m.repo, cache_dir=str(CACHE))
        model = AutoModel.from_pretrained(m.repo, cache_dir=str(CACHE)).eval().to(device)

        @torch.no_grad()
        def embed(images):
            x = proc(images=images, return_tensors="pt").to(device)
            f = model(**x).last_hidden_state[:, 0]
            return torch.nn.functional.normalize(f, dim=-1).cpu().numpy().astype(np.float32)

    return embed
