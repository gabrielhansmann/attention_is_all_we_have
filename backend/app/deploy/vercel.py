"""Export the existing API with its built frontend for Vercel's CDN inspection."""
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from app.main import create_app


def create_deployment_app(directory: Path) -> FastAPI:
    application = create_app()

    async def require_frontend_files() -> None:
        # Vercel promotes these files to its CDN and can omit them from the
        # function bundle. Unmatched backend requests must still return 404.
        if not directory.is_dir():
            raise HTTPException(status_code=404, detail="Not Found")

    frontend = APIRouter(dependencies=[Depends(require_frontend_files)])
    # The build produces this directory after entrypoint discovery. Hash navigation
    # needs no SPA fallback, so missing files and disabled docs keep their HTTP errors.
    frontend.frontend("/", directory=directory, fallback=None, check_dir=False)
    application.include_router(frontend)
    return application


app = create_deployment_app(Path.cwd() / "public")
