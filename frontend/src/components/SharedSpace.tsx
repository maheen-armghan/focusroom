/**
 * SharedSpace.tsx
 * File upload panel for the session — sits next to the chat.
 * Uploads files to Supabase Storage, lists them for all participants.
 */
import { useEffect, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Paperclip, Upload, Download, Trash2, X, ChevronUp, ChevronDown } from "lucide-react";

interface FileItem {
  id: string;
  name: string;
  size: number;
  uploader: string;
  created_at: string;
  path: string;
}

interface SharedSpaceProps {
  sessionId: string;
  userId: string;
}

const ALLOWED = ["pdf","png","jpg","jpeg","docx","pptx","txt","md"];
const MAX_MB  = 25;

function fmt(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

export function SharedSpace({ sessionId, userId }: SharedSpaceProps) {
  const [open,    setOpen]    = useState(false);
  const [files,   setFiles]   = useState<FileItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load files from Supabase Storage
  const loadFiles = async () => {
    const { data } = await supabase.storage
      .from("session-files")
      .list(sessionId, { sortBy: { column: "created_at", order: "desc" } });
    if (data) {
      setFiles(data.map((f: any) => ({
        id:         f.id,
        name:       f.name,
        size:       f.metadata?.size ?? 0,
        uploader:   f.metadata?.uploader ?? "Unknown",
        created_at: f.created_at,
        path:       `${sessionId}/${f.name}`,
      })));
    }
  };

  useEffect(() => {
    if (open && sessionId) loadFiles();
  }, [open, sessionId]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ALLOWED.includes(ext)) {
      alert(`File type .${ext} not allowed. Allowed: ${ALLOWED.join(", ")}`);
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      alert(`File too large. Max ${MAX_MB} MB.`);
      return;
    }

    setUploading(true);
    const path = `${sessionId}/${Date.now()}_${file.name}`;
    const { error } = await supabase.storage
      .from("session-files")
      .upload(path, file, {
        cacheControl: "3600",
        upsert: false,
        metadata: { uploader: userId },
      } as any);

    if (error) alert("Upload failed: " + error.message);
    else await loadFiles();
    setUploading(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleDownload = async (item: FileItem) => {
    const { data } = await supabase.storage
      .from("session-files")
      .createSignedUrl(item.path, 60);
    if (data?.signedUrl) window.open(data.signedUrl, "_blank");
  };

  const handleDelete = async (item: FileItem) => {
    if (!confirm(`Delete ${item.name}?`)) return;
    await supabase.storage.from("session-files").remove([item.path]);
    await loadFiles();
  };

  return (
    <div className="fixed bottom-20 right-4 z-50 w-72">
      {/* Toggle button */}
      <button
        onClick={() => setOpen(!open)}
        className="mb-2 flex w-full items-center justify-between rounded-xl bg-black/70 px-4 py-2.5 text-sm font-semibold text-white backdrop-blur"
      >
        <span className="flex items-center gap-2">
          <Paperclip className="h-4 w-4" />
          Shared Files {files.length > 0 && `(${files.length})`}
        </span>
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
      </button>

      {open && (
        <div className="rounded-xl bg-black/80 backdrop-blur border border-white/10 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <span className="text-xs font-semibold text-white/70 uppercase tracking-wider">Session Files</span>
            <button
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
            >
              <Upload className="h-3 w-3" />
              {uploading ? "Uploading…" : "Upload"}
            </button>
            <input ref={inputRef} type="file" className="hidden" onChange={handleUpload}
              accept=".pdf,.png,.jpg,.jpeg,.docx,.pptx,.txt,.md" />
          </div>

          {/* File list */}
          <div className="max-h-64 overflow-y-auto p-2">
            {files.length === 0 ? (
              <div className="py-8 text-center text-xs text-white/40">
                No files yet. Upload study materials to share with everyone.
              </div>
            ) : (
              files.map((f) => (
                <div key={f.id} className="flex items-center gap-2 rounded-lg p-2 hover:bg-white/5">
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-xs font-medium text-white">{f.name}</div>
                    <div className="text-[10px] text-white/40">{fmt(f.size)}</div>
                  </div>
                  <button onClick={() => handleDownload(f)}
                    className="rounded p-1 text-white/50 hover:text-white">
                    <Download className="h-3.5 w-3.5" />
                  </button>
                  {f.uploader === userId && (
                    <button onClick={() => handleDelete(f)}
                      className="rounded p-1 text-white/50 hover:text-red-400">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
          <div className="px-4 py-2 text-[10px] text-white/30 border-t border-white/10">
            Max {MAX_MB}MB per file · PDF, images, docs
          </div>
        </div>
      )}
    </div>
  );
}
