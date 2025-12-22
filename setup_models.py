import os
from huggingface_hub import hf_hub_download, list_repo_files
import shutil

os.makedirs("models", exist_ok=True)

def get_best_pt(repo_id):
    print(f"Searching {repo_id}...")
    files = list_repo_files(repo_id)
    # Prefer 'best.pt', then 'weights/best.pt', then any '.pt'
    candidates = [f for f in files if f.endswith(".pt")]
    
    target = None
    if "best.pt" in candidates:
        target = "best.pt"
    elif "weights/best.pt" in candidates:
        target = "weights/best.pt"
    else:
        # Pick the largest pt file? or just the first?
        # Usually valid models are > 3MB
        target = candidates[0] if candidates else None
    
    if target:
        print(f"Downloading {target}...")
        return hf_hub_download(repo_id=repo_id, filename=target)
    return None

def main():
    # 1. Threat Model
    threat_repo = "Subh775/Threat-Detection-YOLOv8n"
    print(f"\n--- Processing {threat_repo} ---")
    try:
        path = get_best_pt(threat_repo)
        if path:
            shutil.copy(path, "models/threat.pt")
            print("✅ Saved to models/threat.pt")
        else:
            print("❌ No .pt file found!")
    except Exception as e:
        print(f"❌ Error: {e}")

    # 2. Mask Model
    mask_repo = "keremberke/yolov8n-protective-equipment-detection"
    print(f"\n--- Processing {mask_repo} ---")
    try:
        path = get_best_pt(mask_repo)
        if path:
            shutil.copy(path, "models/mask.pt")
            print("✅ Saved to models/mask.pt")
        else:
            print("❌ No .pt file found!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
