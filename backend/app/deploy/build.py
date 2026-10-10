"""Build the Vite frontend into Vercel's public directory from the repository root.

Run as ``PYTHONPATH=backend python -m app.deploy.build``. Runtime dependencies are
installed from the backend package; this build never reads credentials or BMW files.
"""
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    root = Path.cwd()
    frontend = root / "frontend"
    if not (frontend / "package.json").is_file():
        raise SystemExit("Run the deployment build from the repository root.")
    subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=frontend, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)
    output = root / "public"
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(frontend / "dist", output)
    print("Frontend build prepared in public/ for the Vercel CDN.")


if __name__ == "__main__":
    main()
