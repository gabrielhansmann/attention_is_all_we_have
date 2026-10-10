# Agent rules

Project: BMW hackathon requirement-evidence engine. Architecture docs live in `docs/`
(start at `docs/README.md`); those `.md` files are the source of truth.

## UI design

- Before generating or changing UI, read `design.md` and `docs/ui-design-guidelines.md`.
- Use the BMW tokens and component rules in `design.md` for all UI.
- Apply the anti-slop workflow in `docs/ui-design-guidelines.md`. BMW's explicit brand rules
  take precedence over generic aesthetic defaults, including white surfaces, Inter fallback,
  rectangular components, and dark hero bands.

## Pushing

1. **Only push when the user asks.** Never push on your own initiative.
2. **Always squash before pushing.** Collapse all local work since the branch diverged from
   `main` into a single commit (`git reset --soft $(git merge-base HEAD origin/main)` then
   commit, or `git merge-base` + `git rebase -i` equivalent without interactive flags). One push
   = one commit.
3. **Commit message:** imperative subject line, then a short body listing what changed and why.
   Mention any `docs/decisions/` entry added or changed.
4. **Never push to `main` directly** unless the user explicitly says so; work on a branch and
   open a PR. Never force-push `main`. Force-pushing your own feature branch after a squash is
   fine (`--force-with-lease`).
5. **Never commit** `data/` (BMW-provided files), `.env`, or any secret. Check `git status`
   before committing; if any of those show up as staged, stop and fix `.gitignore`.

## Docs and design decisions

- When a design decision changes, edit the relevant `docs/architecture/*.md` in place, bump its
  `Last updated` date, and add a dated entry in `docs/decisions/` (see `docs/decisions/README.md`).
  Do this in the same commit as the code change that motivated it.

## Syncing to Supabase after a push

After a successful push, sync the project record to Supabase (use the Supabase MCP tools):

1. Upsert every new or changed `docs/decisions/*.md` entry into the `design_decisions` table
   (`id`, `title`, `status`, `body`, `source_path`, `commit_sha`, `updated_at`).
2. Upsert changed `docs/architecture/*.md` files into the `architecture_docs` table
   (`path`, `title`, `status`, `body`, `commit_sha`, `updated_at`).
3. Schema changes go through `apply_migration` (never ad-hoc DDL via `execute_sql`), and the
   migration file is committed in the same squashed commit.
4. Inspect existing tables (`list_tables`) before changing schema. Run `get_advisors` after DDL.
5. Report what was synced in the final message. If a sync step fails or is skipped, say so
   explicitly. Do not claim the sync is done.

The git repo is the source of truth; Supabase is a mirror. Never edit docs only in Supabase.
