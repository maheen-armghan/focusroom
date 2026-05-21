"""
backend/api/focus.py
POST /api/focus/predict
Accepts a base64 eye crop, runs CNN inference, returns focus score.
This is the only endpoint the Lovable frontend calls on our Python server.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from backend.ml.cnn_model import predict

router = APIRouter(prefix="/api/focus", tags=["focus"])


class PredictRequest(BaseModel):
    eye_crop_b64: str     # base64-encoded JPEG/PNG eye crop


@router.post("/predict")
async def predict_focus(req: PredictRequest):
    """
    Runs CNN inference on the eye crop.
    Returns: {state, score, probs, ok}
    """
    return predict(req.eye_crop_b64)
