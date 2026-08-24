# Frontend Spec — Pick-a-Recipe React SPA

Single source of truth for everyone working in `ui/frontend`. Read this before touching code.

## Stack

- **Vite + React 19 + TypeScript** (strict, `erasableSyntaxOnly`, no unused locals/params)
- **Tailwind CSS v4** (`@import "tailwindcss"` in `src/index.css`; NO tailwind.config file)
- **shadcn/ui**, style `radix-nova` (Lucide icons, Geist font). Components live in `src/components/ui/*` — installed via CLI, never hand-edited
- **TanStack Query** (`@tanstack/react-query`) for all server state; **socket events invalidate queries**
- **React Router v7** (`BrowserRouter`) — routes: `/login`, `/` , `/jobs/:jobId`, `/tasks`, `/settings`
- **sonner** toasts (`toast.success/error` from `'sonner'`)
- **socket.io-client** singleton via `@/lib/socket`

## Hard conventions

1. **Named exports only** for pages/components you author (`export function HomePage()`).
2. **No default exports**, no `React.FC`, no forwardRef (shadcn primitives already handle refs).
3. **No type suppression**: never `as any`, `@ts-ignore`, `@ts-expect-error`.
4. **No comments** unless truly load-bearing (type-system workarounds, non-obvious protocol details).
5. **Dark mode first**: respect tokens via Tailwind classes (`bg-card`, `text-muted-foreground`, …). Never hardcode hex colors. Light mode must look right too.
6. **All colors/spacing via design tokens.** Radius via `rounded-lg/xl` etc.
7. Data fetching through `api.*` from `@/lib/api`. Never raw `fetch`.
8. Real-time through `useSocketEvent` / `useJobRoom` from `@/lib/socket`.
9. Query invalidation over manual cache mutation. On socket events, call `queryClient.invalidateQueries({queryKey: [...]})`.

## Contract gotchas (from ui/app.py — do not "fix" these)

- Socket transition events are **dynamic**: `job_running`, `job_awaiting_approval`, `job_uploading`, `job_completed`, `job_failed`, `job_cancelled`, `job_expired` — payloads `{job_id, status, previous_status, reason}`.
- Completion event is **`job_complete`** (not `job_completed`) with `{job_id, recipe, llm_tokens_used}`.
- Config values are **string booleans** (`"true"`/`"false"`) — coerce with `=== 'true'`.
- `recipe_data.recipeIngredients` = structured objects (plural key); `recipeIngredient` = flat strings (singular key). Both exist.
- Thumbnails: prefer base64 `thumbnail_data` / `image_data` fields (`data:image/jpeg;base64,...` prefix needed when rendering). `thumbnail_path` is unreliable after restarts.
- `job.queue_position` present only while `queued`; `pending_upload_id` only while `awaiting_approval`.

## Behavior sources (port faithfully, restyle freely)

| New page | Port behavior from |
|---|---|
| `src/pages/login-page.tsx` | `ui/templates/login.html` |
| `src/pages/home-page.tsx` | `ui/templates/index.html` + `ui/static/js/main.js` |
| `src/pages/job-page.tsx` | `ui/templates/job.html` + `ui/static/js/job-page.js` |
| `src/pages/tasks-page.tsx` | `ui/templates/tasks.html` + `ui/static/js/tasks.js` |
| `src/pages/settings-page.tsx` | `ui/templates/settings.html` (+ its inline script) |

Read those files before implementing. Preserve every user-visible capability (batch input limits of 50, polling fallbacks, confirm flows, admin-only controls, share-target auto-start via `sessionStorage` handoff, PWA install prompt on login page).

## Shared components (owned by the home-page task)

- `src/components/job-card.tsx` → `<JobCard job={Job} onCancel={(id)=>void} href?: string />`
  Pipeline stage tracker (7 stages: info→download→transcribe→visual→image→evaluate→upload), Progress bar, queue-position Badge, status Badge variants (queued=secondary, running=default, awaiting_approval=warning-ish outline amber, uploading=default, failed=destructive, cancelled/expired=outline muted, completed=success-ish emerald), error Alert when failed, cancel Button (destructive-outline) while cancellable, optional link to `/jobs/:id`.
- `src/components/recipe-view.tsx` → `<RecipeView recipe={RecipeData} />`
  Name, description, meta row (yield/prep/cook/total from ISO-8601 durations), two-column ingredients (structured `recipeIngredients` fallback `recipeIngredient`) + numbered instructions (handle string | HowToStep | HowToSection), nutrition chips if present, category/cuisine/keyword badges.
- `src/components/image-picker.tsx` → `<ImagePicker images={CandidateImage[]} value={number} onChange={(i)=>void} />`
  Selectable candidate-image grid with best-image highlight ring.

Tasks/home pages MUST reuse these instead of re-implementing.

## UX bar (shadcn aesthetic)

- Cards with `CardHeader/CardContent`; forms with `Label`+`Input`; actions as `Button` variants; destructive confirmations via `AlertDialog` (never browser `confirm`); dropdown kebab menus via `DropdownMenu`; empty states with icon + muted text; loading via `Skeleton`.
- Responsive: usable at 375px. Sidebar collapses via built-in `SidebarTrigger`.
- Toast feedback on every mutating action (success + failure), including bulk ops summary counts.
