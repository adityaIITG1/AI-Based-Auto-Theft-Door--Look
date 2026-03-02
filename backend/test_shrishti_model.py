import tensorflow as tf
import numpy as np
import cv2
import os

def load_graph(frozen_graph_filename):
    with tf.io.gfile.GFile(frozen_graph_filename, "rb") as f:
        graph_def = tf.compat.v1.GraphDef()
        graph_def.ParseFromString(f.read())

    with tf.Graph().as_default() as graph:
        tf.import_graph_def(graph_def, name="")
    return graph

model_path = r'c:\Users\ASUS\OneDrive\Desktop\Auto Theft Door Lock - ARGUS\backend\weapon-detection-shrishti\frozen_inference_graph.pb'

print(f"Loading graph from {model_path}...")
graph = load_graph(model_path)
print("Graph loaded successfully!")

# Define input and output tensors
image_tensor = graph.get_tensor_by_name('image_tensor:0')
detection_boxes = graph.get_tensor_by_name('detection_boxes:0')
detection_scores = graph.get_tensor_by_name('detection_scores:0')
detection_classes = graph.get_tensor_by_name('detection_classes:0')
num_detections = graph.get_tensor_by_name('num_detections:0')

# Create a blank image to test
dummy_img = np.zeros((300, 300, 3), dtype=np.uint8)
img_expanded = np.expand_dims(dummy_img, axis=0)

with tf.compat.v1.Session(graph=graph) as sess:
    print("Running inference test...")
    (boxes, scores, classes, num) = sess.run(
        [detection_boxes, detection_scores, detection_classes, num_detections],
        feed_dict={image_tensor: img_expanded}
    )
    print("Inference successful!")
    print(f"Number of detections found: {int(num[0])}")
