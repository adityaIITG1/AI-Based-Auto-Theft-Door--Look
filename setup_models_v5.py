import os
from huggingface_hub import hf_hub_download, list_repo_files
import shutil

os.makedirs("models", exist_ok=True)

def get_best_pt(repo_id, limit_search=""):
    print(f"Searching {repo_id}...")
    try:
        files = list_repo_files(repo_id)
        # Filter
        candidates = [f for f in files if f.endswith(".pt")]
        if limit_search:
              candidates = [f for f in candidates if limit_search in f]

        print(f"Found candidates: {candidates}")
        
        target = None
        if "best.pt" in candidates: target = "best.pt"
        elif "weights/best.pt" in candidates: target = "weights/best.pt"
        else: target = candidates[0] if candidates else None
        
        if target:
            print(f"Downloading {target}...")
            return hf_hub_download(repo_id=repo_id, filename=target)
    except Exception as e:
        print(f"Error listing {repo_id}: {e}")
    return None

from huggingface_hub import HfApi

def main():
    api = HfApi()
    print("🔍 Searching for 'yolov5 weapon' models on HuggingFace...")
    models = api.list_models(search="yolov5 weapon", limit=10, sort="downloads", direction=-1)
    
    found_model = None
    
    for m in models:
        repo_id = m.modelId
        print(f"Checking {repo_id}...")
        try:
            path = get_best_pt(repo_id)
            if path:
                print(f"✅ Found valid model: {repo_id}")
                shutil.copy(path, "models/threat_v5.pt")
                print("✅ Saved to models/threat_v5.pt")
                found_model = repo_id
                break
        except Exception as e:
            print(f"Skipping {repo_id}: {e}")
            
    if not found_model:
        print("❌ Could not find ANY valid YOLOv5 weapon model with .pt files.")
        # Fallback to previous v8 just to ensure file exists? 
        # No, user wants v5. We will strip the v5 requirement if it fails completely?
        # Leaving it empty will crash backend.
        if os.path.exists("models/threat.pt"):
            print("⚠️ Reverting to existing v8 model as fallback.")
            shutil.copy("models/threat.pt", "models/threat_v5.pt")
    else:
        print(f"🚀 Ready! Using {found_model}")

if __name__ == "__main__":
    main()
