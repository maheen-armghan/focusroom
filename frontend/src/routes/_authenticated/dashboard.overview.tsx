import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/use-auth";
import { PixelAvatar, type AvatarConfig, DEFAULT_AVATAR } from "@/components/PixelAvatar";
import { AvatarEditor } from "@/components/AvatarEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Pencil } from "lucide-react";

export const Route = createFileRoute("/_authenticated/dashboard/overview")({
  head: () => ({ meta: [{ title: "Overview — Focus Room" }] }),
  component: OverviewPage,
});

function OverviewPage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<{ username: string; display_name: string | null; bio: string | null; avatar_config: AvatarConfig } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    supabase.from("profiles").select("username, display_name, bio, avatar_config").eq("id", user.id).maybeSingle()
      .then(({ data }) => setProfile((data as any) ?? null));
  }, [user]);

  if (!profile || !user) return <div className="text-muted-foreground">Loading profile...</div>;

  const save = async () => {
    setSaving(true);
    const { error } = await supabase.from("profiles").update({
      display_name: profile.display_name,
      bio: profile.bio,
    }).eq("id", user.id);
    setSaving(false);
    if (error) return toast.error(error.message);
    toast.success("Profile saved");
  };

  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-3xl font-semibold">Overview</h1>
      <p className="mt-1 text-muted-foreground">Your personal profile.</p>

      <div className="mt-8 rounded-3xl bg-card p-8" style={{ boxShadow: "var(--shadow-card)" }}>
        <div className="flex items-start gap-6">
          <div className="rounded-2xl bg-secondary p-3">
            <PixelAvatar config={profile.avatar_config ?? DEFAULT_AVATAR} size={120} />
          </div>
          <div className="flex-1 space-y-4">
            <div>
              <Label>Username</Label>
              <Input value={profile.username} disabled className="mt-1" />
            </div>
            <div>
              <Label htmlFor="dn">Display name</Label>
              <Input id="dn" value={profile.display_name ?? ""} onChange={(e) => setProfile({ ...profile, display_name: e.target.value })} className="mt-1" />
            </div>
            <div>
              <Label htmlFor="bio">Bio</Label>
              <Textarea id="bio" rows={3} value={profile.bio ?? ""} onChange={(e) => setProfile({ ...profile, bio: e.target.value })} className="mt-1" />
            </div>
            <div className="flex gap-2">
              <Button onClick={save} disabled={saving}>{saving ? "Saving..." : "Save changes"}</Button>
              <AvatarEditor
                config={profile.avatar_config ?? DEFAULT_AVATAR}
                userId={user.id}
                trigger={<Button variant="outline"><Pencil className="mr-2 h-4 w-4" /> Edit avatar</Button>}
                onSaved={(c) => setProfile({ ...profile, avatar_config: c })}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
