/**
 * FocusHUD.tsx
 * Shows:
 *   • Your live focus score (top of session UI)
 *   • All participants' latest scores (fetched from Supabase focus_scores table)
 *   • Colour-coded indicator: green = focused, amber = distracted, red = closed
 */

import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";

interface ScoreRow {
  user_id:  string;
  score:    number;
  state:    string;
}

interface FocusHUDProps {
  sessionId:  string;
  myUserId:   string;
  myScore:    number;
  myState:    string;
  cameraOn:   boolean;
}

/** Colour + label based on focus state */
function stateStyle(state: string, score: number) {
  if (state === "closed")     return { color: "#ef4444", label: "Drowsy 😴" };
  if (state === "distracted") return { color: "#f59e0b", label: "Distracted 👀" };
  return score >= 70          ? { color: "#22c55e", label: "Focused ✓" }
                              : { color: "#f59e0b", label: "Distracted 👀" };
}

/** Small score badge — rendered on top of each avatar in the iso stage */
export function ScoreBadge({
  score, state, name,
}: { score: number; state: string; name: string }) {
  const { color, label } = stateStyle(state, score);
  return (
    <div
      style={{ background: `${color}22`, border: `1px solid ${color}88` }}
      className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold backdrop-blur"
      title={`${name}: ${label} (${score}%)`}
    >
      <span style={{ color }} className="text-[8px]">●</span>
      <span className="text-white">{Math.round(score)}%</span>
    </div>
  );
}

/** Full HUD bar shown in the session header */
export function FocusHUD({ sessionId, myUserId, myScore, myState, cameraOn }: FocusHUDProps) {
  const [allScores, setAllScores] = useState<ScoreRow[]>([]);

  useEffect(() => {
    // Initial load
    supabase
      .from("focus_scores")
      .select("user_id, score, state")
      .eq("session_id", sessionId)
      .then(({ data }) => data && setAllScores(data as ScoreRow[]));

    // Realtime updates
    const ch = supabase
      .channel(`focus-${sessionId}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "focus_scores",
          filter: `session_id=eq.${sessionId}` },
        (payload) => {
          const row = payload.new as ScoreRow;
          setAllScores((prev) => {
            const next = prev.filter((s) => s.user_id !== row.user_id);
            return [...next, row];
          });
        },
      )
      .subscribe();

    return () => { supabase.removeChannel(ch); };
  }, [sessionId]);

  const { color, label } = stateStyle(myState, myScore);
  const others = allScores.filter((s) => s.user_id !== myUserId);
  const groupAvg = allScores.length
    ? Math.round(allScores.reduce((s, r) => s + r.score, 0) / allScores.length)
    : null;

  return (
    <div className="flex items-center gap-3 rounded-full bg-black/50 px-4 py-2 text-sm backdrop-blur">
      {cameraOn ? (
        <>
          <span style={{ color }} className="text-xs">●</span>
          <span className="font-semibold text-white">{Math.round(myScore)}%</span>
          <span style={{ color }} className="text-xs text-white/70">{label}</span>
        </>
      ) : (
        <span className="text-xs text-white/50">Camera off</span>
      )}
      {groupAvg !== null && others.length > 0 && (
        <span className="text-xs text-white/50">
          · Group avg: <span className="font-semibold text-white">{groupAvg}%</span>
        </span>
      )}
    </div>
  );
}

/** Returns the score row for a specific user (for use in IsoStage) */
export function useParticipantScores(sessionId?: string) {
  const [scores, setScores] = useState<Record<string, ScoreRow>>({});

  useEffect(() => {
    if (!sessionId) return;

    supabase
      .from("focus_scores")
      .select("user_id, score, state")
      .eq("session_id", sessionId)
      .then(({ data }) => {
        if (data) {
          const map: Record<string, ScoreRow> = {};
          for (const r of data as ScoreRow[]) map[r.user_id] = r;
          setScores(map);
        }
      });

    const ch = supabase
      .channel(`focus-scores-${sessionId}`)
      .on("postgres_changes",
        { event: "*", schema: "public", table: "focus_scores",
          filter: `session_id=eq.${sessionId}` },
        (payload) => {
          const row = payload.new as ScoreRow;
          setScores((prev) => ({ ...prev, [row.user_id]: row }));
        })
      .subscribe();

    return () => { supabase.removeChannel(ch); };
  }, [sessionId]);

  return scores;
}
