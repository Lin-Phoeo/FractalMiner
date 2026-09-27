"""Back up git-ignored ground-truth data that cannot be recovered from Git.

Usage: python Tools/backup_truth_data.py <dest_root> [--dry-run] [--with-typhoeus]
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

GAME = r"A:\Hypergryph Launcher\games\Arknights Endfield"
FM = os.path.join(GAME, "FractalMiner")
SOURCES = [
    r"C:\Users\Administrator\Downloads\正面.rdc",
    r"C:\Users\Administrator\Downloads\123.rdc",
    r"C:\Users\Administrator\Downloads\213.rdc",
    os.path.join(FM, r"Validation\Captures"),
    os.path.join(FM, r"Assets\EndfieldShaderPack\GeneratedCapture"),
    os.path.join(FM, "_dump_1.5.3"),
    r"C:\Users\Administrator\Documents\EndfieldMmdSourceRigs",
    r"D:\MmdOracle\out",
    r"D:\MmdOracle\OracleProject\Assets",
]
TYPHOEUS = os.path.join(FM, r"Assets\Typhoeus")


def size_of(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest_root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--with-typhoeus", action="store_true")
    a = ap.parse_args()
    sources = SOURCES + ([TYPHOEUS] if a.with_typhoeus else [])
    missing = [s for s in sources if not os.path.exists(s)]
    if missing:
        sys.exit("missing sources: " + "; ".join(missing))
    total = 0
    for s in sources:
        n = size_of(s)
        total += n
        print(f"{n / 2**30:8.2f} GiB  {s}", flush=True)
    print(f"{total / 2**30:8.2f} GiB  total", flush=True)
    if a.dry_run:
        return
    dest = os.path.join(a.dest_root, "FractalMiner-truth-" + datetime.date.today().isoformat())
    manifest = {}
    for s in sources:
        target = os.path.join(dest, os.path.splitdrive(s)[1].lstrip("\\"))
        if os.path.isfile(s):
            src_dir, name = os.path.split(s)
            rc = subprocess.run(["robocopy", src_dir, os.path.dirname(target), name,
                                 "/COPY:DAT", "/R:1", "/W:1", "/NP"], stdout=subprocess.DEVNULL).returncode
            manifest[s] = sha256(s)
            if sha256(target) != manifest[s]:
                sys.exit("hash mismatch: " + s)
        else:
            rc = subprocess.run(["robocopy", s, target, "/E", "/COPY:DAT", "/R:1", "/W:1",
                                 "/NP", "/NFL", "/NDL"], stdout=subprocess.DEVNULL).returncode
        if rc >= 8:
            sys.exit(f"robocopy failed ({rc}) for {s}")
        print("copied", s, flush=True)
    with open(os.path.join(dest, "manifest-sha256.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("backup ok ->", dest, flush=True)


if __name__ == "__main__":
    main()
