import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { PixelAvatar, type AvatarConfig, DEFAULT_AVATAR } from "./PixelAvatar";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";

const HAIRS: AvatarConfig["hair"][] = ["short", "long", "buzz", "bun"];
const OUTFITS: AvatarConfig["outfit"][] = ["hoodie", "tee", "sweater", "blazer"];
const ACCS: AvatarConfig["accessory"][] = ["none", "glasses", "headphones", "beanie"];
const SKINS = ["#f5d6b8", "#e0b088", "#c08b65", "#8b5a3c", "#5c3a25"];
const COLORS = ["#7c9eff", "#ff8a65", "#81c784", "#ffd54f", "#ba68c8", "#4dd0e1"];

export function AvatarEditor({
  config,
  trigger,
  userId,
  onSaved,
}: {
  config: AvatarConfig;
  userId: string;
  trigger: React.ReactNode;
  onSaved?: (c: AvatarConfig) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<AvatarConfig>({ ...DEFAULT_AVATAR, ...config });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    const { error } = await supabase.from("profiles").update({ avatar_config: draft }).eq("id", userId);
    setSaving(false);
    if (error) return toast.error(error.message);
    toast.success("Avatar updated");
    onSaved?.(draft);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Edit your avatar</DialogTitle></DialogHeader>
        <div className="grid grid-cols-[160px_1fr] gap-6">
          <div className="grid place-items-center rounded-2xl bg-secondary p-4">
            <PixelAvatar config={draft} size={140} />
          </div>
          <div className="space-y-4">
            <Picker label="Hair" value={draft.hair} options={HAIRS} onChange={(v) => setDraft({ ...draft, hair: v })} />
            <Picker label="Outfit" value={draft.outfit} options={OUTFITS} onChange={(v) => setDraft({ ...draft, outfit: v })} />
            <Picker label="Accessory" value={draft.accessory} options={ACCS} onChange={(v) => setDraft({ ...draft, accessory: v })} />
            <Swatches label="Skin" value={draft.skin} options={SKINS} onChange={(v) => setDraft({ ...draft, skin: v })} />
            <Swatches label="Outfit color" value={draft.color} options={COLORS} onChange={(v) => setDraft({ ...draft, color: v })} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={save} disabled={saving}>{saving ? "Saving..." : "Save"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Picker<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: T[]; onChange: (v: T) => void }) {
  return (
    <div>
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">{label}</Label>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button key={o} type="button" onClick={() => onChange(o)}
            className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${value === o ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground hover:bg-muted"}`}>
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

function Swatches({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <div>
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">{label}</Label>
      <div className="mt-1 flex flex-wrap gap-2">
        {options.map((o) => (
          <button key={o} type="button" onClick={() => onChange(o)}
            className={`h-7 w-7 rounded-full border-2 transition ${value === o ? "border-primary scale-110" : "border-transparent"}`}
            style={{ background: o }} aria-label={o} />
        ))}
      </div>
    </div>
  );
}
