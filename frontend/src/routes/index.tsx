import { createFileRoute, Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Sparkles, Users, Trophy, BookOpen } from "lucide-react";

export const Route = createFileRoute("/")({
  component: Landing,
});

function Landing() {
  return (
    <div className="min-h-screen bg-background">
      <header className="container mx-auto flex items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-xl" style={{ background: "var(--gradient-warm)" }}>
            <Sparkles className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="font-display text-xl font-semibold">Focus Room</span>
        </div>
        <div className="flex gap-2">
          <Link to="/login"><Button variant="ghost">Sign in</Button></Link>
          <Link to="/signup"><Button>Get started</Button></Link>
        </div>
      </header>

      <main className="container mx-auto px-6 pt-12 pb-24">
        <section className="mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full bg-secondary px-4 py-1.5 text-xs font-medium text-secondary-foreground">
            <Sparkles className="h-3 w-3" /> Cozy virtual study rooms
          </span>
          <h1 className="mt-6 font-display text-5xl font-semibold leading-tight md:text-6xl">
            Study together,<br />stay focused.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted-foreground">
            Join a cafe, library, garden, dorm, or train. Bring friends with a code,
            track your focus, share notes, and finish what matters.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Link to="/signup"><Button size="lg" className="rounded-full px-7">Create account</Button></Link>
            <Link to="/login"><Button size="lg" variant="outline" className="rounded-full px-7">Sign in</Button></Link>
          </div>
        </section>

        <section className="mx-auto mt-20 grid max-w-4xl gap-4 md:grid-cols-3">
          {[
            { icon: Users, title: "Rooms with friends", body: "Create a session, share the code, study side by side." },
            { icon: Trophy, title: "Focus leaderboards", body: "Track your focus score and climb the ranks." },
            { icon: BookOpen, title: "Shared library", body: "Drop notes and PDFs into a shared 24h library." },
          ].map((f, i) => (
            <div key={i} className="rounded-2xl bg-card p-6" style={{ boxShadow: "var(--shadow-card)" }}>
              <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-secondary text-primary">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="font-display text-lg font-semibold">{f.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{f.body}</p>
            </div>
          ))}
        </section>
      </main>
    </div>
  );
}
