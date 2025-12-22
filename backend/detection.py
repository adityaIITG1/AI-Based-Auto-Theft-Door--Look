import cv2
import time
import asyncio
import threading
from ultralytics import YOLO
from connection import manager
from hardware import monitor

# Load Model (assumed in root)
try:
    model = YOLO("yolov8n.pt") # Now in the same directory (backend/)
except:
    print("Warning: yolov8n.pt not found, downloading...")
    model = YOLO("yolov8n.pt")

# Global flags
running = True
camera_id = 0 # Default webcam

# Global Frame for Streaming
output_frame = None
lock = threading.Lock()

def detection_loop():
    global running, output_frame
    print("[DETECTION] Starting Camera...")
    cap = cv2.VideoCapture(camera_id)
    
    if not cap.isOpened():
        print("[DETECTION] Camera failed to open!")
        return

    while running:
        ret, frame = cap.read()
        if not ret:
            print("[DETECTION] Failed to read frame")
            time.sleep(1)
            continue

        # Run Inference
        results = model(frame, verbose=False, iou=0.5, conf=0.4)
        
        # Parse Results
        detections = []
        highest_risk = 0
        rule_action = "none"
        det_type = "info"
        person_count = 0
        
        # Draw Detections on Frame
        annotated_frame = results[0].plot()

        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                label = model.names[cls_id]
                conf = float(box.conf[0])
                
                # Logic Mapping
                risk = 0
                
                if label == "person":
                    person_count += 1
                
                # RISK SCORING RULES
                if label in ["knife", "scissors", "gun"]: 
                    risk = 100
                    det_type = "weapon"
                    rule_action = "auto_lock+siren"
                elif label == "person":
                    risk = 10 # Base risk for person
                
                detections.append({
                    "label": label,
                    "confidence": conf,
                    "bbox": box.xyxy[0].tolist()
                })
                
                if risk > highest_risk:
                    highest_risk = risk

        # Crowd Aggregation logic
        if person_count >= 3:
            if highest_risk < 80:
                highest_risk = 80
            det_type = "crowd"
            rule_action = "auto_lock+siren"

        # Hardware Actions (Auto)
        if rule_action == "auto_lock+siren":
            monitor.lock()
            monitor.siren_on()

        # Update Global Frame
        with lock:
            output_frame = annotated_frame.copy()

        # Broadcast via WebSocket
        payload = {
            "type": det_type,
            "risk_score": highest_risk,
            "confidence": 0.99, # Aggr
            "ts": time.strftime("%H:%M:%S"),
            "rule_action": rule_action,
            "meta": {"person_count": person_count},
            "camera_id": "CAM-1"
        }
        
        # Fire and forget broadcast
        try:
            asyncio.run(safe_broadcast(payload))
        except:
            pass # Event loop might be tricky here

        time.sleep(0.05) 

    cap.release()

async def safe_broadcast(payload):
    await manager.broadcast(payload)

def generate_frames():
    global output_frame, lock
    while True:
        with lock:
            if output_frame is None:
                continue
            (flag, encodedImage) = cv2.imencode(".jpg", output_frame)
            if not flag:
                continue
        
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
            bytearray(encodedImage) + b'\r\n')
        time.sleep(0.05)


def start_detection():
    t = threading.Thread(target=detection_loop, daemon=True)
    t.start()
