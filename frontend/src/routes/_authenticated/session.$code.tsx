import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { PixelAvatar, DEFAULT_AVATAR, type AvatarConfig } from "@/components/PixelAvatar";
import { LogOut, Copy, Armchair } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import { SessionChat } from "@/components/SessionChat";
import cafeImg from "@/assets/room-cafe.jpg";
import libraryImg from "@/assets/room-library.jpg";
import gardenImg from "@/assets/room-garden.jpg";
import dormImg from "@/assets/room-dorm.jpg";
import trainImg from "@/assets/room-train.jpg";
import { useEyeCapture } from "@/hooks/use-eye-capture";
import { FocusHUD, ScoreBadge, useParticipantScores } from "@/components/FocusHUD";

const ROOM_IMAGES: Record<string, string> = {
  cafe: cafeImg,
  library: libraryImg,
  garden: gardenImg,
  dorm: dormImg,
  train: trainImg,
};

// Isometric tile grid configuration. Seats use tile coordinates (col, row)
// inside a COLS x ROWS floor; positions are projected to a tilted 3D plane.
const COLS = 9;
const ROWS = 7;
const TILE = 72; // px, square tile in floor-space
const TILT_X = 58; // degrees — how steeply the camera looks down

type Seat = { col: number; row: number; label: string };
const SEATS: Record<string, Seat[]> = {
  cafe: [
    { col: 1, row: 1, label: "Window seat" },
    { col: 3, row: 1, label: "Window seat" },
    { col: 5, row: 1, label: "Counter" },
    { col: 7, row: 1, label: "Counter" },
    { col: 2, row: 4, label: "Lounge" },
    { col: 6, row: 4, label: "Lounge" },
  ],
  library: [
    { col: 1, row: 1, label: "Desk 1" },
    { col: 3, row: 1, label: "Desk 2" },
    { col: 5, row: 1, label: "Desk 3" },
    { col: 7, row: 1, label: "Desk 4" },
    { col: 2, row: 4, label: "Study nook" },
    { col: 6, row: 4, label: "Study nook" },
  ],
  garden: [
    { col: 1, row: 1, label: "Bench" },
    { col: 3, row: 1, label: "Bench" },
    { col: 5, row: 1, label: "Picnic" },
    { col: 7, row: 1, label: "Picnic" },
    { col: 2, row: 4, label: "Shade" },
    { col: 6, row: 4, label: "Shade" },
  ],
  dorm: [
    { col: 1, row: 1, label: "Desk" },
    { col: 4, row: 1, label: "Bed" },
    { col: 7, row: 1, label: "Floor cushion" },
    { col: 2, row: 4, label: "Beanbag" },
    { col: 4, row: 4, label: "Beanbag" },
    { col: 7, row: 4, label: "Rug" },
  ],
  train: [
    { col: 1, row: 1, label: "Window" },
    { col: 3, row: 1, label: "Aisle" },
    { col: 5, row: 1, label: "Aisle" },
    { col: 7, row: 1, label: "Window" },
    { col: 2, row: 4, label: "Table seat" },
    { col: 6, row: 4, label: "Table seat" },
  ],
};

// Per-space floor palette (two-tone checker + accent for seat pedestals).
const FLOOR_THEME: Record<string, { a: string; b: string; pedestal: string; rim: string }> = {
  cafe: { a: "#5b3a26", b: "#7a4f33", pedestal: "#d9a066", rim: "#fff3" },
  library: { a: "#2b3a55", b: "#384a6b", pedestal: "#8aa6d6", rim: "#fff2" },
  garden: { a: "#2f5a35", b: "#3d6e43", pedestal: "#a8d18d", rim: "#fff3" },
  dorm: { a: "#5a3a55", b: "#6f4a6a", pedestal: "#e7a7c7", rim: "#fff3" },
  train: { a: "#2f3a44", b: "#3d4a56", pedestal: "#9cc0d6", rim: "#fff2" },
};

export const Route = createFileRoute("/_authenticated/session/$code")({
  head: () => ({ meta: [{ title: "In Session — Focus Room" }] }),
  component: SessionPage,
});

type SessionRow = {
  id: string;
  code: string;
  space: string;
  duration_seconds: number;
  host_id: string;
  started_at: string | null;
};
type Participant = {
  user_id: string;
  chair_index: number | null;
  profile: { username: string; display_name: string | null; avatar_config: AvatarConfig } | null;
};

function fmt(s: number) {
  if (s < 0) s = 0;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

function SessionPage() {
  const { code } = Route.useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [session, setSession] = useState<SessionRow | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const [loading, setLoading] = useState(true);
  const [sitting, setSitting] = useState(false);
  const {
    score,
    state: eyeState,
    cameraReady,
  } = useEyeCapture({
    sessionId: session?.id ?? "",
    userId: user?.id ?? "",
    enabled: !!session,
  });
  const participantScores = useParticipantScores(session?.id ?? "");

  // Load session + participants
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data: s } = await supabase
        .from("sessions")
        .select("*")
        .eq("code", code)
        .maybeSingle();
      if (cancelled) return;
      if (!s) {
        toast.error("Session not found");
        navigate({ to: "/dashboard/sessions" });
        return;
      }
      setSession(s as SessionRow);
      // Start if host and not started
      if (user && s.host_id === user.id && !s.started_at) {
        await supabase
          .from("sessions")
          .update({ started_at: new Date().toISOString(), status: "active" })
          .eq("id", s.id);
        const { data: s2 } = await supabase
          .from("sessions")
          .select("*")
          .eq("id", s.id)
          .maybeSingle();
        if (s2 && !cancelled) setSession(s2 as SessionRow);
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [code, user, navigate]);

  const loadParticipants = async (sessionId: string) => {
    const { data: parts } = await supabase
      .from("session_participants")
      .select("user_id, chair_index")
      .eq("session_id", sessionId)
      .is("left_at", null);
    if (!parts) return;
    const ids = parts.map((p) => p.user_id);
    if (ids.length === 0) {
      setParticipants([]);
      return;
    }
    const { data: profiles } = await supabase
      .from("profiles")
      .select("id, username, display_name, avatar_config")
      .in("id", ids);
    setParticipants(
      parts.map((p) => ({
        user_id: p.user_id,
        chair_index: (p as any).chair_index ?? null,
        profile: (profiles?.find((pr) => pr.id === p.user_id) as any) ?? null,
      })),
    );
  };

  useEffect(() => {
    if (!session) return;
    loadParticipants(session.id);
    const ch = supabase
      .channel(`session-${session.id}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "session_participants",
          filter: `session_id=eq.${session.id}`,
        },
        () => loadParticipants(session.id),
      )
      .subscribe();
    return () => {
      supabase.removeChannel(ch);
    };
  }, [session]);

  // Tick
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const remaining = useMemo(() => {
    if (!session?.started_at) return session?.duration_seconds ?? 0;
    const end = new Date(session.started_at).getTime() + session.duration_seconds * 1000;
    return Math.max(0, Math.floor((end - now) / 1000));
  }, [session, now]);

  const leave = async () => {
    if (session && user) {
      await supabase
        .from("session_participants")
        .update({ left_at: new Date().toISOString() })
        .eq("session_id", session.id)
        .eq("user_id", user.id);
    }
    navigate({ to: "/dashboard/sessions" });
  };

  const sit = async (chairIndex: number) => {
    if (!session || !user || sitting) return;
    // prevent taking an occupied chair
    if (participants.some((p) => p.chair_index === chairIndex && p.user_id !== user.id)) {
      toast.error("That seat is taken");
      return;
    }
    setSitting(true);
    const { error } = await supabase
      .from("session_participants")
      .update({ chair_index: chairIndex })
      .eq("session_id", session.id)
      .eq("user_id", user.id);
    setSitting(false);
    if (error) {
      toast.error(error.message);
      return;
    }
  };

  const standUp = async () => {
    if (!session || !user) return;
    await supabase
      .from("session_participants")
      .update({ chair_index: null })
      .eq("session_id", session.id)
      .eq("user_id", user.id);
  };

  if (loading || !session) {
    return (
      <div className="grid min-h-screen place-items-center text-muted-foreground">
        Loading session...
      </div>
    );
  }

  const bg = ROOM_IMAGES[session.space] ?? cafeImg;
  const done = remaining === 0 && !!session.started_at;
  const seats = SEATS[session.space] ?? SEATS.cafe;
  const me = participants.find((p) => p.user_id === user?.id);
  const myChair = me?.chair_index ?? null;
  const mySeatLabel = myChair != null ? seats[myChair]?.label : null;

  return (
    <div className="relative min-h-screen overflow-hidden">
      <img src={bg} alt="" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-b from-[#0c0a07]/60 via-[#0c0a07]/35 to-[#0c0a07]/80" />
      <div className="absolute inset-0 mix-blend-soft-light bg-[var(--gradient-warm)] opacity-30" />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-6xl flex-col p-6 text-white">
        <header className="flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-white/70">{session.space}</div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-lg tracking-wider">{session.code}</span>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-white hover:bg-white/10"
                onClick={() => {
                  navigator.clipboard.writeText(session.code);
                  toast.success("Copied");
                }}
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-black/40 px-4 py-1.5 font-mono text-base tabular-nums backdrop-blur">
              {done ? "00:00" : fmt(remaining)}
              <FocusHUD
                sessionId={session.id}
                myUserId={user?.id ?? ""}
                myScore={score}
                myState={eyeState}
                cameraOn={cameraReady}
              />
            </div>
            <Button
              variant="outline"
              onClick={leave}
              className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white"
            >
              <LogOut className="mr-2 h-4 w-4" /> Leave
            </Button>
          </div>
        </header>

        {/* Isometric 2.5D room stage */}
        <IsoStage
          space={session.space}
          seats={seats}
          participants={participants}
          userId={user?.id}
          myChair={myChair}
          onSit={sit}
          sitting={sitting}
          myAvatar={(me?.profile?.avatar_config as AvatarConfig) ?? DEFAULT_AVATAR}
          myName={me?.profile?.display_name || me?.profile?.username || "You"}
          participantScores={participantScores}
        />

        {/* Bottom HUD: prompt or close-up */}
        <div className="relative mt-4">
          <div className="flex items-end justify-between gap-4">
            {myChair == null ? (
              <div className="rounded-2xl bg-black/55 px-5 py-3 text-sm backdrop-blur-md">
                Pick a seat to settle in for your focus session.
              </div>
            ) : (
              <div
                key={myChair}
                className="animate-closeup-in flex items-center gap-4 rounded-3xl bg-black/55 p-4 backdrop-blur-md"
              >
                <div className="animate-sit-down rounded-2xl bg-white/10 p-2">
                  <PixelAvatar
                    config={(me?.profile?.avatar_config as AvatarConfig) ?? DEFAULT_AVATAR}
                    size={120}
                  />
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-[0.25em] text-white/60">
                    Seated · close-up
                  </div>
                  <div className="mt-1 font-display text-xl font-semibold">
                    {me?.profile?.display_name || me?.profile?.username || "You"}
                  </div>
                  <div className="text-xs text-white/70">{mySeatLabel}</div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={standUp}
                    className="mt-2 h-7 border-white/30 bg-white/10 text-xs text-white hover:bg-white/20 hover:text-white"
                  >
                    Stand up
                  </Button>
                </div>
              </div>
            )}

            <div className="rounded-2xl bg-black/55 px-4 py-2 text-xs backdrop-blur-md">
              In the room · <span className="font-semibold">{participants.length}</span>
            </div>
          </div>

          {done && (
            <div className="pointer-events-none mt-4 grid place-items-center">
              <div className="rounded-full bg-white/15 px-6 py-3 text-sm backdrop-blur">
                Session complete — great work.
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Floating chat panel on the right */}
      <SessionChat sessionId={session.id} userId={user?.id} />
    </div>
  );
}

function IsoStage({
  space,
  seats,
  participants,
  userId,
  myChair,
  onSit,
  sitting,
  myAvatar,
  myName,
  participantScores,
}: {
  space: string;
  seats: Seat[];
  participants: Participant[];
  userId: string | undefined;
  myChair: number | null;
  onSit: (i: number) => void;
  sitting: boolean;
  myAvatar: AvatarConfig;
  myName: string;
  participantScores: Record<string, { score: number; state: string }>;
}) {
  const theme = FLOOR_THEME[space] ?? FLOOR_THEME.cafe;
  const floorW = COLS * TILE;
  const floorH = ROWS * TILE;

  // tile (col,row) -> floor-space pixel (top-left of tile, centered later)
  const tilePos = (col: number, row: number) => ({
    x: col * TILE + TILE / 2 - floorW / 2,
    y: row * TILE + TILE / 2 - floorH / 2,
  });

  const tiles: { col: number; row: number; key: string }[] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) tiles.push({ col: c, row: r, key: `${c}-${r}` });
  }

  return (
    <TooltipProvider delayDuration={120}>
      <div className="relative mt-6 flex-1" style={{ perspective: "1400px" }}>
        {/* ambient floor vignette */}
        <div className="pointer-events-none absolute inset-0 rounded-3xl bg-[radial-gradient(ellipse_at_center,transparent_30%,#000a_90%)]" />

        {/* tilted floor plane */}
        <div
          className="absolute left-1/2 top-1/2"
          style={{
            width: floorW,
            height: floorH,
            transformStyle: "preserve-3d",
            transform: `translate(-50%, -35%) rotateX(${TILT_X}deg)`,
          }}
        >
          {/* checker tiles */}
          <div
            className="absolute inset-0 rounded-[18px] shadow-[0_30px_60px_-10px_rgba(0,0,0,0.55)]"
            style={{
              background: `
              linear-gradient(${theme.a}, ${theme.a}),
              repeating-conic-gradient(${theme.a} 0% 25%, ${theme.b} 0% 50%)
            `,
              backgroundSize: `100% 100%, ${TILE * 2}px ${TILE * 2}px`,
              backgroundPosition: "0 0, 0 0",
              backgroundBlendMode: "normal, normal",
            }}
          />
          {/* tile grid lines */}
          <svg
            className="absolute inset-0 h-full w-full opacity-30"
            viewBox={`0 0 ${floorW} ${floorH}`}
            preserveAspectRatio="none"
          >
            {Array.from({ length: COLS + 1 }).map((_, i) => (
              <line
                key={`v${i}`}
                x1={i * TILE}
                y1={0}
                x2={i * TILE}
                y2={floorH}
                stroke={theme.rim}
                strokeWidth={1}
              />
            ))}
            {Array.from({ length: ROWS + 1 }).map((_, i) => (
              <line
                key={`h${i}`}
                x1={0}
                y1={i * TILE}
                x2={floorW}
                y2={i * TILE}
                stroke={theme.rim}
                strokeWidth={1}
              />
            ))}
          </svg>

          {/* "Entering the room" avatar — visible only while the user hasn't
            picked a seat yet. Sits at the front-center of the floor with an
            entrance + idle bob so the user feels present in the space. */}
          {userId && myChair == null && (
            <div
              className="pointer-events-none absolute left-1/2 top-1/2"
              style={{
                transform: `translate(-50%, -50%) translate3d(0px, ${((ROWS - 1) * TILE) / 2 - TILE / 2}px, 0)`,
                transformStyle: "preserve-3d",
                zIndex: 100 + ROWS * 10 + COLS,
              }}
            >
              <div
                className="absolute left-1/2 top-1/2 h-10 w-16 -translate-x-1/2 -translate-y-1/2 rounded-[50%] bg-black/45 blur-md"
                style={{ zIndex: -1 }}
              />
              <div
                className="animate-avatar-enter"
                style={{
                  transform: `rotateX(-${TILT_X}deg) translateY(-28px)`,
                  transformOrigin: "bottom center",
                }}
              >
                <div className="animate-avatar-bob flex flex-col items-center">
                  <div className="rounded-2xl bg-white/15 p-1 ring-1 ring-white/40 backdrop-blur shadow-[0_0_24px_rgba(255,255,255,0.2)]">
                    <PixelAvatar config={myAvatar} size={64} />
                  </div>
                  <div className="mt-1 max-w-[110px] truncate rounded-full bg-primary/80 px-2 py-0.5 text-[10px] text-primary-foreground">
                    {myName} · arriving
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* seats — sit ON the floor (children counter-rotate to stand up) */}
          {seats
            .map((seat, i) => ({ seat, i }))
            // Painter's algorithm: render back rows first so front rows
            // (higher row index) naturally overlap them. Tie-break by column
            // so left-to-right stacking is also deterministic.
            .sort((a, b) => a.seat.row - b.seat.row || a.seat.col - b.seat.col)
            .map(({ seat, i }) => {
              const occupant = participants.find((p) => p.chair_index === i);
              const isMe = occupant?.user_id === userId;
              const cfg = (occupant?.profile?.avatar_config as AvatarConfig) ?? DEFAULT_AVATAR;
              const name = occupant?.profile?.display_name || occupant?.profile?.username || "";
              const canClick = !occupant && myChair == null;
              const { x, y } = tilePos(seat.col, seat.row);
              const tipText = occupant
                ? `${isMe ? "You" : name || "Anonymous"} · seated at ${seat.label}`
                : myChair != null
                  ? `${seat.label} · stand up first to switch seats`
                  : `Sit at ${seat.label}`;

              return (
                <div
                  key={i}
                  className="absolute left-1/2 top-1/2"
                  style={{
                    transform: `translate(-50%, -50%) translate3d(${x}px, ${y}px, 0)`,
                    transformStyle: "preserve-3d",
                    // Depth hint for the 2D stacking pass: rows closer to the
                    // camera (higher row index) sit on top of rows behind them.
                    // Columns add a tiny offset so adjacent seats in the same
                    // row stack deterministically left-over-right.
                    zIndex: 100 + seat.row * 10 + seat.col,
                  }}
                >
                  {/* shadow disc on floor */}
                  <div
                    className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-16 -translate-x-1/2 -translate-y-1/2 rounded-[50%] bg-black/45 blur-md"
                    style={{ zIndex: -1 }}
                  />
                  {/* pedestal tile highlight */}
                  <div
                    className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-md transition-all duration-200 ${
                      canClick ? "group-hover/seat:scale-110 group-hover/seat:brightness-125" : ""
                    } ${occupant ? (isMe ? "ring-2 ring-primary/80" : "ring-1 ring-white/40") : ""}`}
                    style={{
                      width: TILE - 8,
                      height: TILE - 8,
                      background: occupant ? `${theme.pedestal}55` : `${theme.pedestal}33`,
                      border: `1px solid ${theme.pedestal}aa`,
                      boxShadow: `inset 0 0 16px ${theme.pedestal}55`,
                    }}
                  />
                  {/* upright content */}
                  <Tooltip delayDuration={120}>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        disabled={!canClick || sitting}
                        onClick={() => canClick && onSit(i)}
                        className={`group/seat relative block transition-transform duration-200 ${
                          canClick
                            ? "cursor-pointer hover:-translate-y-1 focus-visible:-translate-y-1 focus-visible:outline-none"
                            : occupant
                              ? "cursor-default"
                              : "cursor-not-allowed"
                        }`}
                        style={{
                          transform: `rotateX(-${TILT_X}deg) translateY(-28px)`,
                          transformOrigin: "bottom center",
                        }}
                        aria-label={tipText}
                      >
                        {occupant ? (
                          <div
                            key={`occ-${i}-${occupant.user_id}`}
                            className={`flex flex-col items-center ${isMe ? "animate-sit-down" : ""}`}
                          >
                            <div
                              className={`rounded-2xl p-1 backdrop-blur transition ${
                                isMe
                                  ? "bg-primary/40 ring-2 ring-primary shadow-[0_0_24px_rgba(255,255,255,0.25)]"
                                  : "bg-white/15 ring-1 ring-white/30"
                              }`}
                            >
                              <div className="flex flex-col items-center">
                                <ScoreBadge
                                  score={participantScores[occupant.user_id]?.score ?? 50}
                                  state={participantScores[occupant.user_id]?.state ?? "focused"}
                                  name={isMe ? "You" : name || "Anonymous"}
                                />
                                <PixelAvatar config={cfg} size={56} />
                                <div className="mt-1 max-w-[90px] truncate rounded-full bg-black/60 px-2 py-0.5 text-[10px] text-white">
                                  {isMe ? "You" : name || "Anonymous"}
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="flex flex-col items-center gap-1">
                            <div
                              className={`grid h-11 w-11 place-items-center rounded-xl border backdrop-blur transition-all duration-200 ${
                                canClick
                                  ? "border-white/40 bg-white/10 group-hover/seat:border-primary group-hover/seat:bg-primary/30 group-hover/seat:shadow-[0_0_20px_rgba(255,255,255,0.35)] group-focus-visible/seat:border-primary group-focus-visible/seat:bg-primary/30"
                                  : "border-white/20 bg-white/5 opacity-70"
                              }`}
                            >
                              <Armchair
                                className={`h-5 w-5 transition-colors ${
                                  canClick
                                    ? "text-white/90 group-hover/seat:text-white"
                                    : "text-white/60"
                                }`}
                              />
                            </div>
                            <div
                              className={`rounded-full px-2 py-0.5 text-[10px] transition ${
                                canClick
                                  ? "bg-black/55 text-white/85 group-hover/seat:bg-primary group-hover/seat:text-primary-foreground"
                                  : "bg-black/40 text-white/60"
                              }`}
                            >
                              {seat.label}
                            </div>
                          </div>
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs">
                      {tipText}
                    </TooltipContent>
                  </Tooltip>
                </div>
              );
            })}
        </div>
      </div>
    </TooltipProvider>
  );
}
