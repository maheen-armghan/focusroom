import { createFileRoute, Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/use-auth";
import { PixelAvatar, type AvatarConfig, DEFAULT_AVATAR } from "@/components/PixelAvatar";
import { AvatarEditor } from "@/components/AvatarEditor";
import { Button } from "@/components/ui/button";
import { Sparkles, User, Coffee, BarChart3, ListTodo, BookOpen, LogOut, Pencil, Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/use-theme";

export const Route = createFileRoute("/_authenticated/dashboard")({
  component: DashboardLayout,
});

const NAV = [
  { to: "/dashboard/overview", label: "Overview", icon: User },
  { to: "/dashboard/sessions", label: "Study Session", icon: Coffee },
  { to: "/dashboard/statistics", label: "Statistics", icon: BarChart3 },
  { to: "/dashboard/tasks", label: "Tasks", icon: ListTodo },
  { to: "/dashboard/library", label: "Library", icon: BookOpen },
] as const;

function DashboardLayout() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const [profile, setProfile] = useState<{ username: string; display_name: string | null; avatar_config: AvatarConfig } | null>(null);

  useEffect(() => {
    if (!user) return;
    supabase.from("profiles").select("username, display_name, avatar_config").eq("id", user.id).maybeSingle()
      .then(({ data }) => data && setProfile(data as any));
  }, [user]);

  // Redirect bare /dashboard to /dashboard/overview
  useEffect(() => {
    if (location.pathname === "/dashboard" || location.pathname === "/dashboard/") {
      navigate({ to: "/dashboard/overview", replace: true });
    }
  }, [location.pathname, navigate]);

  const signOut = async () => {
    await supabase.auth.signOut();
    navigate({ to: "/" });
  };

  const cfg = profile?.avatar_config ?? DEFAULT_AVATAR;

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex max-w-[1400px]">
        <aside className="sticky top-0 flex h-screen w-64 flex-col border-r border-border bg-sidebar p-5">
          <Link to="/" className="mb-8 flex items-center gap-2">
            <div className="grid h-9 w-9 place-items-center rounded-xl" style={{ background: "var(--gradient-warm)" }}>
              <Sparkles className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="font-display text-lg font-semibold">Focus Room</span>
          </Link>

          {user && profile && (
            <div className="mb-6 rounded-2xl bg-sidebar-accent p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-background p-1">
                  <PixelAvatar config={cfg} size={48} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{profile.display_name || profile.username}</div>
                  <div className="truncate text-xs text-muted-foreground">@{profile.username}</div>
                </div>
                <AvatarEditor
                  config={cfg}
                  userId={user.id}
                  trigger={<Button size="icon" variant="ghost" className="h-7 w-7"><Pencil className="h-3.5 w-3.5" /></Button>}
                  onSaved={(c) => setProfile({ ...profile, avatar_config: c })}
                />
              </div>
            </div>
          )}

          <nav className="flex-1 space-y-1">
            {NAV.map((item) => (
              <Link key={item.to} to={item.to}
                className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-sidebar-foreground transition hover:bg-sidebar-accent"
                activeProps={{ className: "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium bg-primary text-primary-foreground" }}>
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="space-y-1">
            <Button variant="ghost" onClick={toggle} className="w-full justify-start">
              {theme === "dark" ? <Sun className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />}
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </Button>
            <Button variant="ghost" onClick={signOut} className="w-full justify-start">
              <LogOut className="mr-2 h-4 w-4" /> Sign out
            </Button>
          </div>
        </aside>

        <main className="flex-1 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
