"""
backend/ml/cnn_model.py
Loads the trained Keras model once at startup.
Accepts a base64-encoded greyscale eye crop, returns
{state, score, probabilities}.
"""
from __future__ import annotations
import base64
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import cv2

from backend.utils.logger import get_logger

log = get_logger(__name__)

CLASS_NAMES = ["focused", "distracted", "closed"]

# Score mapping: how much each eye state contributes to the 0-100 focus score
# focused → high score, distracted → medium penalty, closed → heavy penalty
STATE_SCORE = {"focused": 95.0, "distracted": 35.0, "closed": 5.0}

_model      = None
_img_size   = 32      # default — overridden by model_config.json
_model_path = None


def _find_model_config(base_dir: Path) -> Optional[dict]:
    """Search common locations for model_config.json."""
    candidates = [
        base_dir / "model_weights" / "model_config.json",
        base_dir.parent / "ml_training" / "model_weights" / "model_config.json",
        base_dir / "ml" / "model_weights" / "model_config.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    return None


def _find_model_file(base_dir: Path) -> Optional[Path]:
    """Search common locations for best_model.keras."""
    candidates = [
        base_dir / "model_weights" / "best_model.keras",
        base_dir.parent / "ml_training" / "checkpoints" / "best_model.keras",
        base_dir / "ml" / "model_weights" / "best_model.keras",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def load_model(model_path: str = None):
    """
    Load the Keras model. Called once at app startup (lifespan).
    Reads img_size from model_config.json so evaluate/serve always match training.
    """
    global _model, _img_size, _model_path

    try:
        import tensorflow as tf
        from tensorflow import keras
    except ImportError:
        log.error("TensorFlow not installed — focus scoring disabled.")
        return

    base_dir = Path(__file__).parent

    # ── Load config ───────────────────────────────────────────────────────────
    cfg = _find_model_config(base_dir)
    if cfg:
        _img_size = cfg.get("img_size", 32)
        log.info(f"model_config.json found — img_size={_img_size}")
    else:
        log.warning("model_config.json not found — using img_size=32")

    # ── Find model file ───────────────────────────────────────────────────────
    if model_path:
        p = Path(model_path)
    else:
        p = _find_model_file(base_dir)

    if p is None or not p.exists():
        log.error(
            f"best_model.keras not found at {p}. Copy it to backend/ml/model_weights/ "
            f"or set MODEL_PATH in .env. Provided model_path={model_path}"
        )
        return

    _model_path = p
    log.info(f"Loading model from {p}…")
    t0 = time.time()
    try:
        _model = keras.models.load_model(str(p))
        log.info(f"✓ Model loaded in {time.time()-t0:.1f}s — img_size={_img_size}")
    except Exception as e:
        log.error(f"Failed to load model: {e}")
        _model = None
        return


def predict(eye_crop_b64: str) -> dict:
    """
    Accept a base64-encoded eye crop (JPEG or PNG), return prediction.

    Returns:
        {
            "state":  "focused" | "distracted" | "closed",
            "score":  float 0-100,
            "probs":  {"focused": f, "distracted": d, "closed": c},
            "ok":     True
        }

    On any error returns {"ok": False, "score": 50.0, "state": "focused"}
    """
    if _model is None:
        return {"ok": False, "score": 50.0, "state": "focused",
                "probs": {c: 0.0 for c in CLASS_NAMES}}

    try:
        # Decode base64 → numpy image
        img_bytes = base64.b64decode(eye_crop_b64)
        img_arr   = np.frombuffer(img_bytes, dtype=np.uint8)
        img       = cv2.imdecode(img_arr, cv2.IMREAD_GRAYSCALE)

        if img is None:
            raise ValueError("cv2.imdecode returned None")

        # Resize + normalise
        img = cv2.resize(img, (_img_size, _img_size), interpolation=cv2.INTER_AREA)
        img = img.astype(np.float32) / 255.0
        img = img[np.newaxis, ..., np.newaxis]   # (1, H, W, 1)

        # Inference
        probs     = _model.predict(img, verbose=0)[0]   # shape (3,)
        pred_idx  = int(np.argmax(probs))
        state     = CLASS_NAMES[pred_idx]

        # Weighted focus score using softmax probabilities
        score = (
            float(probs[0]) * STATE_SCORE["focused"]
            + float(probs[1]) * STATE_SCORE["distracted"]
            + float(probs[2]) * STATE_SCORE["closed"]
        )

        return {
            "ok":    True,
            "state": state,
            "score": round(score, 1),
            "probs": {c: round(float(p), 4) for c, p in zip(CLASS_NAMES, probs)},
        }

    except Exception as e:
        log.warning(f"Inference error: {e}")
        return {"ok": False, "score": 50.0, "state": "focused",
                "probs": {c: 0.0 for c in CLASS_NAMES}}
