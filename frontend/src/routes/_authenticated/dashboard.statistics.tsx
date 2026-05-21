import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/use-auth";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip } from "recharts";
import { Trophy, Flame, Clock } from "lucide-react";

export const Route = createFileRoute("/_authenticated/dashboard/statistics")({
  head: () => ({ meta: [{ title: "Statistics — Focus Room" }] }),
  component: StatsPage,
});

function StatsPage() {
  const { user } = useAuth();
  const [samples, setSamples] = useState<{ recorded_at: string; score: number }[]>([]);
  const [sessions, setSessions] = useState(0);

  useEffect(() => {
    if (!user) return;
    supabase.from("focus_samples").select("recorded_at, score").eq("user_id", user.id).order("recorded_at").limit(200)
      .then(({ data }) => setSamples(data ?? []));
    supabase.from("session_participants").select("session_id", { count: "exact", head: true }).eq("user_id", user.id)
      .then(({ count }) => setSessions(count ?? 0));
  }, [user]);

  const avg = samples.length ? Math.round(samples.reduce((a, s) => a + s.score, 0) / samples.length) : 0;
  const data = samples.map((s, i) => ({ idx: i, score: s.score }));

  return (
    <div className="max-w-5xl">
      <h1 className="font-display text-3xl font-semibold">Statistics</h1>
      <p className="mt-1 text-muted-foreground">Your study insights.</p>

      <div className="mt-8 grid gap-4 md:grid-cols-3">
        <Stat icon={Trophy} label="Avg focus" value={`${avg}`} suffix="/100" tone="primary" />
        <Stat icon={Flame} label="Sessions joined" value={`${sessions}`} tone="accent" />
        <Stat icon={Clock} label="Focus samples" value={`${samples.length}`} tone="secondary" />
      </div>

      <div className="mt-8 rounded-3xl bg-card p-6" style={{ boxShadow: "var(--shadow-card)" }}>
        <h2 className="font-display text-xl font-semibold">Focus over time</h2>
        <div className="mt-4 h-72">
          {data.length === 0 ? (
            <div className="grid h-full place-items-center text-sm text-muted-foreground">
              No focus data yet — finish a session to see your trend here.
            </div>
          ) : (
            <ResponsiveContainer>
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="idx" stroke="var(--color-muted-foreground)" />
                <YAxis domain={[0, 100]} stroke="var(--color-muted-foreground)" />
                <Tooltip contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: 12 }} />
                <Line type="monotone" dataKey="score" stroke="var(--color-primary)" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value, suffix, tone }: { icon: any; label: string; value: string; suffix?: string; tone: "primary" | "accent" | "secondary" }) {
  return (
    <div className="rounded-3xl bg-card p-6" style={{ boxShadow: "var(--shadow-card)" }}>
      <div className={`mb-3 grid h-10 w-10 place-items-center rounded-xl ${tone === "primary" ? "bg-primary text-primary-foreground" : tone === "accent" ? "bg-accent text-accent-foreground" : "bg-secondary text-secondary-foreground"}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 font-display text-3xl font-semibold">{value}<span className="text-base text-muted-foreground">{suffix}</span></div>
    </div>
  );
}
