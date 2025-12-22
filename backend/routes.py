from fastapi import APIRouter
from fastapi.responses import JSONResponse, FileResponse
from hardware import monitor
import os
import csv

router = APIRouter()

@router.post("/actuators/lock")
async def lock_gate():
    monitor.lock()
    return {"status": "locked", "message": "Gate locked manually"}

@router.post("/actuators/unlock")
async def unlock_gate():
    monitor.unlock()
    return {"status": "unlocked", "message": "Gate unlocked manually"}

@router.post("/actuators/siren")
async def trigger_siren():
    monitor.siren_on()
    return {"status": "siren_on", "message": "Siren activated manually"}

@router.get("/report/generate")
async def generate_report():
    # Generate a dummy CSV report
    filename = "security_report.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Event", "Risk Score", "Action Taken"])
        writer.writerow(["2024-05-20 10:00:00", "System Start", "0", "None"])
        writer.writerow(["2024-05-20 10:05:23", "Person Detected", "10", "None"])
        writer.writerow(["2024-05-20 12:30:00", "Weapon Detected", "100", "Locked+Siren"])
    
    return FileResponse(filename, filename=filename, media_type='text/csv')
