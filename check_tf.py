import sys
try:
    import tensorflow as tf
    print(f"TF VALID: {tf.__version__}")
except ImportError:
    print("TF INVALID")
except Exception as e:
    print(f"TF ERROR: {e}")
