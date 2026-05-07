#!/usr/bin/env python3
"""
Package Lambda deployment zips without Docker (Linux x86_64 == Lambda layout).

Use when Docker is unavailable. Matches package_docker.py layout per agent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PYTHON = "3.12"
BACKEND = Path(__file__).resolve().parent
DATABASE = BACKEND / "database"

AGENTS: dict[str, list[str]] = {
    "tagger": ["lambda_handler.py", "agent.py", "templates.py", "observability.py"],
    "reporter": ["lambda_handler.py", "agent.py", "templates.py", "observability.py", "judge.py"],
    "charter": ["lambda_handler.py", "agent.py", "templates.py", "observability.py"],
    "retirement": ["lambda_handler.py", "agent.py", "templates.py", "observability.py"],
    "planner": [
        "lambda_handler.py",
        "agent.py",
        "templates.py",
        "market.py",
        "prices.py",
        "observability.py",
    ],
}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    if r.returncode != 0:
        sys.exit(r.returncode)


def export_requirements(agent_dir: Path) -> str:
    out = subprocess.run(
        ["uv", "export", "--no-hashes", "--no-emit-project"],
        cwd=str(agent_dir),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines: list[str] = []
    skipping_editable_continuation = False
    for line in out.splitlines():
        if skipping_editable_continuation:
            if line.startswith((" ", "\t")):
                continue
            skipping_editable_continuation = False

        stripped = line.strip()
        if stripped.startswith("pyperclip"):
            continue
        # Omit editable workspace installs (paths break outside uv workspace)
        if stripped.startswith("-e ") or stripped.startswith("--editable"):
            skipping_editable_continuation = True
            continue

        lines.append(line)
    return "\n".join(lines)


def package_agent(name: str) -> Path:
    agent_dir = BACKEND / name
    if not agent_dir.is_dir():
        raise FileNotFoundError(agent_dir)

    req_txt = export_requirements(agent_dir)
    zip_path = agent_dir / f"{name}_lambda.zip"

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        pkg = tdp / "package"
        pkg.mkdir()
        req_file = tdp / "requirements.txt"
        req_file.write_text(req_txt)

        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                PYTHON,
                "--target",
                str(pkg),
                "-r",
                str(req_file),
            ]
        )
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                PYTHON,
                "--target",
                str(pkg),
                "--no-deps",
                str(DATABASE),
            ]
        )

        for fname in AGENTS[name]:
            shutil.copy2(agent_dir / fname, pkg / fname)

        if zip_path.exists():
            zip_path.unlink()
        run(["zip", "-rq", str(zip_path), "."], cwd=pkg)

    mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"✅ {zip_path.name} ({mb:.1f} MB)")
    return zip_path


def package_api() -> Path:
    api_dir = BACKEND / "api"
    zip_path = api_dir / "api_lambda.zip"

    deps = [
        "boto3>=1.40.29",
        "fastapi>=0.116.1",
        "fastapi-clerk-auth>=0.0.7",
        "httpx>=0.28.1",
        "mangum>=0.19.0",
        "pydantic>=2.11.7",
        "python-dotenv>=1.1.1",
        "python-jose[cryptography]>=3.5.0",
        "uvicorn>=0.35.0",
    ]

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        pkg = tdp / "package"
        pkg.mkdir()
        api_pkg = pkg / "api"
        shutil.copytree(
            api_dir,
            api_pkg,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".env*",
                "*.zip",
                "package_docker.py",
                "package_native.py",
                "test_*.py",
            ),
        )
        shutil.copy2(api_dir / "lambda_handler.py", pkg / "lambda_handler.py")

        db_src = DATABASE / "src"
        db_dst = pkg / "src"
        if db_dst.exists():
            shutil.rmtree(db_dst)
        shutil.copytree(
            db_src,
            db_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

        run(
            ["uv", "pip", "install", "--python", PYTHON, "--target", str(pkg)]
            + deps
        )
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                PYTHON,
                "--target",
                str(pkg),
                "--no-deps",
                str(DATABASE),
            ]
        )

        if zip_path.exists():
            zip_path.unlink()
        run(["zip", "-rq", str(zip_path), "."], cwd=pkg)

    mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"✅ {zip_path.name} ({mb:.1f} MB)")
    return zip_path


def main() -> None:
    os.chdir(BACKEND)
    print("Packaging agents (native, no Docker)...")
    for agent in AGENTS:
        package_agent(agent)
    print("Packaging API...")
    package_api()
    print("Done.")


if __name__ == "__main__":
    main()
