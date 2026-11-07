import os
import numpy as np
from PIL import Image
import cv2
import json
import base64
import requests

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

def llm_sort(image_paths, engine, api_key, nsfw_flag):
    # Mock LLM API bypass for structural demo
    return list(range(len(image_paths)))
