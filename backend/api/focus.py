"""
backend/api/focus.py
Accepts a full webcam frame (base64), detects face/eyes using OpenCV,
crops the eye region, runs CNN inference, returns focus score.
"""
import base64
import cv2
import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel
from backend.ml import cnn_model
from backend.ml.cnn_model import predict, _img_size
from backend.utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/api/focus", tags=["focus"])

# Load face + eye cascade classifiers (built into OpenCV — no download needed)
_face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_eye_cascade  = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")


class PredictRequest(BaseModel):
    eye_crop_b64: str     # base64-encoded JPEG frame from webcam


@router.get("/health")
async def health_check():
    """Check if ML model is loaded and ready."""
    if cnn_model._model is None:
        return {"status": "error", "message": "Model not loaded", "ok": False}
    return {"status": "ready", "message": "Model loaded", "ok": True, "img_size": _img_size}


@router.post("/predict")
async def predict_focus(req: PredictRequest):
    """
    1. Decode base64 frame
    2. Detect face → crop eye region using OpenCV Haar cascades
    3. Run CNN inference
    4. Return {state, score, probs, ok}
    """
    try:
        img_bytes = base64.b64decode(req.eye_crop_b64)
        img_arr   = np.frombuffer(img_bytes, dtype=np.uint8)
        frame     = cv2.imdecode(img_arr, cv2.IMREAD_GRAYSCALE)

        if frame is None:
            log.warning("Could not decode image from base64")
            return _fallback("Could not decode image")

        # Try to detect face and crop eye region
        eye_crop = _extract_eye(frame)

        if eye_crop is not None:
            # Resize to model input size and encode back to base64
            eye_resized = cv2.resize(eye_crop, (_img_size, _img_size))
            _, buf      = cv2.imencode(".jpg", eye_resized)
            eye_b64     = base64.b64encode(buf).decode()
            return predict(eye_b64)
        else:
            # No face detected — run CNN on the full resized frame
            resized  = cv2.resize(frame, (_img_size, _img_size))
            _, buf   = cv2.imencode(".jpg", resized)
            full_b64 = base64.b64encode(buf).decode()
            return predict(full_b64)

    except Exception as e:
        log.error(f"Prediction error: {e}", exc_info=True)
        return _fallback(str(e))


def _extract_eye(gray_frame: np.ndarray):
    """Detect face → detect eye inside face ROI → return eye crop."""
    faces = _face_cascade.detectMultiScale(gray_frame, 1.1, 4, minSize=(60, 60))
    if len(faces) == 0:
        return None

    # Use the largest face
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    face_roi    = gray_frame[y:y+h, x:x+w]

    # Look for eyes in the upper half of the face
    upper_face  = face_roi[:h//2, :]
    eyes        = _eye_cascade.detectMultiScale(upper_face, 1.1, 4, minSize=(20, 20))

    if len(eyes) == 0:
        # Return full face crop if no eyes detected separately
        return face_roi

    # Use the first detected eye
    ex, ey, ew, eh = eyes[0]
    return upper_face[ey:ey+eh, ex:ex+ew]


def _fallback(reason: str = ""):
    return {"ok": False, "score": 50.0, "state": "focused",
            "probs": {"focused": 0.5, "distracted": 0.3, "closed": 0.2}}