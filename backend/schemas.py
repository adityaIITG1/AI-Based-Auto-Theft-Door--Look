from pydantic import BaseModel
from typing import Optional, List

class Detection(BaseModel):
    label: str
    confidence: float
    bbox: List[int]

class FrameData(BaseModel):
    ts: str
    risk_score: int
    detections: List[Detection]
    # Meta info for hardware sync
    meta: Optional[dict] = None

class ActionRequest(BaseModel):
    action: str # lock, unlock, siren
