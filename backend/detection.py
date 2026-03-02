import cv2
import time
import winsound
import logging
import numpy as np
import os
import threading
from queue import Queue
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

if TF_AVAILABLE:
    import tensorflow.compat.v1 as tf_v1

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
            self.helmet_model = YOLO('Bike-Helmet-Detction-Model/Weights/best.pt')
            self.helmet_model_loaded = True
            print("[SUCCESS] HELMET MODEL LOADED")
        except Exception as e:
            # Try absolute or different relative if first fails
            try:
                self.helmet_model = YOLO('backend/Bike-Helmet-Detction-Model/Weights/best.pt')
                self.helmet_model_loaded = True
                print("[SUCCESS] HELMET MODEL LOADED (Alt Path)")
            except:
                self.logger.error(f"Failed to load Helmet Model: {e}")
                self.helmet_model_loaded = False
            
        # 3. Load Gun Model (Custom YOLOv8)
        try:
            self.gun_model = YOLO('WraponDetectionYOLOv8/GunDetector.pt')
            self.gun_model_loaded = True
            print("[SUCCESS] YOLOv8 GUN MODEL LOADED")
        except Exception as e:
            try:
                self.gun_model = YOLO('backend/WraponDetectionYOLOv8/GunDetector.pt')
                self.gun_model_loaded = True
                print("[SUCCESS] YOLOv8 GUN MODEL LOADED (Alt Path)")
            except:
                self.logger.error(f"Failed to load Gun Model: {e}")
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
                maskModelPath = os.path.join(base_path, "mask_detector.model.keras")
                
                # Load Face Net
                self.face_net = cv2.dnn.readNet(prototxtPath, weightsPath)
                self.logger.info("FaceNet Loaded.")
                
                # Load Mask Model (Robust Patch for Keras 3)
                import shutil
                temp_h5_path = os.path.join(base_path, "mask_detector_fixed.keras")
                # ALWAYS Copy fresh model (overwrite temp) to pick up training changes
                shutil.copyfile(maskModelPath, temp_h5_path)
                    
                self.mask_model = load_model(temp_h5_path, custom_objects={
                    'GlorotUniform': PatchedGlorotUniform,
                    'Zeros': PatchedZeros,
                    'Ones': PatchedOnes
                })
                self.mask_model_loaded = True
                print("\n" + "="*50)
                print(f" [SUCCESS] CUSTOM TRAINED MODEL LOADED: {temp_h5_path}")
                print("="*50 + "\n")
                self.logger.info("Face Mask Detection Model Loaded (Type: Keras 3 Patched)")
            except Exception as e:
                self.logger.error(f"Failed to load Mask Models: {e}")
                import traceback
                traceback.print_exc()

        # 4. Load Shrishti Weapon Detection Model (TF Frozen Graph)
        self.shrishti_model_loaded = False
        if TF_AVAILABLE:
            try:
                shrishti_pb_path = r'backend/weapon-detection-shrishti/frozen_inference_graph.pb'
                if os.path.exists(shrishti_pb_path):
                    with tf_v1.gfile.GFile(shrishti_pb_path, "rb") as f:
                        graph_def = tf_v1.GraphDef()
                        graph_def.ParseFromString(f.read())
                    
                    self.shrishti_graph = tf_v1.Graph()
                    with self.shrishti_graph.as_default():
                        tf_v1.import_graph_def(graph_def, name="")
                    
                    self.shrishti_sess = tf_v1.Session(graph=self.shrishti_graph)
                    
                    # Tensors
                    self.shrishti_image_tensor = self.shrishti_graph.get_tensor_by_name('image_tensor:0')
                    self.shrishti_boxes = self.shrishti_graph.get_tensor_by_name('detection_boxes:0')
                    self.shrishti_scores = self.shrishti_graph.get_tensor_by_name('detection_scores:0')
                    self.shrishti_classes = self.shrishti_graph.get_tensor_by_name('detection_classes:0')
                    self.shrishti_num = self.shrishti_graph.get_tensor_by_name('num_detections:0')
                    
                    self.shrishti_model_loaded = True
                    print("\n" + "="*50)
                    print(f" [SUCCESS] SHRISHTI WEAPON MODEL LOADED")
                    print("="*50 + "\n")
                    self.logger.info("Shrishti Weapon Detection Model Loaded")
                else:
                    self.logger.error(f"Shrishti model not found at {shrishti_pb_path}")
            except Exception as e:
                self.logger.error(f"Failed to load Shrishti Model: {e}")

        self.hand_landmarker_loaded = False

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
        self.last_results = (None, 0, "NORMAL", [])
        self.loiter_threshold_seconds = 120 
        
        # Tamper Detection State
        self.prev_gray = None
        self.last_raw_detections = []
        self.last_threat_score = 0
        self.last_decision = "NORMAL"
        self.last_reasons = []
        self.two_masked_start_time = None

        # --- MULTI-THREADING SETUP ---
        self.input_frame = None
        self.inference_lock = threading.Lock()
        self.results_lock = threading.Lock()
        
        # Shared State (Protected by results_lock)
        self.latest_raw_detections = []
        self.latest_threat_score = 0
        self.latest_decision = "NORMAL"
        self.latest_reasons = []
        
        # Start Inference Thread
        self.inference_thread = threading.Thread(target=self._inference_worker, daemon=True)
        self.inference_thread.start()
        print("[ArgusDetector] Async Inference Thread Started.")

        
    def detect_objects(self, frame):
        # 1. Main Object Detection (COCO)
        results = self.model(frame, verbose=False)
        detections = []
        
        # Whitelist of COCO classes we care about
        # 0: person, 24: backpack, 26: handbag, 28: suitcase, 43: knife, 76: scissors
        RELEVANT_CLASSES = [
            self.CLASS_PERSON, 
            self.CLASS_BACKPACK, self.CLASS_HANDBAG, self.CLASS_SUITCASE, 
            self.CLASS_KNIFE
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
        
        # 5. Shrishti Weapon Detection (TF)
        if self.shrishti_model_loaded:
            try:
                # Preprocess for SSD Mobilenet (RGB + Expansion)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img_expanded = np.expand_dims(rgb_frame, axis=0)
                
                (boxes, scores, classes, num) = self.shrishti_sess.run(
                    [self.shrishti_boxes, self.shrishti_scores, self.shrishti_classes, self.shrishti_num],
                    feed_dict={self.shrishti_image_tensor: img_expanded}
                )
                
                boxes = np.squeeze(boxes)
                scores = np.squeeze(scores)
                classes = np.squeeze(classes).astype(np.int32)
                
                h, w = frame.shape[:2]
                for i in range(int(num[0])):
                    if scores[i] > 0.5: # Threshold for Shrishti Model
                        # TF boxes are [ymin, xmin, ymax, xmax] normalized
                        ymin, xmin, ymax, xmax = boxes[i]
                        xyxy = [xmin * w, ymin * h, xmax * w, ymax * h]
                        
                        # Shrishti model class 1 is Gun (pistol)
                        if classes[i] == 1:
                            detections.append({
                                'cls': 'GUN_REAL', 
                                'conf': float(scores[i]), 
                                'bbox': xyxy, 
                                'source': 'shrishti_model'
                            })
            except Exception as e:
                self.logger.error(f"Shrishti Inference Error: {e}")
        
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
            
            # THRESHOLD RESTORED: Decreased to 0.15 for aggressive detection
            if confidence > 0.15:
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
            
            # Estimate Face Area (Top 40%) - Increased again
            face_endY = startY + int(person_h * 0.40)
            
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
            
            # Lowered threshold for fallback safety (0.25)
            if label == "No Mask" and conf > 0.25: 
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

    def _inference_worker(self):
        """Background thread for heavy AI inference"""
        while True:
            frame_to_process = None
            with self.inference_lock:
                if self.input_frame is not None:
                    frame_to_process = self.input_frame.copy()
                    self.input_frame = None 
            
            if frame_to_process is not None:
                try:
                    # 1. AI Ensemble
                    raw_detections = self.detect_objects(frame_to_process)
                    mask_detections = self.detect_masks(frame_to_process)
                    raw_detections.extend(mask_detections)
                    
                    # 2. Full Threat Analysis
                    threat_score = 0
                    active_threats = []
                    current_time = time.time()
                    
                    # WEAPONS
                    weapons = [d for d in raw_detections if d['cls'] == 'GUN_REAL' or d['cls'] == self.CLASS_KNIFE]
                    if weapons:
                        score = self.WEIGHTS['WEAPON']
                        threat_score += score
                        active_threats.append(f"WEAPON: {weapons[0]['cls']} ({weapons[0]['conf']:.2f})")
                    
                    # CONCEALMENT (Masks/Helmets)
                    masks = [d for d in raw_detections if d['cls'] == 'MASK_REAL']
                    helmets = [d for d in raw_detections if d['cls'] == 'HELMET_REAL']
                    if masks:
                        threat_score += self.WEIGHTS['FACE_MASK']
                        active_threats.append(f"FACE COVERED ({len(masks)})")
                    if helmets:
                        threat_score += self.WEIGHTS['HELMET']
                        active_threats.append("RIDER HELMET DETECTED")

                    # CROWD / PROXIMITY
                    persons = [d['bbox'] for d in raw_detections if d['cls'] == self.CLASS_PERSON]
                    if len(persons) > 1:
                        threat_score += self.WEIGHTS['CROWD']
                        active_threats.append(f"MULTIPLE PEOPLE ({len(persons)})")
                        
                    # 2+ Masks logic
                    if len(masks) >= 2:
                        if self.two_masked_start_time is None:
                            self.two_masked_start_time = current_time
                        elif current_time - self.two_masked_start_time > 60:
                            threat_score = 100
                            active_threats.append("CRITICAL: HIGH-RISK CONCEALMENT")
                    else:
                        self.two_masked_start_time = None

                    # Final Aggregation
                    threat_score = min(threat_score, 100)
                    decision = "NORMAL"
                    if threat_score >= self.THREAT_THRESHOLD_LOCK: decision = "LOCK"
                    elif threat_score >= self.THREAT_THRESHOLD_WARN: decision = "WARN"

                    # Update shared results
                    with self.results_lock:
                        self.latest_raw_detections = raw_detections
                        self.latest_threat_score = threat_score
                        self.latest_decision = decision
                        self.latest_reasons = active_threats
                        
                except Exception as e:
                    print(f"[ArgusDetector] Inference Thread Error: {e}")
            
            time.sleep(0.01)

    def process_frame(self, frame):
        """
        Non-blocking: 
        1. Pushes frame to inference thread.
        2. Draws LATEST known results on current frame.
        3. Returns immediately.
        """
        # 1. Push latest frame for inference (if thread is ready)
        if self.inference_lock.acquire(blocking=False):
            self.input_frame = frame.copy()
            self.inference_lock.release()
            
        # 2. Get latest results
        with self.results_lock:
            detections = self.latest_raw_detections
            score = self.latest_threat_score
            decision = self.latest_decision
            reasons = self.latest_reasons
        # 3. Annotate current frame with latest detections
        annotated_frame = frame.copy()
        for d in detections:
            bbox = [int(x) for x in d['bbox']]
            cls = str(d['cls'])
            conf = d['conf']
            color = (0, 255, 0)
            if 'GUN' in cls or 'KNIFE' in cls: color = (0, 0, 255)
            elif 'MASK' in cls or 'HELMET' in cls: color = (0, 165, 255)
            
            cv2.rectangle(annotated_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
            cv2.putText(annotated_frame, f"{cls} {conf:.2f}", (bbox[0], bbox[1]-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
        # UI Status
        status_color = (0, 255, 0)
        if decision == "WARN": status_color = (0, 255, 255)
        if decision == "LOCK": status_color = (0, 0, 255)
        
        cv2.putText(annotated_frame, f"STATUS: {decision} ({score}%)", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        
        y_off = 90
        for r in reasons:
            cv2.putText(annotated_frame, f"- {r}", (20, y_off), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            y_off += 25
            
        return annotated_frame, score, decision, reasons
