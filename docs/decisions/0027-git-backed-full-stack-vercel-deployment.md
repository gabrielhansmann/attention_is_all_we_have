# 0027: Deploy the frontend and API together from the repository root

Date: 2026-10-11
Status: accepted

## Context

The live application was deployed from a temporary, assembled frontend/API artifact. The GitHub
preview integration instead ran npm at the repository root, where no package.json exists, and
failed before building the application. Merging an otherwise valid feature would repeat that
failure for production. The deployment must be reproducible from the published repository.

## Decision

Keep the Vercel project rooted at this repository and use its FastAPI framework. The root
pyproject.toml selects `backend.app.deploy.vercel:app` and declares the backend package as a local uv source.
requirements.txt provides the equivalent local package install for pip. Runtime dependencies
remain defined in backend/pyproject.toml. All Python code stays under
backend/app and imports through app.

The root vercel.json invokes `python -m app.deploy.build` with PYTHONPATH=backend. This build runs
npm ci and the production frontend build inside frontend/, then copies dist/ to root public/.
The deployment adapter registers public/ with FastAPI's frontend support, using a deferred
directory check because files are generated after entrypoint discovery. Explicit CDN promotion
handles the application's CORS middleware. Vercel serves the frontend through the CDN and the
existing protected /api routes through FastAPI on the same origin. API routes always take priority.
Hash navigation needs no SPA fallback; missing assets and documentation requests remain 404.
The frontend router checks for local files before serving a fallback request. When CDN promotion
omits public/ from the function bundle, unmatched requests return 404 rather than triggering
the static handler's missing-directory error. This check applies only to frontend fallback routes.
FastAPI's minimum version reflects the frontend API. Production documentation restrictions and security headers remain.
The function duration remains 300 seconds; a durable worker is still separate future work.

Exclude .env, BMW files, tests, documentation and generated dependencies from deployment inputs
or function bundles. Database and AI credentials stay in the existing encrypted server-only
Vercel environment. Deployment does not run migrations or create application users.

Vercel documents the [custom FastAPI entrypoint and public directory](https://vercel.com/docs/frameworks/backend/fastapi)
and [Python packaging and function exclusions](https://vercel.com/docs/functions/runtimes/python).

## Consequences

- A Git push can build and deploy both application layers without a temporary staging artifact.
- Production source downloads still require the original files, which remain excluded.
- The build requires npm and Python; frontend dependency versions remain pinned by its lockfile.
- Serverless/background research limitations are unchanged; a successful build is not proof of a
  completed signed-in research run.
