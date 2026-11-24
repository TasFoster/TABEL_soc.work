"""Создать version.json из готовых установщиков Windows и пакетов Ubuntu."""

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote


def build_manifest(version, repository, full, lite, notes="", *, linux_full=None, linux_lite=None):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must be MAJOR.MINOR.PATCH")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository must be owner/name")
    files = {"full": Path(full), "lite": Path(lite)}
    if linux_full is not None and linux_lite is not None:
        files.update({"linux-amd64-full": Path(linux_full), "linux-amd64-lite": Path(linux_lite)})
    elif linux_full is not None or linux_lite is not None:
        raise ValueError("Both Ubuntu packages are required")
    if len({path.resolve() for path in files.values()}) != len(files):
        raise ValueError("Each variant requires a different installer")
    latest = {}
    for variant, path in files.items():
        suffix, magic = (".deb", b"!<arch>\n") if variant.startswith("linux-") else (".exe", b"MZ")
        if path.suffix.lower() != suffix or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty installer: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            if stream.read(len(magic)) != magic:
                raise ValueError(f"Invalid {suffix} installer: {path}")
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
    parser.add_argument("--linux-full", type=Path)
    parser.add_argument("--linux-lite", type=Path)
    parser.add_argument("--out", required=True)
    parser.add_argument("--notes-file", type=Path)
    args = parser.parse_args()
    notes = args.notes_file.read_text(encoding="utf-8") if args.notes_file else ""
    manifest = build_manifest(
        args.version, args.repository, args.full, args.lite, notes,
        linux_full=args.linux_full, linux_lite=args.linux_lite,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)


if __name__ == "__main__":
    main()
