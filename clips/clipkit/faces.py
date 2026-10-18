"""Face detection: OpenCV's YuNet (assets/models, ~230 KB). Fast (~9 ms a 960x540 frame on Apple silicon), finds
profiles and tilted heads, gives 5 landmarks, and ignores the shirt logos, hands and mics the old Haar cascades
mistook for faces. Measured on two episodes: real faces score >= 0.82, the odd back-of-a-head 0.60-0.65."""
import os
import threading
import cv2
import numpy as np

from .project import ASSETS

MODEL = os.path.join(ASSETS, "models", "face_detection_yunet_2023mar.onnx")
MIN_SCORE = 0.75
WORK_W = 960          # detection runs at this width
SIZE_SCALE = 1.29     # YuNet's box is tighter than the engine's calibration (Haar's): 0.775x the width, same centre
_local = threading.local()  # one network per thread: a YuNet detector must not be shared between threads


def _detector(w, h):
    det = _local.__dict__.setdefault("det", {})
    if (w, h) not in det:
        det[(w, h)] = cv2.FaceDetectorYN.create(MODEL, "", (w, h), MIN_SCORE, 0.3, 5000)
    return det[(w, h)]


def detect(rgb):
    """every face: [{x, y, size, score, eyes: ((x, y), (x, y)), nose, mouth}] in the frame's own pixels"""
    sh, sw = rgb.shape[:2]
    k = WORK_W / sw
    small = cv2.resize(rgb, (WORK_W, round(sh * k)), interpolation=cv2.INTER_AREA) if sw != WORK_W else rgb
    small = np.ascontiguousarray(small[:, :, ::-1]) if small.ndim == 3 else cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    _, found = _detector(small.shape[1], small.shape[0]).detect(small)
    out = []
    for f in [] if found is None else found:
        x, y, w, h = f[:4] / k
        lm = f[4:14].reshape(5, 2) / k
        out.append({"x": float(x + w / 2), "y": float(y + h / 2), "size": float(w * SIZE_SCALE), "score": float(f[14]),
                    "eyes": (tuple(lm[0]), tuple(lm[1])), "nose": tuple(lm[2]), "mouth": (tuple(lm[3]), tuple(lm[4]))})
    return sorted(out, key=lambda d: -d["size"])


def faces_in(rgb):
    """[(cx, cy, size)] in source px: what the tracker and the angle analysis use"""
    return [(d["x"], d["y"], d["size"]) for d in detect(rgb)]
