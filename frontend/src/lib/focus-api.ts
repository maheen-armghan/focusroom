/**
 * focus-api.ts
 * Thin client for the FocusRoom Python FastAPI backend.
 * Only used for CNN inference — everything else stays in Supabase.
 */

// In dev: Python runs on :8000, Vite on :5173
// In prod: set VITE_API_URL to your deployed FastAPI URL
const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface FocusResult {
  state: "focused" | "distracted" | "closed";
  score: number;          // 0-100
  probs: {
    focused: number;
    distracted: number;
    closed: number;
  };
  ok: boolean;
}

/**
 * Send a base64-encoded greyscale eye crop to the Python CNN backend.
 * Returns a FocusResult with the predicted eye state and 0-100 focus score.
 *
 * @param eyeCropB64 - base64 string of a JPEG or PNG eye crop
 */
export async function predictFocus(eyeCropB64: string): Promise<FocusResult> {
  try {
    const res = await fetch(`${API_BASE}/api/focus/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ eye_crop_b64: eyeCropB64 }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    // If backend is unreachable, return a neutral score so the UI still works
    return { state: "focused", score: 50, probs: { focused: 0.5, distracted: 0.3, closed: 0.2 }, ok: false };
  }
}

/**
 * Broadcast this user's focus score to Supabase so other participants can see it.
 * Upserts into focus_scores table (created by migration below).
 */
export async function broadcastScore(
  supabase: ReturnType<typeof import("@/integrations/supabase/client")["supabase"]["valueOf"]>,
  sessionId: string,
  userId: string,
  score: number,
  state: string,
) {
  await supabase.from("focus_scores").upsert(
    { session_id: sessionId, user_id: userId, score, state, updated_at: new Date().toISOString() },
    { onConflict: "session_id,user_id" },
  );
}
