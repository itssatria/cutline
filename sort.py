import os
import numpy as np
from PIL import Image
import cv2

def get_color_histogram(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return np.zeros(768)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    hist_r = cv2.calcHist([img], [0], None, [256], [0, 256])
    hist_g = cv2.calcHist([img], [1], None, [256], [0, 256])
    hist_b = cv2.calcHist([img], [2], None, [256], [0, 256])
    hist = np.concatenate([hist_r, hist_g, hist_b]).flatten()
    hist = hist / (hist.sum() + 1e-7)
    return hist

def compute_distance_matrix(features, histograms, color_weight=0.2):
    n = len(features)
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i+1, n):
            feat_dist = np.linalg.norm(features[i] - features[j])
            hist_dist = cv2.compareHist(histograms[i].astype(np.float32), histograms[j].astype(np.float32), cv2.HISTCMP_BHATTACHARYYA)
            d = feat_dist + color_weight * hist_dist
            dist[i, j] = d
            dist[j, i] = d
    return dist

def tsp_nearest_neighbor_2opt(dist_matrix):
    n = len(dist_matrix)
    if n <= 1: return list(range(n))
    best_path = None
    min_dist = float('inf')
    for start in range(n):
        unvisited = set(range(n))
        unvisited.remove(start)
        path = [start]
        curr = start
        path_dist = 0
        while unvisited:
            next_node = min(unvisited, key=lambda x: dist_matrix[curr, x])
            path_dist += dist_matrix[curr, next_node]
            path.append(next_node)
            unvisited.remove(next_node)
            curr = next_node
        if path_dist < min_dist:
            min_dist = path_dist
            best_path = path
            
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 2):
            for j in range(i + 1, n):
                if j - i == 1: continue
                new_path = best_path[:]
                new_path[i:j] = best_path[j-1:i-1:-1]
                old_d = sum(dist_matrix[best_path[k], best_path[k+1]] for k in range(n-1))
                new_d = sum(dist_matrix[new_path[k], new_path[k+1]] for k in range(n-1))
                if new_d < old_d:
                    best_path = new_path
                    improved = True
                    break
            if improved: break
    return best_path

def apply_action(current_items, action, select_index=None):
    # current_items is list of (path, label) tuples
    if not current_items:
        return current_items, "No images to modify."
        
    paths = [item[0] for item in current_items]
    
    if action == "reverse":
        paths.reverse()
        msg = "Storyboard order reversed."
    elif action == "move_left":
        if select_index is not None and 0 <= select_index < len(paths):
            if select_index > 0:
                paths[select_index], paths[select_index-1] = paths[select_index-1], paths[select_index]
                msg = f"Moved image {select_index+1} left."
                select_index -= 1
            else:
                msg = "Already at the beginning."
        else:
            # Move first item left or move last selected
            msg = "Please select an image in the gallery first, or use drag-and-drop."
    elif action == "move_right":
        if select_index is not None and 0 <= select_index < len(paths):
            if select_index < len(paths) - 1:
                paths[select_index], paths[select_index+1] = paths[select_index+1], paths[select_index]
                msg = f"Moved image {select_index+1} right."
                select_index += 1
            else:
                msg = "Already at the end."
        else:
            msg = "Please select an image in the gallery first, or use drag-and-drop."
    else:
        msg = "Unknown action."
        
    new_items = [(p, f"{i+1} — {os.path.basename(p)}") for i, p in enumerate(paths)]
    return new_items, msg

def apply_final_action(current_items, action_mode, folder_path):
    if not current_items:
        return "No images to apply."
    if not folder_path or not os.path.exists(folder_path):
        return "Invalid folder path."
        
    paths = [item[0] for item in current_items]
    
    if "Copy to _storyboard" in action_mode:
        target_dir = os.path.join(folder_path, "_storyboard")
        os.makedirs(target_dir, exist_ok=True)
        count = 0
        for i, p in enumerate(paths):
            ext = os.path.splitext(p)[1]
            dest = os.path.join(target_dir, f"{i+1:03d}_{os.path.basename(p)}")
            shutil.copy2(p, dest)
            count += 1
        return f"Successfully copied {count} sorted images to {target_dir}"
    else:
        # Rename originals
        count = 0
        for i, p in enumerate(paths):
            dir_name = os.path.dirname(p)
            ext = os.path.splitext(p)[1]
            # avoid collision by temporary naming or direct rename if unique
            new_name = f"{i+1:03d}_{os.path.basename(p)}"
            dest = os.path.join(dir_name, new_name)
            if p != dest:
                if os.path.exists(dest):
                    os.remove(dest)
                os.rename(p, dest)
            count += 1
        return f"Successfully renamed {count} files in {folder_path}"
