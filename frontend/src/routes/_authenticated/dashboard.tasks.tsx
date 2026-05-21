import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";

type Task = { id: string; title: string; done: boolean; scope: "session" | "personal"; session_id: string | null };

export const Route = createFileRoute("/_authenticated/dashboard/tasks")({
  head: () => ({ meta: [{ title: "Tasks — Focus Room" }] }),
  component: TasksPage,
});

function TasksPage() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");

  const load = async () => {
    if (!user) return;
    const { data } = await supabase.from("tasks").select("id, title, done, scope, session_id").order("created_at", { ascending: false });
    setTasks((data as any) ?? []);
  };

  useEffect(() => { load(); }, [user]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !title.trim()) return;
    const { error } = await supabase.from("tasks").insert({ user_id: user.id, title: title.trim(), scope: "personal" });
    if (error) return toast.error(error.message);
    setTitle("");
    load();
  };

  const toggle = async (t: Task) => {
    await supabase.from("tasks").update({ done: !t.done }).eq("id", t.id);
    setTasks((ts) => ts.map((x) => (x.id === t.id ? { ...x, done: !t.done } : x)));
  };

  const remove = async (t: Task) => {
    await supabase.from("tasks").delete().eq("id", t.id);
    setTasks((ts) => ts.filter((x) => x.id !== t.id));
  };

  const personal = tasks.filter((t) => t.scope === "personal");
  const session = tasks.filter((t) => t.scope === "session");

  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-3xl font-semibold">Tasks</h1>
      <p className="mt-1 text-muted-foreground">Plan it, do it.</p>

      <form onSubmit={add} className="mt-6 flex gap-2">
        <Input placeholder="Add a task to your personal backlog..." value={title} onChange={(e) => setTitle(e.target.value)} />
        <Button type="submit">Add</Button>
      </form>

      <Section title="Current session tasks" empty="No session tasks — they'll show up when you're in a room." tasks={session} onToggle={toggle} onDelete={remove} />
      <Section title="Personal backlog" empty="Your backlog is empty." tasks={personal} onToggle={toggle} onDelete={remove} />
    </div>
  );
}

function Section({ title, tasks, empty, onToggle, onDelete }: { title: string; tasks: Task[]; empty: string; onToggle: (t: Task) => void; onDelete: (t: Task) => void }) {
  return (
    <div className="mt-8">
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <div className="mt-3 rounded-2xl bg-card p-2" style={{ boxShadow: "var(--shadow-card)" }}>
        {tasks.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-muted-foreground">{empty}</div>
        ) : tasks.map((t) => (
          <div key={t.id} className="flex items-center gap-3 rounded-xl px-3 py-2 hover:bg-muted">
            <Checkbox checked={t.done} onCheckedChange={() => onToggle(t)} />
            <span className={`flex-1 text-sm ${t.done ? "text-muted-foreground line-through" : ""}`}>{t.title}</span>
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onDelete(t)}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
      </div>
    </div>
  );
}
