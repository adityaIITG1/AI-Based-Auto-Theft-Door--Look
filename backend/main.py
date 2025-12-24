from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
import cv2
import asyncio
import json
import logging
import time
from detection import ArgusDetector
from arduino_controller import ArduinoController

# Initialize Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ARGUS_Server")

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Components
detector = ArgusDetector(model_path='yolov8n.pt') 
arduino = ArduinoController(port='COM3') 

# Try connecting to Arduino
arduino_connected = arduino.connect()
if not arduino_connected:
    logger.warning("Arduino not found on COM3. Running in simulation mode.")

# Global State
system_state = {
    "threat_score": 0,
    "decision": "SAFE",
    "lock_status": "UNLOCKED",
    "siren_active": False,
    "hardware_connected": False, # New field
    "reasons": [],
    "last_update": 0
}

global_capture = None

@app.on_event("startup")
async def startup_event():
    global global_capture
    global_capture = cv2.VideoCapture(0)
    if not global_capture.isOpened():
        logger.error("Cannot open webcam")

@app.on_event("shutdown")
async def shutdown_event():
    global global_capture
    if global_capture:
        global_capture.release()

@app.post("/control/siren")
async def control_siren(action: dict = Body(...)):
    global system_state, arduino
    state = action.get("state", "OFF")
    
    if state == "OFF":
        system_state["siren_active"] = False
        system_state["snooze_until"] = time.time() + 30 # Snooze for 30 seconds
        logger.info("Siren manually silenced (Snoozed 30s)")
        
        # Hardware Silence
        if arduino and system_state["hardware_connected"]:
            arduino.silence_siren()
            
    elif state == "ON":
        system_state["siren_active"] = True
        system_state["snooze_until"] = 0 # Cancel snooze
        if arduino and system_state["hardware_connected"]:
            arduino.warning_siren()

    return {"status": "success", "siren": system_state["siren_active"]}

@app.websocket("/ws/video")
async def video_endpoint(websocket: WebSocket):
    await websocket.accept()
    global system_state
    
    try:
        while True:
            if not global_capture or not global_capture.isOpened():
                await asyncio.sleep(1)
                continue
                
            success, frame = global_capture.read()
            if not success:
                logger.warning("Failed to read frame")
                await asyncio.sleep(0.1)
                continue

            # Resize for Balance (Limit to 800px width)
            height, width = frame.shape[:2]
            if width > 800:
                scale = 800 / width
                frame = cv2.resize(frame, (800, int(height * scale)))

            # Process Frame
            processed_frame, score, decision, reasons = detector.process_frame(frame)

            # Check Arduino Feedback (THROTTLED: Only every 30 frames / ~1 sec)
            if arduino_connected and (detector.frame_count % 30 == 0): 
                hw_status = arduino.read_status()
                system_state["hardware_connected"] = True
                if hw_status == "STATUS_LOCKED":
                    system_state["lock_status"] = "LOCKED"
                elif hw_status == "STATUS_UNLOCKED":
                    system_state["lock_status"] = "UNLOCKED"
            else:
                system_state["hardware_connected"] = False

    # Update Global State
            # Only update if meaningful change to avoid flickering
            system_state["threat_score"] = score
            system_state["decision"] = decision
            system_state["reasons"] = reasons
            system_state["last_update"] = time.time()

            # Check Snooze
            is_snoozed = time.time() < system_state.get("snooze_until", 0)

            # Trigger Actions
            if decision == "LOCK":
                system_state["lock_status"] = "LOCKED"
                if arduino_connected: arduino.lock_door()
                
                # Dynamic Siren Logic
                if not is_snoozed:
                    system_state["siren_active"] = True
                    # Note: Arduino typically turns siren ON with LOCK. 
                    # If we want to force it off (unlikely in fresh lock), we'd need valid logic.
                    # But if snoozed, we want silence.
                else:
                    system_state["siren_active"] = False
                    if arduino_connected: arduino.silence_siren()

            elif decision == "WARN":
                if not is_snoozed:
                    if arduino_connected: arduino.warning_siren()
                    system_state["siren_active"] = True
                else:
                    system_state["siren_active"] = False
            else:
                # User Request: Auto-unlock if score < 50 (SAFE)
                if score < 50:
                    system_state["lock_status"] = "UNLOCKED"
                    system_state["siren_active"] = False
                    if arduino_connected:
                        arduino.unlock_door()

            # Send Frame (Compressed)
            # Send Frame (Quality 70 - Good balance)
            _, buffer = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            await websocket.send_bytes(buffer.tobytes())
            await asyncio.sleep(0.04) # 25 FPS Cap to prevent CPU starvation

    except WebSocketDisconnect:
        logger.info("Video Client disconnected")
    except Exception as e:
        logger.error(f"Video Error: {e}")

@app.websocket("/ws/status")
async def status_endpoint(websocket: WebSocket):
    await websocket.accept()
    global system_state
    
    try:
        while True:
            await websocket.send_json({
                "status": system_state["decision"],
                "threat_score": system_state["threat_score"],
                "lock_status": system_state["lock_status"],
                "siren": system_state["siren_active"],
                "hardware": system_state["hardware_connected"],
                "reasons": system_state["reasons"]
            })
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("Status Client disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
