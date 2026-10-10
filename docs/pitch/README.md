# BMW Product Intelligence: presentation snapshot

[PowerPoint](bmw-product-intelligence-mcp.pptx) · [PDF](bmw-product-intelligence-mcp.pdf) · [Speaker script](speaker-script.md)

The presentation has six pitch slides with a three-minute rehearsal target and three hidden Q&A slides. Text, diagrams and coverage bars are editable PowerPoint objects. The application image is a real crop of the public Vercel sign-in screen. The deck was built through PowerPoint MCP, then finished locally with speaker notes, explicit background fills and corrected theme effects. The final file was reopened and saved through MCP and rendered with LibreOffice for visual verification.

## Evidence and deployment snapshot

The captured data is in [verified-data.json](verified-data.json); public deployment checks are in [verified-deployment.json](verified-deployment.json). The snapshot was taken on 2026-10-10 at 21:01 UTC against Supabase and the Vercel deployment of `main` at `7c7ba86`. Numbers are a dated snapshot, rather than a live PowerPoint connection.

The database contains 13,771 comments, 1,627 study cells, 198 equipment options and 198 stored text passages. The passages split into 149 BMW catalog passages and 49 web passages. There are eight internal files and three registered web sources. Study cells are not respondent counts; comments are not unique customers. Equipment availability is not observed option uptake, and 2030 sales rows are forecasts.

The example is G60 / US / Comfort & Space: 396 category comments, including 139 tagged negative. The displayed heated-steering-wheel quote comes from `G60_feedback_hackathon.xlsx`, sheet `Feedback_Explorer`, row 361 (`G60-0287`). It is one comment within the category, not evidence of 139 identical complaints or an approved requirement.

The public [Vercel app](https://bmw-product-intelligence.vercel.app/) and `/api/health` returned 200; health reported `db: ok` and an AI key configured. The hosted frontend JavaScript was byte-for-byte identical to the local build of deployed `main`. Protected source, conversation and account endpoints returned 401 without a session. Production interactive docs returned 404. Desktop and mobile screenshots were captured without mocks or runtime errors.

Automatic approval review rejected creating a temporary authentication session for hosted screenshots because it would change live authentication state. That action was removed. No account, password or session was created by this presentation work. Signed-in hosted research, evidence search and source-viewer interactions were not newly exercised. The screenshot therefore depicts only the public sign-in page.

## Corrections to the older presentation

- The deployed frontend uses live `/api` data. It is no longer the illustrative static workspace described by the old deck.
- The orchestrator selects agents and reacts to their output. Manual plan/start and per-step accept/edit/retry/reject controls were removed in decision 0018.
- LangGraph and Postgres checkpoints are implemented in decision 0019; restart recovery is no longer simply described as future work. Reliable long-running execution on Vercel remains unverified.
- No editable target dashboard, approval UI, recurring report automation or persistent approved requirement backlog is claimed. The `finding`, `cluster`, `requirement` and `score` tables are empty at the snapshot. Research outputs are retained on steps and messages.
- Supabase has five completed stored runs and one older in-progress run with a planned step. Those rows are historical observations, not proof that a fresh hosted execution succeeded.
- Original BMW source files were omitted from the Vercel package. Stored source passages can be served by the backend, but downloading the original files is unavailable there.
- The deployment package sets `maxDuration: 300`. A separate durable worker is a next step for longer research. This setting is not a universal Vercel limit; see [Vercel's duration documentation](https://vercel.com/docs/functions/configuring-functions/duration).

## Data-quality and version boundaries

The source metadata contains a [Genesis G70 page](https://www.caranddriver.com/genesis/g70-2025) tagged with `vehicle_line: G70`. That tag collides with the BMW vehicle code and needs review before a competitor conclusion. The presentation flags this ambiguity rather than treating stored web evidence as a verified competitor match. No source rows were changed.

China has no feedback comments in this dataset, but G68 and G70 have Chinese study cells and sales rows. G60 / CN must not silently inherit G68 / CN evidence. Missing rows and explicit zero volumes are different.

Supabase's architecture mirror is at `4c86193`, while the deployed app is `7c7ba86`. Mirrored decisions 0022 and 0023 belong to `fix/database-backed-workspace`, commit `2a9081b`, rather than deployed `main`. The presentation uses the actual deployment, read-only database observations and main's decisions 0017–0021 to establish what is delivered.

## Files and replacement

`bmw-product-intelligence-mcp.pptx` is the sole project presentation and reuses the previous canonical filename. The main checkout already contained no old project `.ppt` or `.pptx` files; no duplicate or alternate deck is retained. Old screenshots, scripts and previews from the earlier branch are not reused. Historical Git revisions and dependencies' default PowerPoint templates are unaffected.

[mcp-build.json](mcp-build.json) records the 178 MCP operations and slide scripts. [validation.json](validation.json) records reconciliation and rendering checks. The PDF includes the Q&A slides even though they are hidden in the PowerPoint slideshow.

This presentation records the deployment and database snapshot above. Later application changes,
including model comparisons and the requirement register, are described in the architecture docs
and their validation reports; they are outside this presentation's captured version.
