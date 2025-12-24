from ultralytics import YOLO

try:
    # Try loading with Ultralytics (YOLOv8) which supports many formats
    model = YOLO("backend/Cap-detection/best.pt")
    print("Model loaded successfully")
    print("Classes:", model.names)
except Exception as e:
    print(f"Error loading model: {e}")
