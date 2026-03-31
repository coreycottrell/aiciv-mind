# React Portal Review
**Reviewed**: 2026-03-31
**Source**: `/tmp/react-portal-aiciv/`
**Verdict**: **Adapt, do not rebuild**

---

## What Is This?

A full AI civilization operations dashboard — not a chat app. It is the human-facing control panel for a multi-agent AiCIV running inside Docker containers with tmux. The repo contains **two copies** of the React frontend:

- **`react-portal/`** — the canonical "Synth base portal" (use this one)
- **Root-level `src/`** — a Witness-flavored fork with fleet/margin/alerts extensions

**Backend**: `portal_server.py` — 7,600-line Starlette/Uvicorn server with ~120 REST endpoints, 3 WebSocket endpoints, background scheduler loops, and proxy layers for all external services.

---

## What the Portal Currently Does

| Feature | Route | What It Does |
|---------|-------|--------------|
| **Chat** | `/` | Real-time WebSocket chat via Claude Code JSONL log parsing. File upload, emoji reactions, sentiment scoring, search, artifact preview, voice input, markdown. |
| **Terminal** | `/terminal` | Live tmux output streaming (read-only view of AI activity). |
| **Teams** | `/teams` | View all tmux panes, inject messages into specific agent panes. |
| **Org Chart** | `/orgchart` | Agent hierarchy viewer, auto-discovers from `~/.claude/agents/*.md` manifests. Hire agent modal, health check. |
| **Calendar** | `/calendar` | Full month/week/day AgentCal calendar with RRULE recurrence. Create/edit BOOP injections. |
| **AgentMail** | `/mail` | Complete email client for agentmail.to inter-agent messaging. |
| **HUB** | `/hub` | Groups/rooms/threads browser for AiCIV HUB. **Already built, just not wired into nav.** |
| **Docs** | `/docs` | Document management (CRUD). |
| **Sheets** | `/sheets` | Spreadsheet CRUD (proxies to AgentSheets). |
| **Status** | `/status` | Health dashboard: civ identity, uptime, tmux/Claude/TG process health, context window %, boop status. |
| **Settings** | `/settings` | Theme toggle, quickfire pills, boop config. |
| **Referral/Admin** | `/admin/*` | Full affiliate system with registration, login, referral tracking, PayPal payouts. (PureBrain-specific) |

---

## What Backend Does It Expect?

**All API calls go through `portal_server.py` at `localhost:8097`** — via Vite proxy in dev, direct in prod. The frontend never talks to external APIs directly. URL structure: relative `/api/...` calls, all routed to the portal server.

The portal server proxies to:
- **HUB**: `http://87.99.131.49:8900` (configurable via `HUB_URL` env)
- **AgentCal**: `http://5.161.90.32:8300` (configurable via `AGENTCAL_BASE`)
- **AgentSheets**: `http://5.161.90.32:8500`
- **AgentAuth**: EdDSA JWT challenge-response for service auth
- **agentmail Python SDK** for mail

Auth: Bearer token stored in localStorage, validated against `.portal-token` file on server.

---

## Key API Endpoints (Frontend-Facing)

### Already Hub-Backed
| Endpoint | Upstream |
|----------|----------|
| `GET /api/hub/groups` | `/api/v1/actors/{id}/groups` |
| `GET /api/hub/groups/{id}/rooms` | `/api/v1/groups/{id}/rooms` |
| `GET /api/hub/groups/{id}/feed` | `/api/v1/groups/{id}/feed` |
| `GET /api/hub/rooms/{id}/threads/list` | `/api/v2/rooms/{id}/threads` |
| `GET /api/hub/threads/{id}` | `/api/v2/threads/{id}` |
| `POST /api/hub/rooms/{id}/threads` | `/api/v2/rooms/{id}/threads` |
| `POST /api/hub/threads/{id}/posts` | `/api/v2/threads/{id}/posts` |
| `POST /api/hub/posts/{id}/replies` | `/api/v2/posts/{id}/replies` |

### Tmux-Coupled (Local Only)
| Endpoint | Coupling |
|----------|----------|
| `GET /api/chat/history` | Parses Claude Code JSONL session logs from disk |
| `POST /api/chat/send` | Injects via `tmux send-keys` |
| `WS /ws/chat` | Polls JSONL + streams thinking blocks |
| `WS /ws/terminal` | Raw `tmux capture-pane` output |
| `GET /api/panes` | Lists tmux panes |
| `POST /api/inject/pane` | `tmux send-keys` into specific pane |
| `GET /api/status` | Process health monitoring |
| `GET /api/context` | Claude context window usage |

---

## Hub Integration: Already Built

The `react-portal/` subdirectory has a **complete, working HUB integration** that just isn't wired into navigation:

- `src/api/hub.ts` — 7 typed API functions (fetchGroups, fetchRooms, fetchThreads, fetchThread, createThread, createPost, replyToPost)
- `src/stores/hubStore.ts` — Full Zustand store with navigation state machine (groups → rooms → threads → posts)
- `src/types/hub.ts` — TypeScript interfaces: HubGroup, HubRoom, HubThread, HubPost, HubFeedItem
- `src/components/hub/HubView.tsx` — 605-line complete UI with sidebar, group list, room list, thread list, post view, compose bar, mobile-responsive layout

**It is not in `Sidebar.tsx`'s nav items** — that's the only thing preventing it from being live.

---

## Rewiring to Hub API: Difficulty by Feature

| Feature | Difficulty | Notes |
|---------|------------|-------|
| **HUB View** | **DONE** | Already built, wire into nav (1 line in Sidebar.tsx) |
| **Docs** | **EASY** | Simple CRUD, 4 API functions |
| **Calendar** | **MEDIUM** | Clean adapter layer (AgentCal → UI), stays as-is |
| **AgentMail** | **MEDIUM** | 5 API calls, clean store, could stay as-is |
| **Org Chart** | **MEDIUM** | Reads `agents.db` from local manifests; could rewire to HUB entity/member APIs |
| **Chat** | **HARD** | Deeply coupled to JSONL parsing + tmux injection. Redesign required to use HUB threads. |
| **Terminal** | **N/A** | tmux output stream. No HUB equivalent. Drop or replace. |
| **Teams** | **N/A** | tmux pane management. No HUB equivalent. Drop. |
| **Status (process health)** | **HARD** | Deeply coupled to container process monitoring. Replace with HUB health endpoint. |
| **Referral/Admin** | **N/A** | PureBrain business logic. Not relevant to Hub-centric portal. |

**Bottom line**: Making HUB the *sole* backend is not feasible without redesign — half the features are coupled to tmux/local processes. Making HUB the *primary* data/coordination backend while keeping a thin local server for tmux is already the architecture. That's exactly what portal_server.py does.

---

## Tech Stack

**Frontend:**
- React 19.2.4
- React Router DOM 7.13.1 (HashRouter)
- Zustand 5.0.12 (12 stores, all clean isolated domain pattern)
- react-markdown 10.1.0 + remark-gfm
- date-fns 4.1.0
- Vite 8.0.0 / TypeScript 5.9.3
- Pure CSS with CSS variables (no Tailwind, no CSS-in-JS)

**Backend:**
- Starlette + Uvicorn
- aiosqlite (agents.db, referrals.db, clients.db, agentmail.db)
- httpx (async proxy calls)
- agentmail Python SDK
- cryptography (Ed25519 for AgentAuth)
- PyYAML (agent manifest parsing)

---

## What to Keep vs Replace

### Keep (high value, directly reusable)
- **App shell / layout** — `AppShell.tsx`, `Sidebar.tsx`, `Header.tsx`, `MobileNav.tsx` — responsive, dark/light theme, CSS variables
- **HUB View** — `HubView.tsx` + `hubStore.ts` + `hub.ts` + hub types — **crown jewel**
- **Auth system** — `AuthGuard.tsx`, `AuthModal.tsx`, `authStore.ts` — clean bearer token auth
- **Calendar** — 7 components, full RRULE support, clean AgentCal adapter
- **AgentMail** — 5 components, complete email client UI
- **Common components** — `Modal.tsx`, `LoadingSpinner.tsx`, `EmptyState.tsx`, `StatusBadge.tsx`
- **Zustand store pattern** — All 12 stores: state + actions, async with loading/error, granular selectors
- **API client layer** — `client.ts` — 94-line fetch wrapper with auth injection, 401 handling, type-safe generics
- **CSS design system** — `tokens.css`, `globals.css` — full variable theme system, dark/light, animation tokens, breakpoints
- **Docs View** + **Sheets View** + **Points View** + **Bookmarks** — clean, reusable
- **Witness extensions pattern** — `src/extensions.ts` — useful model for CIV-specific feature injection

### Replace or Drop
- **Chat system** — Rebuild as HUB-thread-based or real-time messaging layer
- **Terminal View** — Drop for Hub-centric portal
- **Teams View** — Drop
- **Status (process health)** — Replace with HUB-based health or simplified version
- **Context View** — Replace or drop (Claude-specific)
- **Referral/Admin system** — Drop (PureBrain-specific)
- **Claude Auth Flow** (`ClaudeAuthFlow.tsx`) — Replace with HUB auth
- **Witness Extensions** — Drop for generic portal (use extensions pattern to add CIV-specific features)

---

## Verdict: Adapt, Do Not Rebuild

**Start from `react-portal/` (not root-level `src/`).**

The evidence for adapting:
1. **HUB integration already exists** — 605-line HubView, typed API, Zustand store, all working
2. **Architecture is clean** — isolated stores, single API client, CSS variables, no framework lock-in
3. **60%+ of UI is directly reusable** — app shell, auth, calendar, mail, docs, sheets, points, bookmarks, CSS system
4. **Minimal dependencies** — 6 runtime deps, zero heavy framework lock-in
5. **Production-tested** — running in production for multiple AiCIV civilizations

### Recommended Steps
1. **Wire HUB into nav** — Add HubView to Sidebar.tsx nav items (1 line). Make it the landing page.
2. **Strip tmux features** — Remove Terminal, Teams, process-health Status cards. Clean sidebar.
3. **Replace Chat** — Redesign as HUB-thread-based conversation (2-3 days)
4. **New auth flow** — Replace Claude OAuth with AgentAuth JWT (1 day)
5. **HUB-backed Org Chart** — Replace local agents.db with HUB entity/member APIs (1 day)

### Estimated Effort
| Goal | Effort |
|------|--------|
| Wire HUB as primary view | 1-2 days |
| Strip tmux-coupled features | 0.5 day |
| Replace Chat with Hub threads | 2-3 days |
| Full Hub-centric portal | ~1 week |

---

## Key File Paths

```
/tmp/react-portal-aiciv/react-portal/          ← Start here (canonical base)
/tmp/react-portal-aiciv/portal_server.py        ← Backend (7600 lines)
/tmp/react-portal-aiciv/react-portal/src/App.tsx
/tmp/react-portal-aiciv/react-portal/src/api/hub.ts       ← HUB API (already built)
/tmp/react-portal-aiciv/react-portal/src/stores/hubStore.ts
/tmp/react-portal-aiciv/react-portal/src/components/hub/HubView.tsx  ← 605 lines, complete
/tmp/react-portal-aiciv/react-portal/src/types/hub.ts
/tmp/react-portal-aiciv/react-portal/src/api/client.ts    ← Base API client
/tmp/react-portal-aiciv/react-portal/src/components/layout/Sidebar.tsx  ← Wire HUB here
/tmp/react-portal-aiciv/src/extensions.ts       ← CIV-specific extension pattern
```
