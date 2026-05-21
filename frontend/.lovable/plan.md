# Focus Room — Build Plan

Pixel/isometric 2.5D style. Focus scores mocked for now. I'll wait for the PDF before locking visual direction.

## Phase 1 — Foundation (UI shell, auth, dashboard)
- Enable Lovable Cloud (auth, DB, storage, realtime).
- Email/password + Google sign-in. `profiles` table + auto-create trigger.
- Design system in `src/styles.css` matching the soft, friendly look implied by the PDF (warm neutrals, rounded cards, playful accents).
- Routes:
  - `/login`, `/signup`
  - `/_authenticated/dashboard` — sidebar + 5 tabs as nested routes:
    - `/dashboard/overview` — profile card
    - `/dashboard/sessions` — create/join room
    - `/dashboard/statistics` — charts (Recharts)
    - `/dashboard/tasks` — Current session tasks + Personal backlog
    - `/dashboard/library` — uploaded files list
- Avatar editor (2.5D pixel customization: hair, skin, outfit, accessory).

## Phase 2 — Rooms (2.5D, single-player)
- 5 environments: cafe, library, garden, dorm, train (isometric tile maps, pixel art).
- Render with HTML canvas / PixiJS (lighter than Three.js for 2.5D).
- Click-to-sit on chairs/benches; close-up view of seated avatar.
- Session timer (30s–3h), session code generator, copy-to-clipboard.
- Mocked focus score floating above avatar head (random walk for now).
- Session-complete screen with leaderboard + trophy.

## Phase 3 — Realtime multiplayer
- Supabase Realtime presence channel keyed by session code.
- Broadcast: avatar position, chair, focus score, chat messages.
- Right-side chat panel (collapsible). Slash command `/task <text>` → adds to Current session tasks.
- Shared library uploads via Supabase Storage (private bucket, signed URLs, 24h TTL cleanup job, 2GB per-user quota check).

## Phase 4 — Mock focus scoring
- Webcam permission prompt; render local preview.
- Stub scorer producing 0–100 score every few seconds (clearly labeled "simulated").
- Persist per-session focus history → Statistics charts + leaderboard.
- Hook designed so a real CNN (TF.js / API endpoint) can drop in later.

## Data model
- `profiles`, `avatars`, `sessions`, `session_participants`, `focus_samples`, `tasks`, `chat_messages`, `library_files`.
- RLS on every table; `user_roles` separate table (no role on profiles).

## Tech choices
- TanStack Start + Lovable Cloud (already scaffolded).
- PixiJS for 2.5D scenes.
- Recharts for stats. Sonner for toasts.

## Out of scope for v1
- Real CNN focus model (mocked).
- Voice chat, screen share.
- Mobile-optimized 3D controls.

---

**Next step:** Once you re-upload the PDF, I'll start Phase 1. Reply with "go" to confirm the plan, or tell me what to change.