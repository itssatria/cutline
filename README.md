# ✂️ Cutline - Image Sequence Manager

> **Clean cuts. Clear story.** 
> A powerful, GPU-accelerated local desktop app for cleaning up image folders and visually sorting them into coherent storyboards.

Cutline is built with Python and Gradio, designed specifically for directors, 3D artists, and photographers who deal with massive image sequences or render outputs. It combines lightning-fast CPU deduplication with advanced AI vision models and LLMs to organize your shots intelligently.

---

## ✨ Key Features

### 1. Smart Duplicate Detection (CPU Fast)
Scans folders (and subfolders) to find redundant files so you can keep your workspace clean.
* **Exact Copies:** Uses strict SHA-256 hashing to find identical file bytes.
* **Near-Duplicates:** Uses 256-bit fingerprinting (`dHash`) with an adjustable tolerance slider. It catches resized, recompressed, or lightly color-edited photos.
* **Smart Keep:** Automatically marks the highest-resolution file to keep, using file size as a tie-breaker.

### 2. AI Storyboard Sorting (GPU Accelerated)
Sorts your images visually, completely offline.
* **Deep Understanding:** Uses local vision models (like DINOv2 or CLIP) to extract structural vectors from your images, combined with OpenCV color histograms to maintain lighting continuity.
* **Optimized Sequencing:** Treats sorting as a Traveling Salesperson Problem (TSP), using nearest-neighbor search with a 2-opt refinement pass to ensure each shot sits next to its most visually similar neighbor.
* **First-Use Auto-Download:** Automatically fetches the required model weights (e.g., `dinov2-base`) and caches them locally in `~/.cutline/models`.

### 3. Narrative LLM Pass (Optional)
After the visual sort, optionally send downscaled thumbnails to an LLM to reorder them for narrative sense (e.g., placing establishing shots before close-ups).
* **Supported Cloud Engines:** Gemini, Claude, OpenAI, OpenRouter.
* **Supported Local Engines:** Ollama (e.g., LLaVA) for completely free, private narrative sorting.

### 4. 🔒 Privacy First (NSFW Killswitch)
If you are working with sensitive or NSFW content, simply tick the **"My photos contain NSFW content"** checkbox. This immediately disables all external cloud APIs, ensuring your images never leave your local machine. You can continue to use Local Vision Models and Ollama.

---

## 🛠️ Installation

### Prerequisites
* Python 3.10 or higher.
* Git.
* An NVIDIA GPU (like an RTX 3080) is highly recommended for faster Vision Model processing, though it will fall back to CPU if necessary.

### Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/cutline.git
   cd cutline
   ```

2. **Create a virtual environment (Recommended):**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Mac/Linux:
   source venv/bin/activate
   ```

3. **Install standard dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install PyTorch with CUDA (Optional but Highly Recommended):**
   To fully utilize your RTX 3080 or other NVIDIA GPU, install the CUDA version of PyTorch. 
   *(Check [PyTorch's official site](https://pytorch.org/get-started/locally/) for the command matching your CUDA version).*
   ```bash
   pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

---

## 🚀 Usage

Start the application by running:
```bash
python app.py
```
This will open the Gradio interface in your default web browser (usually at `http://127.0.0.1:7860`).

### Tab 1: Duplicates
1. Paste the absolute path of your image folder.
2. Adjust the **Similarity tolerance** (0 for exact matches only, 10-20 for resizes/recompression).
3. Click **Scan for duplicates**.
4. Review the visual groups. The app automatically flags lower-quality duplicates for deletion. 

### Tab 2: Storyboard
1. Paste your folder path.
2. Select your **Sorting Engine**:
   * **Local only (CLIP/DINO):** Runs offline using your GPU. Best for visual flow and structural matching.
   * **Cloud LLMs (Gemini, Claude, etc.):** Requires an API key. Reorders images based on narrative logic.
3. Check the **NSFW** box if necessary to protect your privacy.
4. Click **Sort as storyboard**.
5. Use the **Reverse**, **Move left**, and **Move right** buttons to manually tweak the flow.
6. Choose how to save your sequence (Copy to a new folder or Rename originals) and click **Apply order**.

---

## 📁 Model Cache Directory
Vision models are downloaded on their first use. By default, they are stored in `~/.cutline/models`. 
If you want to change this location (e.g., to put them on a larger secondary drive), set the `CUTLINE_MODELS` environment variable before running the app:
```bash
set CUTLINE_MODELS=D:\AI_Models\Cutline
python app.py
```

## 📜 License
This project is licensed under the MIT License - see the LICENSE file for details.
