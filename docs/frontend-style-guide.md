# Frontend style guide

How the frontend is built and changed. Read with [`../design.md`](../design.md) (brand tokens),
[`ui-design-guidelines.md`](ui-design-guidelines.md) (anti-slop workflow) and
[decision 0021](decisions/0021-rounded-chat-first-frontend.md) (rounded, chat-first look).
Where they disagree, 0021 wins on shape and elevation; `design.md` wins on colour and type.

## Stack

Vite, React 19, TypeScript, Tailwind v4, shadcn/ui (style `base-nova`, **Base UI** primitives, not Radix), lucide icons.
Components live in `frontend/src/components/ui/`, features in `src/features/<name>/`, shared chrome in
`src/components/layout/`. The UI talks only to `/api` through `src/lib/api.ts`.

## Look and feel

| Aspect | Rule |
|---|---|
| Colour | White canvas, `canvas-tint` (#f6f7f9) behind white cards. BMW Blue (`primary`) is the only action colour. Semantic colours only for state. No gradients, glows, glass. |
| Type | Inter Variable. Body 400, headings 600, no negative tracking beyond `-0.01em` on headings. |
| Shape | `--radius` 0.75rem. Cards `rounded-2xl`, inputs and buttons `rounded-xl`, chat bubbles and composer `rounded-3xl`, chips and avatars pills. |
| Elevation | `shadow-xs` on cards, `shadow-sm` on primary buttons, `shadow-md` on the composer and sign-in panel only. |
| Icons | lucide only, `size-4` inline, `size-5` in headings. Decorative icons get `aria-hidden`. Never hand-draw SVG. |
| Spacing | 4px scale. Page gutters `px-4 sm:px-8`. Chat column `max-w-3xl`, pages `max-w-6xl`. |
| Motion | Only `.rise` (new messages) and `.typing-dot`. Both are disabled under `prefers-reduced-motion`. |
| Copy | Plain sentences, no em or en dashes, one verb per action ("Send", "Search", "Sign out"). No invented data: examples are labelled as examples. |

## Layout patterns

- **Shell:** `App.tsx` holds a 288px sidebar (`components/layout/Sidebar.tsx`) and the main column. Below `md` the sidebar is a `Sheet`.
- **Chat view:** `h-dvh` column, scrolling thread, composer pinned at the bottom. The empty state centres the composer.
- **Content pages:** wrap in `PageShell` (icon, title, one-line description, scrolling body on `canvas-tint`).
- **State shared across views** (chat list, open chat) lives in `features/research/chat-store.tsx`. Keep other state local.
- Every async view has loading (layout-matched `Skeleton`), empty, error (`role="alert"`) and success states.

## Building a UI change: the workflow

1. **Read** `design.md`, `ui-design-guidelines.md` and this file. Skim the nearest existing feature for conventions.
2. **Pick components with the shadcn MCP** before writing markup:
   - `search_items_in_registries` / `list_items_in_registries` to find a component or block,
   - `view_items_in_registries` and `get_item_examples_from_registries` to read source and usage,
   - `get_add_command_for_items` for the install command, then run `npx shadcn@latest add @shadcn/<name>`.
   - If the MCP is not connected, the CLI does the same (`npx shadcn@latest search`, `view`, `add`). Do not recreate a shadcn component by hand.
3. **Use the design skills.** Invoke the `frontend-design` skill for hierarchy and typography choices and the `vercel:shadcn`
   skill for composition and theming. State the reading ("Reading this as: <page> for <audience>...") from the guidelines.
4. **Check what the CLI generated** (see pitfalls). Adjust the new file to the tokens above instead of overriding it at every call site.
5. **Iterate visually with Playwright.** Start the dev server, mock `/api` with `page.route` (reuse `tests/helpers.ts`:
   `withSession`, `json`), screenshot desktop (1440x1000) and mobile (iPhone 13) to the scratchpad, look at the images, fix, repeat.
   Do at least: empty state, populated state, working/loading, error, and the mobile menu. Delete throwaway screenshot specs afterwards.
6. **Verify:** `npm run build` (type-check), `npx oxlint`, `npx playwright test` (desktop and mobile, includes an axe WCAG AA check on each page).
7. **Docs:** a changed design rule needs an edit here or in `design.md` plus a dated entry in `docs/decisions/`, in the same commit.

## Accessibility (enforced by the axe checks)

- Visible `<label>` above inputs (or `sr-only` when the control is self-evident, like the composer). Placeholders are never labels.
- Text on tinted backgrounds must reach 4.5:1. `text-primary` on `bg-primary/10` is for icons only; for text use `text-accent-foreground` on `bg-accent`.
- Everything is keyboard operable with a visible focus ring. Icon-only buttons need `aria-label`. The page keeps a skip link and `main#main-content`.
- Touch targets 36px or more (controls are 36 to 44px).

## Testing conventions

- Every backend call is mocked; tests never reach a real backend or database.
- The sidebar is visible on desktop and inside a sheet on mobile: use `openMenu(page)` and `closeMenu(page)` from `tests/helpers.ts`,
  and scope sidebar checks with `page.locator('[data-testid=sidebar]:visible')` (two copies exist in the DOM on small screens).
- Playwright role queries skip content hidden by an open dialog (`aria-hidden`), so use CSS locators when you must detect the trigger itself.

## Pitfalls we have hit

- **Generated shadcn files can import `cn` from a `cn` npm package.** Change it to `@/lib/utils` and remove the stray dependency.
- **Base UI menus:** `DropdownMenuLabel` must be inside a `DropdownMenuGroup`, otherwise opening the menu crashes the whole page.
- **Button overwrite prompt:** `shadcn add` asks before overwriting `button.tsx`. Answer no (`echo n |`), or it hangs in a non-interactive shell.
- **Radius changes ripple:** `--radius` scales every `rounded-*` token. A large value turns 44px inputs into pills; check inputs after changing it.
- **Escape on a just-opened sheet is ignored** until its animation ends. Tests must retry (see `closeMenu`).
- Use `100dvh` (`h-dvh`) for full-height layouts, never `100vh`.
