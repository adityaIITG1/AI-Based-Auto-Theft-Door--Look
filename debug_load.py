import os
import cv2
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.initializers import GlorotUniform, Zeros, Ones

# PATCH: Create custom initializers that ignore unexpected args (like dtype)
class PatchedGlorotUniform(GlorotUniform):
    def __init__(self, seed=None, **kwargs):
        super().__init__(seed=seed)

class PatchedZeros(Zeros):
    def __init__(self, **kwargs):
        super().__init__()

class PatchedOnes(Ones):
    def __init__(self, **kwargs):
        super().__init__()

print("DEBUG: Starting Model Load Check (Patched Keras 3 - Full)...")

base_path = "backend/Face-Mask-Detection"
maskModelPath = os.path.join(base_path, "mask_detector.model")

try:
    print("Creating temp .h5 file...")
    import shutil
    temp_h5 = "temp_mask_model.h5"
    shutil.copyfile(maskModelPath, temp_h5)
    
    print("Loading MaskModel with Patch...")
    mask_model = load_model(temp_h5, custom_objects={
        'GlorotUniform': PatchedGlorotUniform,
        'Zeros': PatchedZeros,
        'Ones': PatchedOnes
    })
    print("MaskModel Loaded Successfully (Patched)!")
    
    # Test prediction
    import numpy as np
    dummy_input = np.zeros((1, 224, 224, 3), dtype=np.float32)
    pred = mask_model.predict(dummy_input)
    print(f"Prediction: {pred}")
    
except Exception as e:
    with open("load_error.txt", "w") as f:
        f.write(f"Patched Load Failed: {e}")
    print(f"Patched Load Failed: {e}")
