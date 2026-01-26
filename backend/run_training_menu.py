import os
import subprocess
import sys

def run_mask_training():
    print("\n--- Starting Face Mask Training ---")
    base_dir = os.path.join(os.getcwd(), "Face-Mask-Detection")
    cmd = [sys.executable, "train_mask_detector.py", "--dataset", "dataset"]
    
    print(f"Directory: {base_dir}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, cwd=base_dir, check=True)
        print("\n[SUCCESS] Mask Training Completed! Model saved to 'mask_detector.model'")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Training failed: {e}")

def run_gun_training():
    print("\n--- Starting Gun detection Training (YOLO) ---")
    base_dir = os.path.join(os.getcwd(), "gun-detection")
    
    # YOLO Command (Simplified for 1 epoch/demo, user can edit)
    # python train.py --workers 1 --device 0 --batch-size 8 --data data/custom_data.yaml 
    # --img 640 --cfg cfg/training/yolov7.yaml --weights yolov7.pt --name yolov7-custom 
    # --hyp data/hyp.scratch.custom.yaml --epochs 50
    
    cmd = [
        sys.executable, "train.py",
        "--workers", "1",
        "--batch-size", "4", # Low batch for safety
        "--data", "data/custom_data.yaml",
        "--img", "640",
        "--cfg", "cfg/training/yolov7.yaml",
        "--weights", "yolov7.pt",
        "--name", "yolov7-custom-run",
        "--hyp", "data/hyp.scratch.custom.yaml",
        "--epochs", "5" # Short run for demo
    ]
    
    print(f"Directory: {base_dir}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, cwd=base_dir, check=True)
        print("\n[SUCCESS] Gun Training Completed!")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Training failed: {e}")

def main():
    while True:
        print("\nArgus AI Training Module")
        print("1. Train Face Mask Detector (MobileNetV2)")
        print("2. Train Gun/Weapon Detector (YOLOv7)")
        print("3. Exit")
        
        choice = input("Select option (1-3): ")
        
        if choice == "1":
            run_mask_training()
        elif choice == "2":
            run_gun_training()
        elif choice == "3":
            print("Exiting...")
            break
        else:
            print("Invalid option.")

if __name__ == "__main__":
    main()
