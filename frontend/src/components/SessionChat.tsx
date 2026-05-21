import { useEffect, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MessageCircle, Minus, Send, SmilePlus, X } from "lucide-react";
import { PixelAvatar, DEFAULT_AVATAR, type AvatarConfig } from "@/components/PixelAvatar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

type ChatRow = {
  id: number;
  created_at: string;
  content: string;
  user_id: string;
  session_id: string;
};

type ReactionRow = {
  id: number;
  message_id: number;
  user_id: string;
  emoji: string;
};

const QUICK_EMOJIS = ["👍", "❤️", "😂", "🎉", "🔥", "👏", "😮", "🙏"];

type Profile = {
  id: string;
  username: string;
  display_name: string | null;
  avatar_config: AvatarConfig;
};

export function SessionChat({
  sessionId,
  userId,
}: {
  sessionId: string;
  userId: string | undefined;
}) {
  const [open, setOpen] = useState(true);
  const [messages, setMessages] = useState<ChatRow[]>([]);
  const [profiles, setProfiles] = useState<Record<string, Profile>>({});
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [unread, setUnread] = useState(0);
  const [reactions, setReactions] = useState<ReactionRow[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const loadProfilesFor = async (ids: string[]) => {
    const need = Array.from(new Set(ids)).filter((id) => !profiles[id]);
    if (need.length === 0) return;
    const { data } = await supabase
      .from("profiles")
      .select("id, username, display_name, avatar_config")
      .in("id", need);
    if (data) {
      setProfiles((prev) => {
        const next = { ...prev };
        for (const p of data) next[p.id] = p as unknown as Profile;
        return next;
      });
    }
  };

  // Initial load
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data } = await supabase
        .from("chat_messages")
        .select("*")
        .eq("session_id", sessionId)
        .order("created_at", { ascending: true })
        .limit(200);
      if (cancelled || !data) return;
      setMessages(data as ChatRow[]);
      loadProfilesFor((data as ChatRow[]).map((m) => m.user_id));
      const { data: rx } = await supabase
        .from("chat_reactions")
        .select("id, message_id, user_id, emoji")
        .eq("session_id", sessionId);
      if (!cancelled && rx) setReactions(rx as ReactionRow[]);
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Realtime subscription
  useEffect(() => {
    const ch = supabase
      .channel(`chat-${sessionId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "chat_messages",
          filter: `session_id=eq.${sessionId}`,
        },
        (payload) => {
          const row = payload.new as ChatRow;
          setMessages((prev) =>
            prev.some((m) => m.id === row.id) ? prev : [...prev, row]
          );
          loadProfilesFor([row.user_id]);
          if (!open && row.user_id !== userId) {
            setUnread((n) => n + 1);
          }
        }
      )
      .subscribe();
    return () => {
      supabase.removeChannel(ch);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, open, userId]);

  // Realtime reactions
  useEffect(() => {
    const ch = supabase
      .channel(`chat-reactions-${sessionId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "chat_reactions",
          filter: `session_id=eq.${sessionId}`,
        },
        (payload) => {
          const row = payload.new as ReactionRow;
          setReactions((prev) =>
            prev.some((r) => r.id === row.id) ? prev : [...prev, row]
          );
        }
      )
      .on(
        "postgres_changes",
        {
          event: "DELETE",
          schema: "public",
          table: "chat_reactions",
          filter: `session_id=eq.${sessionId}`,
        },
        (payload) => {
          const row = payload.old as Partial<ReactionRow>;
          setReactions((prev) => prev.filter((r) => r.id !== row.id));
        }
      )
      .subscribe();
    return () => {
      supabase.removeChannel(ch);
    };
  }, [sessionId]);

  // Autoscroll
  useEffect(() => {
    if (!open) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  // Clear unread when opening
  useEffect(() => {
    if (open) setUnread(0);
  }, [open]);

  const send = async () => {
    const content = draft.trim();
    if (!content || !userId || sending) return;
    setSending(true);
    const { error } = await supabase.from("chat_messages").insert({
      session_id: sessionId,
      user_id: userId,
      content,
    });
    setSending(false);
    if (!error) setDraft("");
  };

  const toggleReaction = async (messageId: number, emoji: string) => {
    if (!userId) return;
    const mine = reactions.find(
      (r) => r.message_id === messageId && r.user_id === userId && r.emoji === emoji
    );
    if (mine) {
      setReactions((prev) => prev.filter((r) => r.id !== mine.id));
      await supabase.from("chat_reactions").delete().eq("id", mine.id);
    } else {
      const { data, error } = await supabase
        .from("chat_reactions")
        .insert({ message_id: messageId, session_id: sessionId, user_id: userId, emoji })
        .select("id, message_id, user_id, emoji")
        .single();
      if (!error && data) {
        setReactions((prev) =>
          prev.some((r) => r.id === (data as ReactionRow).id)
            ? prev
            : [...prev, data as ReactionRow]
        );
      }
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-medium text-primary-foreground shadow-[0_8px_30px_rgba(0,0,0,0.45)] backdrop-blur hover:brightness-110"
        aria-label="Open chat"
      >
        <MessageCircle className="h-4 w-4" />
        Chat
        {unread > 0 && (
          <span className="ml-1 grid h-5 min-w-5 place-items-center rounded-full bg-white px-1.5 text-[10px] font-semibold text-primary">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[70vh] max-h-[560px] w-[340px] max-w-[92vw] flex-col overflow-hidden rounded-2xl border border-white/15 bg-black/70 text-white shadow-[0_20px_50px_rgba(0,0,0,0.55)] backdrop-blur-xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <MessageCircle className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Room chat</span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-white/80 hover:bg-white/10 hover:text-white"
            onClick={() => setOpen(false)}
            aria-label="Minimize chat"
          >
            <Minus className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-white/80 hover:bg-white/10 hover:text-white"
            onClick={() => setOpen(false)}
            aria-label="Close chat"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-3 py-3 [scrollbar-width:thin]"
      >
        {messages.length === 0 ? (
          <div className="grid h-full place-items-center text-center text-xs text-white/50">
            No messages yet. Say hi to your focus crew.
          </div>
        ) : (
          messages.map((m) => {
            const p = profiles[m.user_id];
            const isMe = m.user_id === userId;
            const name = isMe ? "You" : p?.display_name || p?.username || "Anonymous";
            const cfg = (p?.avatar_config as AvatarConfig) ?? DEFAULT_AVATAR;
            const msgReactions = reactions.filter((r) => r.message_id === m.id);
            const grouped = msgReactions.reduce<Record<string, ReactionRow[]>>((acc, r) => {
              (acc[r.emoji] ||= []).push(r);
              return acc;
            }, {});
            return (
              <div
                key={m.id}
                className={`flex items-end gap-2 ${isMe ? "flex-row-reverse" : ""}`}
              >
                <div className="shrink-0 rounded-full bg-white/10 p-0.5 ring-1 ring-white/20">
                  <PixelAvatar config={cfg} size={28} />
                </div>
                <div className={`group/msg max-w-[75%] ${isMe ? "items-end" : "items-start"} flex flex-col`}>
                  <div className="text-[10px] uppercase tracking-wider text-white/50">
                    {name}
                  </div>
                  <div className={`relative mt-0.5 flex items-center gap-1 ${isMe ? "flex-row-reverse" : ""}`}>
                    <div
                      className={`break-words rounded-2xl px-3 py-1.5 text-sm leading-snug ${
                        isMe
                          ? "bg-primary text-primary-foreground rounded-br-md"
                          : "bg-white/10 text-white rounded-bl-md"
                      }`}
                    >
                      {m.content}
                    </div>
                    <Popover>
                      <PopoverTrigger asChild>
                        <button
                          type="button"
                          aria-label="Add reaction"
                          className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white/10 text-white/70 opacity-0 transition hover:bg-white/20 hover:text-white group-hover/msg:opacity-100 focus:opacity-100"
                        >
                          <SmilePlus className="h-3.5 w-3.5" />
                        </button>
                      </PopoverTrigger>
                      <PopoverContent
                        side="top"
                        align={isMe ? "end" : "start"}
                        className="flex w-auto gap-1 rounded-full border-white/15 bg-black/80 p-1.5 text-white backdrop-blur"
                      >
                        {QUICK_EMOJIS.map((e) => (
                          <button
                            key={e}
                            type="button"
                            onClick={() => toggleReaction(m.id, e)}
                            className="grid h-8 w-8 place-items-center rounded-full text-lg transition hover:scale-125 hover:bg-white/10"
                            aria-label={`React with ${e}`}
                          >
                            {e}
                          </button>
                        ))}
                      </PopoverContent>
                    </Popover>
                  </div>
                  {Object.keys(grouped).length > 0 && (
                    <div className={`mt-1 flex flex-wrap gap-1 ${isMe ? "justify-end" : "justify-start"}`}>
                      {Object.entries(grouped).map(([emoji, list]) => {
                        const mine = list.some((r) => r.user_id === userId);
                        return (
                          <button
                            key={emoji}
                            type="button"
                            onClick={() => toggleReaction(m.id, emoji)}
                            className={`flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-xs leading-none transition ${
                              mine
                                ? "border-primary/60 bg-primary/25 text-white"
                                : "border-white/15 bg-white/5 text-white/80 hover:bg-white/10"
                            }`}
                            aria-label={`${emoji} ${list.length}`}
                          >
                            <span className="text-sm leading-none">{emoji}</span>
                            <span className="tabular-nums">{list.length}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex items-center gap-2 border-t border-white/10 bg-black/40 p-2"
      >
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message..."
          maxLength={500}
          className="h-9 border-white/15 bg-white/10 text-sm text-white placeholder:text-white/40 focus-visible:ring-primary/60"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!draft.trim() || sending || !userId}
          className="h-9 w-9 shrink-0"
          aria-label="Send message"
        >
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}