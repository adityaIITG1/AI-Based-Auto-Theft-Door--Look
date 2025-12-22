from huggingface_hub import list_repo_files

repos = [
    "patriciacs99/WeaponDetectionYOLOv5",
    "Ahmed-Al-Ghzawi/yolov5-weapon-detection",
    "mikelabs/yolov5-weapon-detection",
    "SkalskiP/yolov5-gun-detection"
]

for repo in repos:
    print(f"--- Files in {repo} ---")
    try:
        files = list_repo_files(repo)
        for f in files:
            if f.endswith(".pt"):
                print(f)
    except Exception as e:
        print(f"Error: {e}")
