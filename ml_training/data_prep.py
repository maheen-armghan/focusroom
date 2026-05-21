"""
FocusRoom — Data Preparation  |  data_prep.py
===============================================
Reads the Roboflow _classes.csv and copies images into
data/raw/focused/ and data/raw/distracted/

YOUR DATASET FORMAT
-------------------
All images are flat in roboflow/train/ (no subfolders).
Labels come from _classes.csv with these columns:

    filename, high, low, slightly high, slightly low

Each column is 0 or 1 (one-hot, but some rows have multiple 1s).

WHAT EACH LABEL MEANS (gaze elevation)
---------------------------------------
    high          = looking UP significantly    → distracted
    slightly high = looking slightly upward     → distracted
    low           = looking DOWN significantly  → distracted
    slightly low  = looking slightly downward   → focused
                    (this is the natural gaze angle when
                     looking at a laptop screen)

MAPPING RULE
------------
    slightly_low=1, all others=0  →  focused
    high=1 OR slightly_high=1 OR low=1  →  distracted
    slightly_low=1 with any other active →  distracted
      (off-gaze always wins over slightly-low)

WHAT THIS SCRIPT ADDS TO YOUR DATA
------------------------------------
    data/raw/focused/     += ~1,349 Roboflow images
    data/raw/distracted/  += ~3,623 Roboflow images
    data/raw/closed/       = unchanged (MRL only)

USAGE
-----
    python data_prep.py            # run for real
    python data_prep.py --dry_run  # count without writing
    python data_prep.py --summary  # check current counts
"""

import sys
import csv
import shutil
import argparse
from pathlib import Path
from datetime import datetime

import cv2

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════

SCRIPT_DIR  = Path(__file__).parent
DATA_RAW    = SCRIPT_DIR / "data" / "raw"

# All images sit flat inside roboflow/train/
# _classes.csv is also in roboflow/train/
RBF_TRAIN   = SCRIPT_DIR / "roboflow" / "train"
CSV_FILE    = RBF_TRAIN / "_classes.csv"

CLASS_NAMES = ["focused", "distracted", "closed"]
VALID_EXTS  = {".jpg", ".jpeg", ".png", ".bmp"}
OUT_SIZE    = 64        # must match train.py IMG_SIZE
RBF_PREFIX  = "rbf_"   # prefix so filenames never clash with MRL files


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def make_raw_dirs():
    for cls in CLASS_NAMES:
        (DATA_RAW / cls).mkdir(parents=True, exist_ok=True)


def count_raw():
    counts = {}
    for cls in CLASS_NAMES:
        d = DATA_RAW / cls
        counts[cls] = len([
            f for f in d.iterdir()
            if f.suffix.lower() in VALID_EXTS
        ]) if d.exists() else 0
    return counts


def print_summary():
    log("=" * 55)
    log("data/raw/ image counts:")
    counts = count_raw()
    for cls in CLASS_NAMES:
        n   = counts[cls]
        bar = "█" * min(35, n // 100)
        ok  = "✓ ready" if n >= 500 else ("✗ need more" if n < 100 else "⚠ low")
        log(f"  {cls:12s}: {n:6,}  {bar:<35s}  {ok}")
    log(f"  {'TOTAL':12s}: {sum(counts.values()):6,}")
    log("=" * 55)


# ══════════════════════════════════════════════════════════════
# MAP ONE ROW → class name
# ══════════════════════════════════════════════════════════════

def map_row(row: dict) -> str | None:
    """
    Returns 'focused', 'distracted', or None (skip).

    Rule:
      slightly_low only            → focused
      high OR slightly_high OR low → distracted
      slightly_low + any other     → distracted  (off-gaze wins)
    """
    h  = int(row.get("high",          0))
    lo = int(row.get("low",           0))
    sh = int(row.get("slightly high", 0))
    sl = int(row.get("slightly low",  0))

    if sl == 1 and h == 0 and lo == 0 and sh == 0:
        return "focused"
    if h == 1 or lo == 1 or sh == 1 or sl == 1:
        return "distracted"
    return None   # all zeros — no label


# ══════════════════════════════════════════════════════════════
# CORE PROCESSING
# ══════════════════════════════════════════════════════════════

def process(dry_run: bool = False) -> dict:
    # Validate paths
    if not RBF_TRAIN.exists():
        log(f"[ERROR] Roboflow folder not found: {RBF_TRAIN}")
        log("Create:  ml_training/roboflow/train/")
        log("Put your images and _classes.csv inside it.")
        sys.exit(1)

    if not CSV_FILE.exists():
        log(f"[ERROR] _classes.csv not found: {CSV_FILE}")
        log("Put _classes.csv inside ml_training/roboflow/train/")
        sys.exit(1)

    # Read CSV
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    log(f"CSV loaded: {len(rows):,} rows")

    # Count before processing
    preview = {"focused": 0, "distracted": 0, "skip": 0}
    for row in rows:
        cls = map_row(row)
        if cls in preview:
            preview[cls] += 1
        else:
            preview["skip"] += 1

    log(f"  Will create → focused: {preview['focused']:,} | "
        f"distracted: {preview['distracted']:,} | "
        f"skip: {preview['skip']:,}")

    if dry_run:
        return {"saved": preview, "errors": 0, "skipped_exists": 0}

    saved          = {cls: 0 for cls in CLASS_NAMES}
    skipped_exists = 0
    errors         = 0

    for row in rows:
        filename   = row.get("filename", "").strip()
        target_cls = map_row(row)

        if target_cls is None:
            continue

        img_path = RBF_TRAIN / filename
        if not img_path.exists():
            # Try common extensions if exact match not found
            found = False
            for ext in VALID_EXTS:
                alt = img_path.with_suffix(ext)
                if alt.exists():
                    img_path = alt
                    found = True
                    break
            if not found:
                errors += 1
                continue

        out_name = RBF_PREFIX + filename
        out_path = DATA_RAW / target_cls / out_name

        # Idempotent — skip if already copied
        if out_path.exists():
            skipped_exists += 1
            saved[target_cls] += 1
            continue

        # Read → greyscale → resize → save
        img = cv2.imread(str(img_path))
        if img is None:
            errors += 1
            continue

        grey    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(grey, (OUT_SIZE, OUT_SIZE),
                             interpolation=cv2.INTER_AREA)
        try:
            cv2.imwrite(str(out_path), resized)
            saved[target_cls] += 1
        except Exception as e:
            log(f"  [ERROR] {out_name}: {e}")
            errors += 1

    return {
        "saved"          : saved,
        "errors"         : errors,
        "skipped_exists" : skipped_exists,
    }


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="Prepare Roboflow gaze data for FocusRoom CNN training",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--dry_run", action="store_true",
                   help="Count what would be saved without writing any files")
    p.add_argument("--summary", action="store_true",
                   help="Show current data/raw/ counts and exit")
    return p.parse_args()


def main():
    args = parse_args()

    if args.summary:
        print_summary()
        return

    make_raw_dirs()

    log("=" * 55)
    log("FocusRoom — Roboflow Data Preparation")
    log(f"  CSV    : {CSV_FILE}")
    log(f"  Images : {RBF_TRAIN}")
    log(f"  Output : {DATA_RAW}")
    log(f"  Dry run: {args.dry_run}")
    log("=" * 55)

    log("Before:"); print_summary()

    result = process(dry_run=args.dry_run)

    log("\nResults:")
    for cls in CLASS_NAMES:
        log(f"  → data/raw/{cls:12s}: +{result['saved'].get(cls, 0):,}")
    if result.get("errors"):
        log(f"  Errors (image not found or unreadable): {result['errors']}")
        log("  This usually means the image filename in CSV doesn't match the file on disk.")
    if result.get("skipped_exists"):
        log(f"  Already existed (skipped): {result['skipped_exists']:,}")

    if args.dry_run:
        log("\n[DRY RUN] No files written. Remove --dry_run to apply.")
    else:
        log("\nAfter:"); print_summary()
        log("\nNext step:  python train.py")


if __name__ == "__main__":
    main()
