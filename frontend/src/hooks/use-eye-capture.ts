/**
 * use-eye-capture.ts
 * React hook that:
 *   1. Requests webcam access
 *   2. Runs MediaPipe FaceMesh to find eye landmarks
 *   3. Crops the eye region and encodes it as base64
 *   4. Sends it to the Python FastAPI backend every 2 seconds
 *   5. Returns the latest focus score + state
 *
 * Privacy: only the tiny eye crop (64x64 px) is sent — never the full video.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { predictFocus, broadcastScore, type FocusResult } from "@/lib/focus-api";
import { supabase } from "@/integrations/supabase/client";

const INTERVAL_MS  = 2000;   // score every 2 seconds
const CROP_SIZE    = 64;     // must match MODEL_IMG_SIZE in Python

// MediaPipe eye landmark indices (from Face Mesh 468-point model)
// Left eye: 33, 160, 158, 133, 153, 144  — right eye: 362, 385, 387, 263, 373, 380
const LEFT_EYE_INDICES  = [33, 160, 158, 133, 153, 144];
const RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380];

interface UseEyeCaptureOptions {
  sessionId: string;
  userId: string;
  enabled?: boolean;
}

interface EyeCaptureState {
  score:       number;
  state:       string;
  cameraReady: boolean;
  error:       string | null;
  startCamera: () => void;
  stopCamera:  () => void;
}

export function useEyeCapture({
  sessionId,
  userId,
  enabled = true,
}: UseEyeCaptureOptions): EyeCaptureState {
  const [score,       setScore]       = useState(50);
  const [state,       setState]       = useState("focused");
  const [cameraReady, setCameraReady] = useState(false);
  const [error,       setError]       = useState<string | null>(null);

  const videoRef    = useRef<HTMLVideoElement | null>(null);
  const canvasRef   = useRef<HTMLCanvasElement | null>(null);
  const streamRef   = useRef<MediaStream | null>(null);
  const faceMeshRef = useRef<unknown>(null);
  const timerRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const latestLands = useRef<unknown[] | null>(null);

  // ── Start camera + MediaPipe ────────────────────────────────────────────────
  const startCamera = useCallback(async () => {
    if (!enabled) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
      });
      streamRef.current = stream;

      // Hidden video element for frame capture
      const video = document.createElement("video");
      video.srcObject = stream;
      video.playsInline = true;
      video.muted = true;
      await video.play();
      videoRef.current = video;

      // Hidden canvas for cropping
      const canvas = document.createElement("canvas");
      canvas.width  = CROP_SIZE;
      canvas.height = CROP_SIZE;
      canvasRef.current = canvas;

      // Load MediaPipe FaceMesh from CDN
      await loadFaceMesh(video, (landmarks: unknown[]) => {
        latestLands.current = landmarks;
      });

      setCameraReady(true);
      setError(null);
    } catch (e) {
      setError("Camera access denied — focus tracking disabled");
      setCameraReady(false);
    }
  }, [enabled]);

  // ── Stop camera ─────────────────────────────────────────────────────────────
  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current  = null;
    videoRef.current   = null;
    if (timerRef.current) clearInterval(timerRef.current);
    setCameraReady(false);
  }, []);

  // ── Scoring loop ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!cameraReady) return;

    timerRef.current = setInterval(async () => {
      const eyeB64 = extractEyeCrop();
      if (!eyeB64) return;

      const result: FocusResult = await predictFocus(eyeB64);
      setScore(result.score);
      setState(result.state);

      // Broadcast to Supabase so other participants see our score
      await broadcastScore(supabase as ReturnType<typeof import("@/integrations/supabase/client")["supabase"]["valueOf"]>, sessionId, userId, result.score, result.state);
    }, INTERVAL_MS);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [cameraReady, sessionId, userId]);

  // ── Eye crop extraction ──────────────────────────────────────────────────────
  function extractEyeCrop(): string | null {
    const video  = videoRef.current;
    const canvas = canvasRef.current;
    const lands  = latestLands.current;
    if (!video || !canvas || !lands || lands.length === 0) return null;

    const ctx    = canvas.getContext("2d");
    if (!ctx)    return null;

    // Get first face landmarks
    const face   = (lands as { x: number; y: number; z: number }[][])[0];
    if (!face)   return null;

    const vW = video.videoWidth;
    const vH = video.videoHeight;

    // Use left eye landmarks to compute bounding box
    const eyePts = LEFT_EYE_INDICES.map((i) => ({
      x: face[i].x * vW,
      y: face[i].y * vH,
    }));

    const xs  = eyePts.map((p) => p.x);
    const ys  = eyePts.map((p) => p.y);
    const pad = 20;
    const x1  = Math.max(0, Math.min(...xs) - pad);
    const y1  = Math.max(0, Math.min(...ys) - pad);
    const x2  = Math.min(vW, Math.max(...xs) + pad);
    const y2  = Math.min(vH, Math.max(...ys) + pad);

    // Draw cropped eye region onto small canvas
    ctx.drawImage(video, x1, y1, x2 - x1, y2 - y1, 0, 0, CROP_SIZE, CROP_SIZE);
    return canvas.toDataURL("image/jpeg", 0.8).split(",")[1];
  }

  // Auto-start on mount
  useEffect(() => {
    if (enabled) startCamera();
    return () => stopCamera();
  }, [enabled]);

  return { score, state, cameraReady, error, startCamera, stopCamera };
}

// ── MediaPipe loader ──────────────────────────────────────────────────────────
async function loadFaceMesh(
  video: HTMLVideoElement,
  onResults: (landmarks: unknown[]) => void,
) {
  // Load MediaPipe from CDN — no npm install needed
  const { FaceMesh } = await import(
    /* @vite-ignore */
    "https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4.1633559619/face_mesh.js"
  );
  const { Camera } = await import(
    /* @vite-ignore */
    "https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils@0.3.1632432234/camera_utils.js"
  );

  const faceMesh = new FaceMesh({
    locateFile: (file: string) =>
      `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4.1633559619/${file}`,
  });

  faceMesh.setOptions({
    maxNumFaces:          1,
    refineLandmarks:      true,
    minDetectionConfidence: 0.5,
    minTrackingConfidence:  0.5,
  });

  faceMesh.onResults((results: { multiFaceLandmarks?: unknown[] }) => {
    if (results.multiFaceLandmarks) {
      onResults(results.multiFaceLandmarks);
    }
  });

  const camera = new Camera(video, {
    onFrame: async () => { await faceMesh.send({ image: video }); },
    width: 640,
    height: 480,
  });

  await camera.start();
}
