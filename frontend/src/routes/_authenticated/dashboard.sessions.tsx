import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { toast } from "sonner";
import { Coffee, BookOpen, Trees, Bed, Train } from "lucide-react";
import cafeImg from "@/assets/room-cafe.jpg";
import libraryImg from "@/assets/room-library.jpg";
import gardenImg from "@/assets/room-garden.jpg";
import dormImg from "@/assets/room-dorm.jpg";
import trainImg from "@/assets/room-train.jpg";

export const Route = createFileRoute("/_authenticated/dashboard/sessions")({
  head: () => ({ meta: [{ title: "Study Session — Focus Room" }] }),
  component: SessionsPage,
});

const SPACES = [
  { id: "cafe", label: "Cafe", icon: Coffee, image: cafeImg },
  { id: "library", label: "Library", icon: BookOpen, image: libraryImg },
  { id: "garden", label: "Garden", icon: Trees, image: gardenImg },
  { id: "dorm", label: "Dorm", icon: Bed, image: dormImg },
  { id: "train", label: "Train", icon: Train, image: trainImg },
] as const;

function genCode() {
  return Math.random().toString(36).substring(2, 8).toUpperCase();
}

function fmt(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec ? sec + "s" : ""}`.trim();
  return `${sec}s`;
}

function SessionsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [space, setSpace] = useState<typeof SPACES[number]["id"]>("cafe");
  const [duration, setDuration] = useState(1800); // 30m
  const [joinCode, setJoinCode] = useState("");
  const [creating, setCreating] = useState(false);

  const create = async () => {
    if (!user) return;
    setCreating(true);
    const c = genCode();
    const { data, error } = await supabase.from("sessions").insert({
      code: c, host_id: user.id, space, duration_seconds: duration,
    }).select().single();
    if (!error && data) {
      await supabase.from("session_participants").insert({ session_id: data.id, user_id: user.id });
    }
    setCreating(false);
    if (error) return toast.error(error.message);
    toast.success("Room created — entering session");
    navigate({ to: "/session/$code", params: { code: c } });
  };

  const join = async () => {
    if (!user || !joinCode.trim()) return;
    const c = joinCode.trim().toUpperCase();
    const { data: s } = await supabase.from("sessions").select("id").eq("code", c).maybeSingle();
    if (!s) return toast.error("Session not found");
    const { error } = await supabase.from("session_participants").upsert({ session_id: s.id, user_id: user.id });
    if (error) return toast.error(error.message);
    toast.success("Joined session");
    navigate({ to: "/session/$code", params: { code: c } });
  };

  return (
    <div className="max-w-5xl">
      <h1 className="font-display text-3xl font-semibold">Study Session</h1>
      <p className="mt-1 text-muted-foreground">Pick a space, set your time, invite friends.</p>

      <div className="mt-8 grid gap-3 md:grid-cols-5">
        {SPACES.map((s) => (
          <button key={s.id} onClick={() => setSpace(s.id)}
            className={`group relative aspect-[4/5] overflow-hidden rounded-2xl text-left transition ${space === s.id ? "ring-2 ring-primary scale-[1.02]" : "hover:scale-[1.02]"}`}
            style={{ boxShadow: "var(--shadow-card)" }}>
            <img src={s.image} alt={s.label} loading="lazy" width={1280} height={768}
              className="absolute inset-[-8%] h-[116%] w-[116%] object-cover transition-transform duration-[1200ms] ease-out will-change-transform group-hover:scale-110 group-hover:-translate-y-1 group-hover:translate-x-1 motion-reduce:transform-none motion-reduce:transition-none" />
            {/* theme-aware tint: warm wash in light, deep wash in dark */}
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#1d1c17]/85 via-[#1d1c17]/30 to-transparent dark:from-[#0c0a07]/90 dark:via-[#0c0a07]/40" />
            <div className="pointer-events-none absolute inset-0 mix-blend-soft-light bg-[var(--gradient-warm)] opacity-40 dark:opacity-30" />
            <div className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.18),transparent_60%)]" />
            <div className="absolute inset-x-0 bottom-0 p-4 transition-transform duration-500 ease-out group-hover:-translate-y-1">
              <s.icon className="h-6 w-6 text-white/90 drop-shadow" />
              <div className="mt-2 font-display text-lg font-semibold text-white drop-shadow">{s.label}</div>
            </div>
          </button>
        ))}
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <div className="rounded-3xl bg-card p-6" style={{ boxShadow: "var(--shadow-card)" }}>
          <h2 className="font-display text-xl font-semibold">Create a room</h2>
          <div className="mt-5">
            <Label>Session length: <span className="font-semibold text-primary">{fmt(duration)}</span></Label>
            <Slider value={[duration]} min={30} max={10800} step={30} onValueChange={([v]) => setDuration(v)} className="mt-3" />
            <div className="mt-1 flex justify-between text-xs text-muted-foreground">
              <span>30s</span><span>3h</span>
            </div>
          </div>
          <Button className="mt-6 w-full" onClick={create} disabled={creating}>
            {creating ? "Creating..." : "Create room"}
          </Button>
        </div>

        <div className="rounded-3xl bg-card p-6" style={{ boxShadow: "var(--shadow-card)" }}>
          <h2 className="font-display text-xl font-semibold">Join a room</h2>
          <p className="mt-1 text-sm text-muted-foreground">Got a code from a friend?</p>
          <div className="mt-5 space-y-3">
            <Input placeholder="ABC123" value={joinCode} onChange={(e) => setJoinCode(e.target.value.toUpperCase())} className="font-mono text-lg tracking-wider" />
            <Button variant="outline" className="w-full" onClick={join}>Join session</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
