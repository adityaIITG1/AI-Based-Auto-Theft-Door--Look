from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
import cv2
import asyncio
import json
import logging
import time
import threading
from detection import ArgusDetector
from arduino_controller import ArduinoController

class ThreadedCamera:
    """Dedicated thread for fresh camera frames (Eliminates buffer lag)"""
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        self.grabbed, self.frame = self.cap.read()
        self.stopped = False
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True

    def start(self):
        self.thread.start()
        return self

    def update(self):
        while not self.stopped:
            if not self.grabbed:
                self.stop()
            else:
                self.grabbed, self.frame = self.cap.read()

    def read(self):
        return self.grabbed, self.frame

    def stop(self):
        self.stopped = True
        self.cap.release()

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
arduino = ArduinoController(port='COM9') 

# Try connecting to Arduino
arduino_connected = arduino.connect()
if arduino_connected:
    logger.info(f"Successfully connected to Arduino on {arduino.port}")
else:
    logger.warning("No Arduino found on COM9 or other ports. Running in simulation mode.")

# Global State
system_state = {
    "threat_score": 0,
    "decision": "SAFE",
    "lock_status": "UNLOCKED",
    "siren_active": False,
    "hardware_connected": arduino_connected, 
    "reasons": [],
    "last_update": 0
}

global_capture = None

@app.on_event("startup")
async def startup_event():
    global global_capture
    global_capture = ThreadedCamera(0).start()
    logger.info("Threaded Camera Started.")

@app.on_event("shutdown")
async def shutdown_event():
    global global_capture
    if global_capture:
        global_capture.stop()

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

@app.get("/control/arduino/status")
async def arduino_status():
    """Returns current Arduino connection status and port."""
    global arduino, system_state
    connected = arduino.serial_conn is not None and arduino.serial_conn.is_open
    system_state["hardware_connected"] = connected
    return {
        "connected": connected,
        "port": arduino.port if connected else None,
        "baud_rate": arduino.baud_rate
    }

@app.post("/control/arduino/connect")
async def arduino_connect(body: dict = Body(default={})):
    """Attempt to connect (or reconnect) to Arduino. Optionally specify port."""
    global arduino, arduino_connected, system_state
    
    # Allow overriding port from request body
    new_port = body.get("port", arduino.port)
    arduino.port = new_port
    
    # Close existing connection if open
    if arduino.serial_conn and arduino.serial_conn.is_open:
        arduino.serial_conn.close()
    
    success = arduino.connect()
    arduino_connected = success
    system_state["hardware_connected"] = success
    
    return {
        "success": success,
        "port": arduino.port if success else new_port,
        "message": f"Connected to {arduino.port}" if success else "Failed to connect. Check port and cable."
    }

@app.websocket("/ws/video")
async def video_endpoint(websocket: WebSocket):
    await websocket.accept()
    global system_state
    
    try:
        while True:
            if not global_capture or not global_capture.grabbed:
                await asyncio.sleep(0.1)
                continue
                
            success, frame = global_capture.read()
            if not success or frame is None:
                await asyncio.sleep(0.01)
                continue

            # Resize (Efficiency)
            height, width = frame.shape[:2]
            if width > 640:
                scale = 640 / width
                frame = cv2.resize(frame, (640, int(height * scale)))

            # Process Frame (ASYNCHRONOUS: returns immediately)
            processed_frame, score, decision, reasons = detector.process_frame(frame)

            # Update Global State
            system_state["threat_score"] = score
            system_state["decision"] = decision
            system_state["reasons"] = reasons
            system_state["last_update"] = time.time()

            # Dynamic Actions
            if decision == "LOCK":
                system_state["lock_status"] = "LOCKED"
                if arduino_connected: arduino.lock_door()
            elif score < 20: 
                # (Optional: Add auto-unlock logic if desired)
                pass

            # Send Frame (Quality 50 for max speed)
            _, buffer = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            await websocket.send_bytes(buffer.tobytes())
            
            # Target ~30 FPS
            await asyncio.sleep(0.033) 

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
