"""Создать version.json только из двух готовых установщиков."""

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote


def build_manifest(version, repository, full, lite, notes=""):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must be MAJOR.MINOR.PATCH")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository must be owner/name")
    files = {"full": Path(full), "lite": Path(lite)}
    if files["full"].resolve() == files["lite"].resolve():
        raise ValueError("Two different installers are required")
    latest = {}
    for variant, path in files.items():
        if path.suffix.lower() != ".exe" or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty installer: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError(f"Not a Windows executable: {path}")
            stream.seek(0)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        latest[variant] = {
            "version": version,
            "date": datetime.date.today().isoformat(),
            "path": "/" + path.name,
            "url": f"https://github.com/{repository}/releases/download/v{version}/{quote(path.name)}",
            "size": path.stat().st_size,
            "sha256": digest.hexdigest(),
            "notes": notes,
        }
    return {"schema": 1, "latest": latest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--full", required=True)
    parser.add_argument("--lite", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--notes-file", type=Path)
    args = parser.parse_args()
    notes = args.notes_file.read_text(encoding="utf-8") if args.notes_file else ""
    manifest = build_manifest(args.version, args.repository, args.full, args.lite, notes)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)


if __name__ == "__main__":
    main()
