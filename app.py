import gradio as gr
import os
from dedupe import find_duplicates
from sort import tsp_nearest_neighbor_2opt, get_color_histogram, llm_sort
from models import load_vision_model, extract_features
from PIL import Image

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
'''

def handle_dedupe(folder_path, tolerance):
    if not os.path.exists(folder_path):
        return "Folder not found.", []
    dupes, kept = find_duplicates(folder_path, tolerance)
    
    gallery_items = []
    for p in kept:
        gallery_items.append((p, f"Keep: {os.path.basename(p)}"))
    for p in dupes:
        gallery_items.append((p, f"Delete: {os.path.basename(p)}"))
        
    return f"Found **{len(dupes)} groups** · {len(dupes)} files marked Delete. Click a card to toggle Keep / Delete.", gallery_items

def handle_sort(folder_path, engine, api_key, is_nsfw, progress=gr.Progress()):
    if not os.path.exists(folder_path):
        return [], "Folder not found."
        
    images = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    if not images:
        return [], "No images found."
        
    def prog_callback(val, desc):
        progress(val, desc=desc)
        
    # Since mockup dropped the model selector, we'll default to dinov2 as it's best for your renders
    processor, model, device, model_type = load_vision_model("dinov2-base", progress_callback=prog_callback)
    
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
    
    if "Local only" not in engine and "Ollama" not in engine and not is_nsfw:
        progress(0.9, desc=f"Sending to {engine} for narrative sort...")
        try:
            llm_indices = llm_sort(sorted_images, engine, api_key, is_nsfw)
            if len(llm_indices) == len(sorted_images):
                sorted_images = [sorted_images[i] for i in llm_indices]
        except: pass
            
    gallery_items = [(img, f"{i+1} — {os.path.basename(img)}") for i, img in enumerate(sorted_images)]
    return gallery_items, f"{len(sorted_images)} images sorted · select a frame, then use Move left / right if the story needs adjusting."

with gr.Blocks(theme=gr.themes.Default(primary_hue="orange"), css=css, title="Cutline") as app:
    gr.HTML('''
    <div class="header-bar">
        <div class="brand-title">Cutline <span class="brand-subtitle">Clean cuts. Clear story.</span></div>
        <div class="header-right">
            <span>Local • RTX 3080 • 127.0.0.1:7860</span>
        </div>
    </div>
    ''')
    
    with gr.Tabs():
        with gr.Tab("1 · Duplicates"):
            with gr.Row():
                with gr.Column(scale=1, min_width=320, elem_classes="sidebar"):
                    gr.Markdown("### Image folder")
                    dup_folder = gr.Textbox(label="", placeholder="D:\Shots\Project01", show_label=False)
                    dup_sub = gr.Checkbox(label="Include subfolders", value=True)
                    
                    gr.Markdown("### Similarity tolerance: 10")
                    dup_tol = gr.Slider(0, 40, value=10, label="", show_label=False)
                    gr.HTML('<div style="display:flex; justify-content:space-between; font-size:12px; color:gray; margin-top:-10px; margin-bottom:10px;"><span>0 exact only</span><span>40 very loose</span></div>')
                    
                    scan_btn = gr.Button("Scan for duplicates", variant="primary", elem_classes="primary-btn")
                    
                    gr.HTML('<hr style="margin-top: 20px; margin-bottom: 20px; border-color: var(--border-color-primary);"/>')
                    dup_status = gr.Markdown("Found **0 groups** · 0 files marked Delete. Click a card to toggle Keep / Delete.", elem_classes="status-text")
                
                with gr.Column(scale=3):
                    dup_gallery = gr.Gallery(label="", show_label=False, columns=3, allow_preview=False, object_fit="contain")
                    
                    scan_btn.click(handle_dedupe, inputs=[dup_folder, dup_tol], outputs=[dup_status, dup_gallery])
                    
        with gr.Tab("2 · Storyboard"):
            with gr.Row():
                with gr.Column(scale=1, min_width=320, elem_classes="sidebar"):
                    gr.Markdown("### Image folder")
                    sb_folder = gr.Textbox(label="", placeholder="D:\Shots\Project01", show_label=False)
                    
                    gr.Markdown("### Sorting engine")
                    sb_engine = gr.Dropdown(
                        choices=["Gemini (free tier key)", "Local only (CLIP/DINO)", "OpenAI", "Claude", "OpenRouter", "Ollama"], 
                        value="Gemini (free tier key)", 
                        label="", show_label=False
                    )
                    
                    sb_api = gr.Textbox(label="", placeholder="Gemini API key", type="password", info="Free key at aistudio.google.com · stays on this PC", show_label=False)
                    sb_nsfw = gr.Checkbox(label="My photos contain NSFW content", info="Turns off cloud engines. Nothing leaves your PC; only Local and Ollama stay available.")
                    
                    sb_sort_btn = gr.Button("Sort as storyboard", variant="primary", elem_classes="primary-btn")
                    
                    with gr.Row():
                        sb_rev = gr.Button("Reverse")
                        sb_left = gr.Button("Move left")
                        sb_right = gr.Button("Move right")
                        
                    gr.HTML('<hr style="margin-top: 10px; margin-bottom: 20px; border-color: var(--border-color-primary);"/>')    
                    sb_action = gr.Radio(["Copy to _storyboard folder", "Rename originals (001_, 002_...)"], show_label=False, value="Copy to _storyboard folder")
                    sb_apply_btn = gr.Button("Apply order", elem_classes="black-btn")
                    
                with gr.Column(scale=3):
                    sb_status = gr.Markdown("0 images sorted · select a frame, then use Move left / right if the story needs adjusting.")
                    sb_gallery = gr.Gallery(label="Storyboard", show_label=False, columns=3, allow_preview=False, object_fit="contain")
                    gr.Markdown("Showing all images · scroll for the rest", elem_classes="status-text")
                    
                    sb_sort_btn.click(handle_sort, inputs=[sb_folder, sb_engine, sb_api, sb_nsfw], outputs=[sb_gallery, sb_status])

if __name__ == "__main__":
    app.launch()
