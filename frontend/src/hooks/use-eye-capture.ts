/**
 * use-eye-capture.ts  — simplified version
 * Skips MediaPipe entirely. Captures a webcam frame every 2 seconds,
 * encodes it as base64, sends to Python backend which handles face/eye detection.
 * Much more reliable than loading MediaPipe from CDN.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";

const INTERVAL_MS = 2000;
const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface UseEyeCaptureOptions {
  sessionId: string;
  userId: string;
  enabled?: boolean;
}

export function useEyeCapture({ sessionId, userId, enabled = true }: UseEyeCaptureOptions) {
  const [score, setScore] = useState(50);
  const [state, setState] = useState("focused");
  const [cameraReady, setCameraReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startCamera = useCallback(async () => {
    if (!enabled || !sessionId) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 320, height: 240, facingMode: "user" },
      });
      streamRef.current = stream;

      const video = document.createElement("video");
      video.srcObject = stream;
      video.playsInline = true;
      video.muted = true;
      await video.play();
      videoRef.current = video;

      const canvas = document.createElement("canvas");
      canvas.width = 320;
      canvas.height = 240;
      canvasRef.current = canvas;

      setCameraReady(true);
      setError(null);
      console.log("[FocusRoom] Camera started ✓");
    } catch (e) {
      setError("Camera access denied");
      setCameraReady(false);
      console.warn("[FocusRoom] Camera error:", e);
    }
  }, [enabled, sessionId]);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    videoRef.current = null;
    if (timerRef.current) clearInterval(timerRef.current);
    setCameraReady(false);
  }, []);

  // Scoring loop — runs when camera is ready
  useEffect(() => {
    if (!cameraReady || !sessionId || !userId) return;

    timerRef.current = setInterval(async () => {
      const frameB64 = captureFrame();
      if (!frameB64) return;

      try {
        const res = await fetch(`${API_BASE}/api/focus/predict`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ eye_crop_b64: frameB64 }),
        });

        if (!res.ok) return;
        const data = await res.json();

        setScore(data.score ?? 50);
        setState(data.state ?? "focused");

        // Broadcast to Supabase for other participants
        if (sessionId && userId) {
          await (supabase as any).from("focus_scores").upsert(
            {
              session_id: sessionId, user_id: userId,
              score: data.score, state: data.state,
              updated_at: new Date().toISOString()
            },
            { onConflict: "session_id,user_id" },
          );
        }
      } catch (e) {
        console.warn("[FocusRoom] Predict error:", e);
      }
    }, INTERVAL_MS);

    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [cameraReady, sessionId, userId]);

  function captureFrame(): string | null {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.6).split(",")[1];
  }

  useEffect(() => {
    if (enabled && sessionId) startCamera();
    return () => stopCamera();
  }, [enabled, sessionId]);

  return { score, state, cameraReady, error, startCamera, stopCamera };
}