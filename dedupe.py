import os
import hashlib
from PIL import Image
import imagehash

def get_file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def get_image_info(filepath):
    try:
        with Image.open(filepath) as img:
            return {
                "path": filepath,
                "width": img.width,
                "height": img.height,
                "size": os.path.getsize(filepath),
                "dhash": imagehash.dhash(img)
            }
    except Exception:
        return None

def find_duplicates(folder_path, tolerance=10):
    images = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                images.append(os.path.join(root, f))
                
    exact_hashes = {}
    dhashes = []
    
    duplicates_to_delete = []
    kept_images = []
    
    for img_path in images:
        sha = get_file_sha256(img_path)
        if sha in exact_hashes:
            duplicates_to_delete.append(img_path)
            continue
        exact_hashes[sha] = img_path
        
        info = get_image_info(img_path)
        if info:
            dhashes.append(info)
            
    kept_dhashes = []
    for info in dhashes:
        is_duplicate = False
        for kept in kept_dhashes:
            if info["dhash"] - kept["dhash"] <= tolerance:
                is_duplicate = True
                kept_res = kept["width"] * kept["height"]
                info_res = info["width"] * info["height"]
                
                if info_res > kept_res or (info_res == kept_res and info["size"] > kept["size"]):
                    duplicates_to_delete.append(kept["path"])
                    kept.update(info)
                else:
                    duplicates_to_delete.append(info["path"])
                break
        
        if not is_duplicate:
            kept_dhashes.append(info)
            kept_images.append(info["path"])
            
    return duplicates_to_delete, kept_images
