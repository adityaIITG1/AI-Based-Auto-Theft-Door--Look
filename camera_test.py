import cv2
import time

def test_camera(index):
    print(f"Testing camera index {index}...")
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"[-] Camera {index} failed to open.")
        return False
    
    ret, frame = cap.read()
    if not ret:
        print(f"[-] Camera {index} opened but failed to read frame.")
        cap.release()
        return False
    
    print(f"[+] Camera {index} looks GOOD. Frame size: {frame.shape}")
    cap.release()
    return True

if __name__ == "__main__":
    print("--- ARGUS Camera Diagnostic ---")
    available = []
    # Test first 3 indices
    for i in range(3):
        if test_camera(i):
            available.append(i)
    
    if not available:
        print("\n[CRITICAL] No cameras found! Please check connection.")
    else:
        print(f"\n[SUCCESS] Found working cameras at indices: {available}")
