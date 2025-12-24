import cv2
import time
import winsound
import logging
import numpy as np
import os
from ultralytics import YOLO
from datetime import datetime
from collections import deque

# Import TensorFlow for Mask Detection
try:
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
    from tensorflow.keras.preprocessing.image import img_to_array
    from tensorflow.keras.models import load_model
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("WARNING: TensorFlow not installed. Face Mask detection will be disabled.")
else:
    # Keras 3 Patch for Legacy Deserialization
    from tensorflow.keras.initializers import GlorotUniform, Zeros, Ones
    
    class PatchedGlorotUniform(GlorotUniform):
        def __init__(self, seed=None, **kwargs):
            super().__init__(seed=seed)

    class PatchedZeros(Zeros):
        def __init__(self, **kwargs):
            super().__init__()

    class PatchedOnes(Ones):
        def __init__(self, **kwargs):
            super().__init__()

print(f"DEBUG: TF_AVAILABLE = {TF_AVAILABLE}")

class TrackedObject:
    """Simple tracker to monitor object duration and movement history"""
    def __init__(self, obj_id, cls_id, bbox, timestamp):
        self.id = obj_id
        self.cls_id = cls_id
        self.bbox_history = deque(maxlen=30) # Store last 30 positions (approx 2-3 sec)
        self.bbox_history.append(bbox)
        self.first_seen = timestamp
        self.last_seen = timestamp
        self.max_threat_level = 0

    def update(self, bbox, timestamp):
        self.bbox_history.append(bbox)
        self.last_seen = timestamp

    @property
    def duration(self):
        return self.last_seen - self.first_seen

    @property
    def centroid(self):
        # Latest bbox
        box = self.bbox_history[-1]
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2, (y1 + y2) / 2)

class ArgusDetector:
    def __init__(self, model_path='yolov8n.pt'):
        self.logger = logging.getLogger("ArgusDetector")
        
        # 1. Load YOLO (Standard)
        self.model = YOLO(model_path)
        
        # 2. Load Helmet Model (Custom YOLO)
        try:
            self.helmet_model = YOLO('backend/Bike-Helmet-Detction-Model/Weights/best.pt')
            self.helmet_model_loaded = True
            self.logger.info("Helmet Detection Model Loaded")
        except Exception as e:
            self.logger.error(f"Failed to load Helmet Model: {e}")
            self.helmet_model_loaded = False
            
        # Initialize other custom model flags to False by default
        self.gun_model_loaded = False
        self.cap_model_loaded = False

        # 3. Load Mask Detector (TF + Caffe)
        self.mask_model_loaded = False
        if TF_AVAILABLE:
            try:
                # Paths
                base_path = "backend/Face-Mask-Detection"
                prototxtPath = os.path.join(base_path, "face_detector", "deploy.prototxt")
                weightsPath = os.path.join(base_path, "face_detector", "res10_300x300_ssd_iter_140000.caffemodel")
                maskModelPath = os.path.join(base_path, "mask_detector.model")
                
                # Load Face Net
                self.face_net = cv2.dnn.readNet(prototxtPath, weightsPath)
                self.logger.info("FaceNet Loaded.")
                
                # Load Mask Model (Robust Patch for Keras 3)
                import shutil
                temp_h5_path = os.path.join(base_path, "mask_detector_fixed.h5")
                if not os.path.exists(temp_h5_path):
                    shutil.copyfile(maskModelPath, temp_h5_path)
                    
                self.mask_model = load_model(temp_h5_path, custom_objects={
                    'GlorotUniform': PatchedGlorotUniform,
                    'Zeros': PatchedZeros,
                    'Ones': PatchedOnes
                })
                self.mask_model_loaded = True
                self.logger.info("Face Mask Detection Model Loaded (Type: Keras 3 Patched)")
            except Exception as e:
                self.logger.error(f"Failed to load Mask Models: {e}")
                import traceback
                traceback.print_exc()
        
        # --- CONFIGURATION ---
        self.THREAT_THRESHOLD_LOCK = 70 
        self.THREAT_THRESHOLD_WARN = 40 
        
        # Weights for Categories
        self.WEIGHTS = {
            'WEAPON': 100,      # Category 1: Immediate Lock
            'VIOLENCE': 90,     # Category 1: Physical assault proxy
            'TAMPER': 80,       # Category 2: ATM Tampering
            'FACE_MASK': 60,    # Category 3: Face Concealment (Medium-High)
            'HELMET': 70,       # Category 3: Helmet (High)
            'BEHAVIOR': 30,     # Category 4: Abnormal Behavior
            'CROWD': 40,        # Category 5: Multi-person
            'OBJECT': 25,       # Category 6: Suspicious Object
            'TIME': 20          # Category 7: Time/Pattern
        }

        # Class IDs (COCO)
        self.CLASS_PERSON = 0
        self.CLASS_BACKPACK = 24
        self.CLASS_HANDBAG = 26
        self.CLASS_SUITCASE = 28
        self.CLASS_KNIFE = 43
        self.CLASS_SCISSORS = 76
        
        # Proxies
        self.CLASS_PROXY_TOOL = 41   # 'cup' -> Simulates 'Tampering Tool'
        
        # Tracking State
        self.tracked_objects = {}
        self.next_object_id = 0
        self.frame_count = 0
        self.loiter_threshold_seconds = 120 
        
        # Tamper Detection State
        self.prev_gray = None
        
        # Optimization: Frame Skipping (Increased to 5 for smoother video)
        self.skip_interval = 5 
        self.last_raw_detections = []
        self.last_threat_score = 0
        self.last_decision = "NORMAL"
        self.last_reasons = []
        
    def detect_objects(self, frame):
        # 1. Main Object Detection (COCO)
        results = self.model(frame, verbose=False)
        detections = []
        
        # Whitelist of COCO classes we care about
        # 0: person, 24: backpack, 26: handbag, 28: suitcase, 43: knife, 76: scissors
        RELEVANT_CLASSES = [
            self.CLASS_PERSON, 
            self.CLASS_BACKPACK, self.CLASS_HANDBAG, self.CLASS_SUITCASE, 
            self.CLASS_KNIFE, self.CLASS_SCISSORS
        ]
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls = int(box.cls[0])
                
                # STRICT FILTERING: Only allow relevant classes
                if cls not in RELEVANT_CLASSES:
                    continue
                    
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].tolist()
                detections.append({'cls': cls, 'conf': conf, 'bbox': xyxy, 'source': 'coco'})
        
        # 2. Helmet Detection (Custom Model)
        if self.helmet_model_loaded:
            helmet_results = self.helmet_model(frame, verbose=False)
            for r in helmet_results:
                boxes = r.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    # Class 0 = With Helmet, Class 1 = Without Helmet
                    if cls == 0: # We only care about "With Helmet"
                        conf = float(box.conf[0])
                        if conf > 0.4: # Threshold
                            xyxy = box.xyxy[0].tolist()
                            detections.append({'cls': 'HELMET_REAL', 'conf': conf, 'bbox': xyxy, 'source': 'helmet_model'})

        # 3. Gun Detection (Custom Model)
        if self.gun_model_loaded:
            gun_results = self.gun_model(frame, verbose=False)
            for r in gun_results:
                boxes = r.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    # Classes: 0: 'gun', 1: 'guns', 2: 'handgun' - Assuming model mapping
                    conf = float(box.conf[0])
                    if conf > 0.4: 
                        xyxy = box.xyxy[0].tolist()
                        detections.append({'cls': 'GUN_REAL', 'conf': conf, 'bbox': xyxy, 'source': 'gun_model'})

        # 4. Cap Detection (Custom Model)
        if self.cap_model_loaded:
            cap_results = self.cap_model(frame, verbose=False)
            for r in cap_results:
                boxes = r.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    # Class 0 = Cap
                    if cls == 0:
                        conf = float(box.conf[0])
                        if conf > 0.4:
                            xyxy = box.xyxy[0].tolist()
                            detections.append({'cls': 'CAP_REAL', 'conf': conf, 'bbox': xyxy, 'source': 'cap_model'})
        
        return detections

    def detect_masks(self, frame):
        """Run Caffe Face Detector + TF Mask Model"""
        if not self.mask_model_loaded:
            return []
            
        (h, w) = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104.0, 177.0, 123.0))
        self.face_net.setInput(blob)
        detections = self.face_net.forward()
        
        faces = []
        locs = []
        preds = []
        results = []
        
        # Loop over detections
        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            # DEBUG
            if confidence > 0.05:
                print(f"DEBUG: Face Conf={confidence:.2f}")
            
            # THRESHOLD RESTORED: Increased from 0.15 to 0.5 to prevent false positives (like piles of paper)
            if confidence > 0.5:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (startX, startY, endX, endY) = box.astype("int")
                (startX, startY) = (max(0, startX), max(0, startY))
                (endX, endY) = (min(w - 1, endX), min(h - 1, endY))
                
                # Extract face ROI
                face = frame[startY:endY, startX:endX]
                if face.shape[0] < 10 or face.shape[1] < 10: continue # Skip small artifacts
                
                face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
                face = cv2.resize(face, (224, 224))
                face = img_to_array(face)
                face = preprocess_input(face)
                
                faces.append(face)
                locs.append((startX, startY, endX, endY))

        # Batch prediction
        if len(faces) > 0:
            faces = np.array(faces, dtype="float32")
            preds = self.mask_model.predict(faces, batch_size=32)
        
        for (box, pred) in zip(locs, preds):
            (startX, startY, endX, endY) = box
            (mask, withoutMask) = pred
            
            # Label
            label = "Mask" if mask > withoutMask else "No Mask"
            conf = max(mask, withoutMask)
            
            if label == "Mask" and conf > 0.5:
                results.append({'cls': 'MASK_REAL', 'conf': float(conf), 'bbox': [startX, startY, endX, endY], 'source': 'mask_model'})
            elif label == "No Mask" and conf > 0.5:
                 results.append({'cls': 'FACE_VISIBLE', 'conf': float(conf), 'bbox': [startX, startY, endX, endY], 'source': 'mask_model'})
            
        return results

    def check_face_fallback(self, frame, person_box):
        """Fallback: Check top area of person box for mask/no-mask"""
        if not self.mask_model_loaded: return False
        
        try:
            (startX, startY, endX, endY) = person_box.astype("int")
            
            # Ensure within frame
            (h, w) = frame.shape[:2]
            (startX, startY) = (max(0, startX), max(0, startY))
            (endX, endY) = (min(w - 1, endX), min(h - 1, endY))
            
            # Person height
            person_h = endY - startY
            if person_h < 50: return False # Too small
            
            # Estimate Face Area (Top 25%)
            face_endY = startY + int(person_h * 0.25)
            
            face_crop = frame[startY:face_endY, startX:endX]
            if face_crop.shape[0] < 10 or face_crop.shape[1] < 10: return False
            
            face_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            face_crop = cv2.resize(face_crop, (224, 224))
            face_crop = img_to_array(face_crop)
            face_crop = preprocess_input(face_crop)
            face_crop = np.expand_dims(face_crop, axis=0)
            
            (mask, withoutMask) = self.mask_model.predict(face_crop, verbose=0)[0]
            label = "Mask" if mask > withoutMask else "No Mask"
            conf = max(mask, withoutMask)
            
            print(f"FALLBACK: {label} ({conf:.2f})")
            
            # Lowered threshold for fallback safety
            if label == "No Mask" and conf > 0.40: 
                return True
        except Exception as e:
            print(f"FALLBACK ERROR: {e}")
            pass
            
        return False

    def check_tampering(self, frame, gray_frame):
        """Category 2: Check for camera blocking/tampering"""
        if self.prev_gray is None:
            self.prev_gray = gray_frame
            return False, "Initializing"
            
        # 1. Global Intensity Change (Occlusion)
        avg_intensity = np.mean(gray_frame)
        if avg_intensity < 30: # Very Dark
            return True, "Camera Occluded (Too Dark)"
            
        # 2. Structural Similarity (simplified to avoid heavy computation per frame)
        std_dev = np.std(gray_frame)
        if std_dev < 10:
            return True, "Camera Covered (Low Contrast)"
            
        return False, ""

    def process_frame(self, frame):
        self.frame_count += 1
        current_time = time.time()
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        if self.frame_count % self.skip_interval != 0 and self.frame_count > 1:
            # SKIP FRAME: Use cached values
            raw_detections = self.last_raw_detections
            threat_score = self.last_threat_score
            decision = self.last_decision
            reasons = self.last_reasons
        else:
            # PROCESS FRAME
            
            # 1. Standard Detections
            raw_detections = self.detect_objects(frame)
            
            # 2. Mask Detections
            mask_detections = self.detect_masks(frame)
            raw_detections.extend(mask_detections)
            
            threat_score = 0
            active_threats = [] # List of tuples (Category, Description, Weight)
            reasons = [] # User facing strings
            
            # --- ANALYSIS ---

            # CATEGORY 2: ATM TAMPERING (Camera Level)
            is_tampered, tamper_reason = self.check_tampering(frame, gray_frame)
            if is_tampered:
                threat_score += self.WEIGHTS['TAMPER']
                active_threats.append(("TAMPER", tamper_reason, self.WEIGHTS['TAMPER']))

            # Object Level Analysis
            person_count = 0
            weapons_found = []
            suspicious_objects = []
            helmet_detected = False
            mask_detected = False
            face_visible = False
            
            # Track persons for behavior
            current_frame_persons = []

            for d in raw_detections:
                cls = d['cls']
                box = d['bbox']
                source = d['source']
                
                # Count People (Only from COCO)
                # STRICTER FILTER: Only count high confidence persons to avoid ghosts
                if source == 'coco' and cls == self.CLASS_PERSON:
                    if d['conf'] > 0.60:
                        person_count += 1
                        current_frame_persons.append(box)
                    
                # Category 1: Weapons
                if source == 'coco' and cls in [self.CLASS_KNIFE, self.CLASS_SCISSORS]:
                    weapons_found.append(self.model.names[cls])
                
                # HELMET REAL
                if source == 'helmet_model' and cls == 'HELMET_REAL':
                    helmet_detected = True
                    
                # MASK REAL
                if source == 'mask_model' and cls == 'MASK_REAL':
                    mask_detected = True

                # FACE VISIBLE
                if source == 'mask_model' and cls == 'FACE_VISIBLE':
                    face_visible = True
                    
                    
                # Category 6: Suspicious Objects (Bags)
                if source == 'coco' and cls in [self.CLASS_BACKPACK, self.CLASS_SUITCASE]:
                    suspicious_objects.append(self.model.names[cls])

            # --- LOGIC AGGREGATION ---

            # Fallback: If Person detected but No Face, check YOLO Box
            if person_count > 0 and not face_visible and not mask_detected:
                 for box in current_frame_persons:
                      if self.check_face_fallback(frame, np.array(box)):
                           face_visible = True
                           break

            # CAT 1: WEAPON (High Severity)
            if weapons_found:
                threat_score += self.WEIGHTS['WEAPON']
                active_threats.append(("WEAPON", f"Weapon(s): {', '.join(weapons_found)}", self.WEIGHTS['WEAPON']))

            # CAT 3: FACE CONCEALMENT (Mask)
            if mask_detected:
                 threat_score += self.WEIGHTS['FACE_MASK']
                 active_threats.append(("FACE", "Face Mask Detected", self.WEIGHTS['FACE_MASK']))
                    
            # CAT 3: HELMET (Real Model)
            if helmet_detected:
                threat_score += self.WEIGHTS['HELMET']
                active_threats.append(("HELMET", "Rider Helmet Detected", self.WEIGHTS['HELMET']))

            # CAT 5: MULTI-PERSON (Crowd)
            if person_count > 1:
                threat_score += self.WEIGHTS['CROWD']
                active_threats.append(("CROWD", f"Multiple People ({person_count})", self.WEIGHTS['CROWD']))
                
                # Simple Proximity Check
                for i in range(len(current_frame_persons)):
                    for j in range(i + 1, len(current_frame_persons)):
                        box1 = current_frame_persons[i]
                        box2 = current_frame_persons[j]
                        
                        xA = max(box1[0], box2[0])
                        yA = max(box1[1], box2[1])
                        xB = min(box1[2], box2[2])
                        yB = min(box1[3], box2[3])
                        
                        interArea = max(0, xB - xA) * max(0, yB - yA)
                        if interArea > 0: 
                            threat_score += 15 
                            # Stricter overlap for Violence (was 20000)
                            if interArea > 40000:
                                 active_threats.append(("VIOLENCE", "Subjects in Close Conflict", self.WEIGHTS['VIOLENCE']))

            # CAT 6: OBJECTS
            if suspicious_objects:
                threat_score += self.WEIGHTS['OBJECT']
                active_threats.append(("OBJECT", f"Suspicious Item: {suspicious_objects[0]}", self.WEIGHTS['OBJECT']))

            # CAT 7: TIME
            hour = datetime.now().hour
            if hour >= 23 or hour < 5:
                threat_score += self.WEIGHTS['TIME']
                active_threats.append(("TIME", "Late Night Access", self.WEIGHTS['TIME']))
                
                # Late Night + Person = Suspicious
                # SAFETY: If face is visible, do not apply this penalty
                if person_count > 0 and not face_visible:
                    threat_score += 30
                    active_threats.append(("BEHAVIOR", "Suspicious Late Activity", 30))
                elif person_count > 0 and face_visible:
                     active_threats.append(("SAFETY", "Identity Verification: OK", -10))
                
            # Final Score Cap
            threat_score = min(threat_score, 100)
            
            # --- DECISION LOGIC ---
            decision = "NORMAL"
            if threat_score >= self.THREAT_THRESHOLD_LOCK:
                decision = "LOCK"
                # Laptop Siren (High Pitch, Long)
                try: winsound.Beep(2500, 500) 
                except: pass
            elif threat_score >= self.THREAT_THRESHOLD_WARN:
                decision = "WARN"
                # Laptop Warning (Lower Pitch, Short)
                try: winsound.Beep(1000, 200)
                except: pass
                
            # Format reasons for UI
            reasons = [t[1] for t in active_threats]
            
            # Cache results
            self.last_raw_detections = raw_detections
            self.last_threat_score = threat_score
            self.last_decision = decision
            self.last_reasons = reasons
        
        # --- ANNOTATION ---
        for d in raw_detections:
            x1, y1, x2, y2 = map(int, d['bbox'])
            cls = d['cls']
            conf = d['conf']
            source = d['source']
            
            color = (0, 255, 0) # Green normal
            label_text = ""
            
            # Filter Visualization: Only draw Threats or Persons
            should_draw = False
            color = (0, 255, 0) # Default Green
            label_text = ""
            
            if source == 'coco':
                # Only draw Person, Weapons, Bags
                if cls in [self.CLASS_PERSON, self.CLASS_BACKPACK, self.CLASS_HANDBAG, self.CLASS_SUITCASE]:
                    should_draw = True
                    label_text = f"{self.model.names[cls]} {conf:.2f}"
                elif cls in [self.CLASS_KNIFE, self.CLASS_SCISSORS]:
                    should_draw = True
                    label_text = f"{self.model.names[cls]} {conf:.2f}"
                    color = (0, 0, 255) # Red for weapon

            elif source in ['helmet_model', 'mask_model', 'gun_model', 'cap_model']:
                should_draw = True # Always draw custom model detections
                if source == 'helmet_model':
                    label_text = f"HELMET {conf:.2f}"
                    if cls == 'HELMET_REAL': color = (0, 0, 255)
                elif source == 'mask_model':
                    label_text = f"MASK {conf:.2f}"
                    color = (0, 0, 255)
                elif source == 'gun_model':
                    label_text = f"GUN {conf:.2f}"
                    color = (0, 0, 255)
                elif source == 'cap_model':
                    label_text = f"CAP {conf:.2f}"
                    color = (0, 165, 255)

            if should_draw:
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label_text, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
        # Overlay Status
        status_color = (0, 255, 0)
        if decision == "WARN": 
            status_color = (0, 255, 255) # Yellow
            try: winsound.Beep(1000, 200) # Short warning beep
            except: pass
        if decision == "LOCK": 
            status_color = (0, 0, 255) # Red
            try: winsound.Beep(2500, 500) # Long alarm beep
            except: pass
        
        cv2.putText(frame, f"STATUS: {decision} ({threat_score}%)", (20, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        
        y_offset = 80
        for reason in reasons:
            cv2.putText(frame, f"- {reason}", (20, y_offset), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            y_offset += 25

        return frame, threat_score, decision, reasons
