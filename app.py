import gradio as gr
import os
import torch
import threading
from fastapi import FastAPI
import uvicorn
from dedupe import find_duplicates
from sort import tsp_nearest_neighbor_2opt, get_color_histogram, apply_action, apply_final_action
from models import load_vision_model, extract_features, MODEL_CONFIGS
from PIL import Image

api_app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api_app.get("/browse_folder")
def open_native_dialog():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_path = filedialog.askdirectory(title="Select Folder")
    root.destroy()
    return {"path": folder_path}

def run_api():
    uvicorn.run(api_app, host="127.0.0.1", port=8001, log_level="error")

api_thread = threading.Thread(target=run_api, daemon=True)
api_thread.start()

css = '''
.sidebar { background-color: var(--background-fill-secondary); padding: 20px; border-radius: 10px; }
.header-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 20px; margin-bottom: 20px; border-bottom: 1px solid var(--border-color-primary); }
.brand-title { font-size: 24px; font-weight: bold; }
.brand-subtitle { font-size: 14px; font-weight: normal; color: var(--body-text-color-subdued); margin-left: 10px; }
.header-right { font-size: 12px; color: var(--body-text-color-subdued); display: flex; gap: 15px; align-items: center;}
.primary-btn { background-color: #d84315 !important; color: white !important; font-weight: bold !important; border: none !important; margin-top: 10px !important; }
.black-btn { background-color: #1a1a1a !important; color: white !important; font-weight: bold !important; margin-top: 10px !important;}
.dark .black-btn { background-color: #ffffff !important; color: black !important; }
.group-card { border: 1px solid var(--border-color-primary); border-radius: 8px; padding: 10px; }
.theme-toggle { display: inline-flex; border: 1px solid var(--border-color-primary); border-radius: 20px; padding: 2px; overflow: hidden; background: var(--background-fill-secondary); }
.theme-btn { border: none !important; background: transparent !important; padding: 4px 12px !important; font-size: 12px !important; cursor: pointer; color: var(--body-text-color) !important; box-shadow: none !important; margin: 0 !important; }
.theme-btn:hover { background: transparent !important; }
'''

js_funcs = '''
function customScripts() {
    window.toggleTheme = function(mode) {
        const isDark = document.querySelector('body').classList.contains('dark');
        if (mode === 'dark' && !isDark) {
            document.querySelector('body').classList.add('dark');
            document.querySelector('#btn-dark').style.background = '#1a1a1a';
            document.querySelector('#btn-dark').style.color = 'white';
            document.querySelector('#btn-dark').style.borderRadius = '16px';
            document.querySelector('#btn-light').style.background = 'transparent';
            document.querySelector('#btn-light').style.color = 'var(--body-text-color)';
        } else if (mode === 'light' && isDark) {
            document.querySelector('body').classList.remove('dark');
            document.querySelector('#btn-light').style.background = '#1a1a1a';
            document.querySelector('#btn-light').style.color = 'white';
            document.querySelector('#btn-light').style.borderRadius = '16px';
            document.querySelector('#btn-dark').style.background = 'transparent';
            document.querySelector('#btn-dark').style.color = 'var(--body-text-color)';
        }
    };
}
'''

fetch_folder_js = '''
async () => {
    try {
        const res = await fetch("http://127.0.0.1:8001/browse_folder");
        const data = await res.json();
        if(data.path) {
            return data.path;
        }
    } catch(e) {
        console.error("Make sure uvicorn API thread is running", e);
    }
    return "";
}
'''

def get_gpu_name():
    if torch.cuda.is_available():
        return torch.cuda.get_device_name(0)
    return "CPU"

def handle_dedupe(folder_path, tolerance):
    if not folder_path or not os.path.exists(folder_path):
        return "Folder not found. Please paste a valid path or browse.", []
    dupes, kept = find_duplicates(folder_path, tolerance)
    
    gallery_items = []
    for p in kept:
        gallery_items.append((p, f"Keep: {os.path.basename(p)}"))
    for p in dupes:
        gallery_items.append((p, f"Delete: {os.path.basename(p)}"))
        
    return f"Found **{len(dupes)} groups** · {len(dupes)} files marked Delete. Click a card to toggle Keep / Delete.", gallery_items

def handle_sort(folder_path, vision_model_key, engine, api_key, is_nsfw, progress=gr.Progress(track_tqdm=True)):
    if not folder_path or not os.path.exists(folder_path):
        return [], "Folder not found. Please paste a valid path or browse."
        
    images = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    if not images:
        return [], "No images found."
        
    def prog_callback(val, desc):
        progress(val, desc=desc)
        
    processor, model, device, model_type = load_vision_model(vision_model_key, progress_callback=prog_callback)
    
    features = []
    histograms = []
    
    for img_path in progress.tqdm(images, desc="Extracting features..."):
        with Image.open(img_path).convert("RGB") as img:
            feat = extract_features(img, processor, model, device, model_type)
            features.append(feat)
        histograms.append(get_color_histogram(img_path))
        
    from sort import compute_distance_matrix
    dist_matrix = compute_distance_matrix(features, histograms)
    path_indices = tsp_nearest_neighbor_2opt(dist_matrix)
    
    sorted_images = [images[i] for i in path_indices]
    
    gallery_items = [(img, f"{i+1} — {os.path.basename(img)}") for i, img in enumerate(sorted_images)]
    return gallery_items, f"{len(sorted_images)} images sorted using {MODEL_CONFIGS.get(vision_model_key, {}).get('label', vision_model_key)} · drag cards to reorder, or use buttons."

with gr.Blocks(theme=gr.themes.Default(primary_hue="orange"), css=css, head=f"<script>{js_funcs}</script>", title="Cutline") as app:
    gpu_name = get_gpu_name()
    
    # Track selected index in gallery
    selected_index_state = gr.State(None)
    
    gr.HTML(f'''
    <div class="header-bar">
        <div class="brand-title">Cutline <span class="brand-subtitle">Clean cuts. Clear story.</span></div>
        <div class="header-right">
            <span>Local • {gpu_name} • 127.0.0.1:7860</span>
            <div class="theme-toggle">
                <button id="btn-light" class="theme-btn" onclick="toggleTheme('light')" style="background: #1a1a1a; color: white; border-radius: 16px;">Light</button>
                <button id="btn-dark" class="theme-btn" onclick="toggleTheme('dark')">Dark</button>
            </div>
        </div>
    </div>
    ''')
    
    with gr.Tabs():
        with gr.Tab("1 · Duplicates"):
            with gr.Row():
                with gr.Column(scale=1, min_width=320, elem_classes="sidebar"):
                    gr.Markdown("### Image folder")
                    with gr.Row():
                        dup_folder = gr.Textbox(label="", placeholder="D:/Shots/Project01", show_label=False, scale=4)
                        dup_browse_btn = gr.Button("Browse", scale=1)
                    
                    dup_sub = gr.Checkbox(label="Include subfolders", value=True)
                    
                    gr.Markdown("### Similarity tolerance: 10")
                    dup_tol = gr.Slider(0, 40, value=10, label="", show_label=False)
                    gr.HTML('<div style="display:flex; justify-content:space-between; font-size:12px; color:gray; margin-top:-10px; margin-bottom:10px;"><span>0 exact only</span><span>40 very loose</span></div>')
                    
                    scan_btn = gr.Button("Scan for duplicates", variant="primary", elem_classes="primary-btn")
                    
                    gr.HTML('<hr style="margin-top: 20px; margin-bottom: 20px; border-color: var(--border-color-primary);"/>')
                    dup_status = gr.Markdown("Found **0 groups** · 0 files marked Delete. Click a card to toggle Keep / Delete.", elem_classes="status-text")
                
                with gr.Column(scale=3):
                    dup_gallery = gr.Gallery(label="", show_label=False, columns=3, allow_preview=False, object_fit="contain")
                    
                    dup_browse_btn.click(
                        None, 
                        inputs=None, 
                        outputs=[dup_folder], 
                        js=fetch_folder_js
                    )
                    
                    scan_btn.click(handle_dedupe, inputs=[dup_folder, dup_tol], outputs=[dup_status, dup_gallery])
                    
        with gr.Tab("2 · Storyboard"):
            with gr.Row():
                with gr.Column(scale=1, min_width=320, elem_classes="sidebar"):
                    gr.Markdown("### Image folder")
                    with gr.Row():
                        sb_folder = gr.Textbox(label="", placeholder="D:/Shots/Project01", show_label=False, scale=4)
                        sb_browse_btn = gr.Button("Browse", scale=1)
                        
                    gr.Markdown("### Vision Model (Local AI)")
                    model_choices = [(cfg["label"], key) for key, cfg in MODEL_CONFIGS.items()]
                    sb_model_dropdown = gr.Dropdown(
                        choices=model_choices,
                        value="dinov2-base",
                        label="", show_label=False,
                        info="Downloads automatically on first use to ~/.cutline/models"
                    )
                    
                    gr.Markdown("### Sorting engine")
                    sb_engine = gr.Dropdown(
                        choices=["Gemini (free tier key)", "Local only (CLIP/DINO)", "OpenAI", "Claude", "OpenRouter", "Ollama"], 
                        value="Local only (CLIP/DINO)", 
                        label="", show_label=False
                    )
                    
                    sb_api = gr.Textbox(label="", placeholder="Gemini API key", type="password", info="Free key at aistudio.google.com · stays on this PC", show_label=False)
                    sb_nsfw = gr.Checkbox(label="My photos contain NSFW content", info="Turns off cloud engines. Nothing leaves your PC; only Local and Ollama stay available.")
                    
                    sb_sort_btn = gr.Button("Sort as storyboard", variant="primary", elem_classes="primary-btn")
                    
                    gr.Markdown("### Manual Adjustments")
                    with gr.Row():
                        sb_rev = gr.Button("Reverse")
                        sb_left = gr.Button("Move left")
                        sb_right = gr.Button("Move right")
                        
                    gr.HTML('<hr style="margin-top: 10px; margin-bottom: 20px; border-color: var(--border-color-primary);"/>')    
                    sb_action = gr.Radio(["Copy to _storyboard folder", "Rename originals (001_, 002_...)"], show_label=False, value="Copy to _storyboard folder")
                    sb_apply_btn = gr.Button("Apply order", elem_classes="black-btn")
                    
                with gr.Column(scale=3):
                    sb_status = gr.Markdown("0 images sorted · drag cards to reorder, or select a card and use Move left / right.")
                    
                    # Gradio Gallery with drag-and-drop enabled by default in newer versions and reordering support
                    sb_gallery = gr.Gallery(
                        label="Storyboard", 
                        show_label=False, 
                        columns=3, 
                        allow_preview=True, 
                        object_fit="contain",
                        selected_index=0
                    )
                    
                    gr.Markdown("Tip: You can **drag and drop** images directly in the gallery to reorder your storyboard timeline.", elem_classes="status-text")
                    
                    sb_browse_btn.click(
                        None, 
                        inputs=None, 
                        outputs=[sb_folder], 
                        js=fetch_folder_js
                    )
                    
                    sb_sort_btn.click(handle_sort, inputs=[sb_folder, sb_model_dropdown, sb_engine, sb_api, sb_nsfw], outputs=[sb_gallery, sb_status])
                    
                    # Capture gallery selection index
                    def track_selection(evt: gr.SelectData):
                        return evt.index
                    sb_gallery.select(track_selection, None, selected_index_state)
                    
                    # Button actions
                    sb_rev.click(lambda items: apply_action(items, "reverse"), inputs=[sb_gallery], outputs=[sb_gallery, sb_status])
                    sb_left.click(lambda items, idx: apply_action(items, "move_left", idx), inputs=[sb_gallery, selected_index_state], outputs=[sb_gallery, sb_status])
                    sb_right.click(lambda items, idx: apply_action(items, "move_right", idx), inputs=[sb_gallery, selected_index_state], outputs=[sb_gallery, sb_status])
                    
                    # Apply final action
                    sb_apply_btn.click(apply_final_action, inputs=[sb_gallery, sb_action, sb_folder], outputs=[sb_status])

if __name__ == "__main__":
    app.launch(allowed_paths=["D:/", "C:/", "E:/", "F:/", "/"])
