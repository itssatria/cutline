import os
import torch
from transformers import AutoProcessor, AutoModel, AutoImageProcessor, Dinov2Model
from tqdm import tqdm

MODELS_DIR = os.getenv("CUTLINE_MODELS", os.path.expanduser("~/.cutline/models"))

MODEL_CONFIGS = {
    "dinov2-base": {"repo": "facebook/dinov2-base", "type": "dinov2", "size": "0.4 GB", "label": "DINOv2 Base (Best for same-scene 3D renders)"},
    "clip-b32": {"repo": "openai/clip-vit-base-patch32", "type": "clip", "size": "0.6 GB", "label": "CLIP ViT-B/32 (Fast, General)"},
    "siglip-b16": {"repo": "google/siglip-base-patch16-224", "type": "siglip", "size": "0.8 GB", "label": "SigLIP ViT-B/16 (Modern Vision)"},
    "clip-l14": {"repo": "openai/clip-vit-large-patch14", "type": "clip", "size": "1.7 GB", "label": "CLIP ViT-L/14 (Detailed Scenes)"}
}

def load_vision_model(model_id, progress_callback=None):
    os.makedirs(MODELS_DIR, exist_ok=True)
    config = MODEL_CONFIGS.get(model_id, MODEL_CONFIGS["dinov2-base"])
    repo_id = config["repo"]
    
    if progress_callback:
        progress_callback(0, f"Loading {config['label']} ({config['size']})...")
        
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    if config["type"] == "dinov2":
        processor = AutoImageProcessor.from_pretrained(repo_id, cache_dir=MODELS_DIR)
        model = Dinov2Model.from_pretrained(repo_id, cache_dir=MODELS_DIR).to(device)
    else:
        processor = AutoProcessor.from_pretrained(repo_id, cache_dir=MODELS_DIR)
        model = AutoModel.from_pretrained(repo_id, cache_dir=MODELS_DIR).to(device)
        
    if progress_callback:
        progress_callback(1, "Model loaded successfully.")
        
    return processor, model, device, config["type"]

def extract_features(image, processor, model, device, model_type):
    if model_type == "dinov2":
        inputs = processor(images=image, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
            features = outputs.last_hidden_state.mean(dim=1)
    elif model_type == "siglip":
        inputs = processor(images=image, return_tensors="pt").to(device)
        with torch.no_grad():
            features = model.get_image_features(**inputs)
    else:
        inputs = processor(images=image, return_tensors="pt").to(device)
        with torch.no_grad():
            features = model.get_image_features(**inputs) if hasattr(model, 'get_image_features') else model(**inputs).image_embeds
            
    features = features / features.norm(p=2, dim=-1, keepdim=True)
    return features.cpu().numpy()[0]
