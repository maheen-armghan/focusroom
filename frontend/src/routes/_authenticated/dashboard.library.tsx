import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import { Upload, Download, Trash2, FileText } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

type LibFile = { id: string; storage_path: string; filename: string; size_bytes: number; mime_type: string | null; expires_at: string; created_at: string };

const MAX_QUOTA = 2 * 1024 * 1024 * 1024; // 2GB

export const Route = createFileRoute("/_authenticated/dashboard/library")({
  head: () => ({ meta: [{ title: "Library — Focus Room" }] }),
  component: LibraryPage,
});

function LibraryPage() {
  const { user } = useAuth();
  const [files, setFiles] = useState<LibFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = async () => {
    if (!user) return;
    const { data } = await supabase.from("library_files").select("*").eq("user_id", user.id).order("created_at", { ascending: false });
    setFiles((data as any) ?? []);
  };

  useEffect(() => { load(); }, [user]);

  const used = files.reduce((a, f) => a + Number(f.size_bytes), 0);

  const upload = async (file: File) => {
    if (!user) return;
    if (used + file.size > MAX_QUOTA) return toast.error("Storage quota exceeded (2GB)");
    setUploading(true);
    const path = `${user.id}/${Date.now()}-${file.name}`;
    const { error: upErr } = await supabase.storage.from("library").upload(path, file);
    if (upErr) { setUploading(false); return toast.error(upErr.message); }
    const { error } = await supabase.from("library_files").insert({
      user_id: user.id, storage_path: path, filename: file.name, size_bytes: file.size, mime_type: file.type,
    });
    setUploading(false);
    if (error) return toast.error(error.message);
    toast.success("Uploaded");
    load();
  };

  const download = async (f: LibFile) => {
    const { data, error } = await supabase.storage.from("library").createSignedUrl(f.storage_path, 60);
    if (error) return toast.error(error.message);
    window.open(data.signedUrl, "_blank");
  };

  const remove = async (f: LibFile) => {
    await supabase.storage.from("library").remove([f.storage_path]);
    await supabase.from("library_files").delete().eq("id", f.id);
    setFiles((fs) => fs.filter((x) => x.id !== f.id));
    toast.success("Deleted");
  };

  return (
    <div className="max-w-4xl">
      <h1 className="font-display text-3xl font-semibold">Library</h1>
      <p className="mt-1 text-muted-foreground">Files auto-delete after 24 hours.</p>

      <div className="mt-6 rounded-3xl bg-card p-6" style={{ boxShadow: "var(--shadow-card)" }}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex-1">
            <div className="text-xs uppercase text-muted-foreground">Storage used</div>
            <div className="mt-1 font-display text-xl">{(used / (1024 * 1024)).toFixed(1)} MB <span className="text-sm text-muted-foreground">/ 2 GB</span></div>
            <Progress value={(used / MAX_QUOTA) * 100} className="mt-2" />
          </div>
          <input ref={fileInput} type="file" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <Button onClick={() => fileInput.current?.click()} disabled={uploading}>
            <Upload className="mr-2 h-4 w-4" /> {uploading ? "Uploading..." : "Upload"}
          </Button>
        </div>
      </div>

      <div className="mt-6 rounded-3xl bg-card p-2" style={{ boxShadow: "var(--shadow-card)" }}>
        {files.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-muted-foreground">No files yet — upload notes or PDFs to share.</div>
        ) : files.map((f) => (
          <div key={f.id} className="flex items-center gap-3 rounded-2xl px-4 py-3 hover:bg-muted">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-secondary text-primary"><FileText className="h-5 w-5" /></div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{f.filename}</div>
              <div className="text-xs text-muted-foreground">{(f.size_bytes / 1024).toFixed(0)} KB · expires {formatDistanceToNow(new Date(f.expires_at), { addSuffix: true })}</div>
            </div>
            <Button size="icon" variant="ghost" onClick={() => download(f)}><Download className="h-4 w-4" /></Button>
            <Button size="icon" variant="ghost" onClick={() => remove(f)}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
      </div>
    </div>
  );
}
