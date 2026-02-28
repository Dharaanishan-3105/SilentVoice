"""
SilentVoice — Single-Command Launcher.

Usage:
    python run.py         → Start both backend (port 8000) and frontend (port 3000)
    python run.py backend → Start only the backend
    python run.py build   → Build frontend for production
"""

import subprocess
import sys
import os
import time
import signal

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")


def start_backend():
    """Start FastAPI backend on port 8000."""
    print("  🔧 Starting backend on http://localhost:8000 ...")
    return subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=BACKEND,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def start_frontend():
    """Start Next.js frontend dev server on port 3000."""
    print("  🎨 Starting frontend on http://localhost:3000 ...")
    # On Windows, npm must be called via cmd /c to resolve correctly
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    return subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--port", "3000"],
        cwd=FRONTEND,
        env={**os.environ, "FORCE_COLOR": "1"},
    )


def build_frontend():
    """Build frontend for production."""
    print("  📦 Building frontend ...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run(
        [npm_cmd, "run", "build"],
        cwd=FRONTEND,
        check=True,
    )
    print("  ✅ Frontend built successfully!")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║   🤟 SilentVoice — Launcher               ║")
    print("  ║                                           ║")
    print("  ║   © 2026 SilentVoice                      ║")
    print("  ║   Licensed to Dharaanishan                ║")
    print("  ║   All Rights Reserved                     ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()

    if mode == "build":
        build_frontend()
        return

    if mode == "backend":
        proc = start_backend()
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
        return

    # Start both
    backend_proc = start_backend()
    time.sleep(3)
    frontend_proc = start_frontend()

    print()
    print("  ✅ SilentVoice is running!")
    print("  📍 Frontend:  http://localhost:3000")
    print("  📍 Backend:   http://localhost:8000")
    print("  📍 API Docs:  http://localhost:8000/docs")
    print("  Press Ctrl+C to stop.")
    print()

    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\n  🛑 Shutting down...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("  ✅ Stopped.")


if __name__ == "__main__":
    main()
