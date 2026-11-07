# Cutline

**Clean cuts. Clear story.**

A local Windows app (Gradio) that cleans up a folder of images and arranges them like a storyboard.

1. **Duplicates**: finds exact and near-duplicate photos, keeps the best copy, and sends the rest to the Recycle Bin.
2. **Storyboard**: sorts images by what they *show*, not by file name or date, so the sequence flows from first shot to last.

Everything runs on your PC. Cloud AI is optional and off by default.

## Quick start (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/) (tick "Add Python to PATH").
2. *(NVIDIA GPU users)* Install the CUDA build of PyTorch first. Get the exact command from <https://pytorch.org>.
3. Double-click **`run.bat`**. The first run creates a virtual environment and installs packages (a few minutes).
4. Your browser opens at `http://127.0.0.1:7860`.

Manual install:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## How to use

**1 · Duplicates**
1. Paste the folder path, set the similarity tolerance, click **Scan**.
2. Each group shows thumbnails. The highest-resolution copy is marked KEEP, the others DELETE.
3. Untick any file you want to keep, then click **Move selected files to Recycle Bin**.
   Cutline never deletes permanently and refuses to remove every copy in a group.

**2 · Storyboard**
1. Paste the folder path and pick a vision model. It downloads automatically the first time you use it, with a progress bar, then is cached in `~/.cutline/models` (change with the `CUTLINE_MODELS` environment variable).
2. Pick a sorting engine and click **Sort as storyboard**.
3. The local sort cannot know which end is the start. Use **Reverse**, or click a frame and use **Move left / Move right**.
4. **Apply order** either copies the images into `_storyboard/` as `001_`, `002_`, ... or renames the originals.

The top-right **Light / Dark** button switches the theme.

## Sorting engines

| Engine | Needs | Leaves your PC? |
|---|---|---|
| **Local only (CLIP, offline)** | nothing | No |
| **Ollama (local vision model)** | [Ollama](https://ollama.com) running, plus a vision model, e.g. `ollama pull qwen2.5vl:7b` | No |
| **Gemini** | API key from Google AI Studio (has a free tier) | Yes |
| **OpenAI** | API key (billed separately from ChatGPT subscriptions) | Yes |
| **Claude** | Anthropic API key | Yes |
| **OpenRouter** | one key, many models | Yes |

* Local mode orders images by visual similarity (smooth flow). The AI engines look at the pictures and also fix story logic, such as establishing shots before close-ups.
* Cloud engines receive 512 px copies of your images, up to 100 per run (Ollama: 24).
* Keys are used for the request only; they are never saved or logged. You can prefill them with the environment variables `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY`.
* Model names change often, so each engine has an editable **Model name** field. If a default is outdated, type a current one. Check each provider's terms and data policy, especially for free tiers.

### NSFW mode

Tick **My photos contain NSFW content** to disable every cloud engine. Only *Local* and *Ollama* remain, so nothing leaves your PC. Duplicate detection and CLIP sorting always run locally and work on any content; CLIP-style models do not filter images.

## Vision models

| Model | Download (approx.) | Notes |
|---|---|---|
| CLIP ViT-B/32 (default) | 0.6 GB | Fast, good all-rounder |
| CLIP ViT-L/14 | 1.7 GB | More precise, slower |
| SigLIP ViT-B/16 | 0.8 GB | Strong alternative |
| DINOv2 base | 0.4 GB | Best for shots of the same scene (renders, camera moves). Requires `pip install transformers` |

Sizes are estimates.

## How it works

* **Duplicates:** SHA-256 for exact copies; a 256-bit difference hash (brightness structure) plus a colour check for near-duplicates such as resized or recompressed versions. The tolerance slider sets how many hash bits may differ. Heavy crops and rotations can be missed.
* **Storyboard:** the vision model turns each image into a vector; an 8×8 colour thumbnail adds lighting/colour continuity. Cutline then searches for the shortest path through all images (nearest-neighbour from many starts, improved with 2-opt), so every shot sits beside its most similar neighbours.

## Project layout

```
app.py              Gradio interface
cutline/
  dedupe.py         duplicate detection
  ordering.py       storyboard ordering
  models.py         vision models: first-use download with progress
  providers.py      optional AI engines (Gemini, OpenAI, Claude, OpenRouter, Ollama)
  files.py          listing, thumbnails, Recycle Bin, applying the order
tests/test_core.py  core tests (no GPU or network needed)
run.bat             Windows launcher
```

Run the tests with `pip install pytest` then `python -m pytest`.

## Known limitations

* The local sort follows visual similarity; it does not understand your intended story. Use an AI engine for narrative logic, and fine-tune by hand.
* The Gradio interface and the model/AI downloads were not exercised in the build environment. The core logic (duplicates, ordering, file operations, reply parsing) is tested, so expect to fix small issues on first run and please open an issue.
* Large folders: the AI engines cap the number of images (see above); local sorting of thousands of images works but gets slower.

## License

MIT. See `LICENSE` (replace `<your name>` with your name before publishing).
