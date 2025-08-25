#!/usr/bin/env python3
# search_dict.py
# Search a sharded NDJSON dictionary built as lines of [mask:int, "word"]
# Manifest format:
# {
#   "alphabet": "aąbcćdeęfghijklłmnńoóprsśtuwyzźż",
#   "maxPop": 12,
#   "files": { "2":"pop-2.jsonl", "3":"pop-3.jsonl", ... }
# }
#
# Usage:
#   python search_dict.py --dict-root res/dict/pl_PL --letters "ąbcio" --mode subset --limit 100 --shuffle

import argparse, json, sys, unicodedata, os, gzip
from pathlib import Path
from random import randrange

def nfc(s:str)->str:
    return unicodedata.normalize("NFC", s)

def load_manifest(root:Path):
    # try manifest.json, then manifest.jsonl (single-line JSON)
    for name in ("manifest.json", "manifest.jsonl"):
        p = root / name
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"No manifest.json(.l) under {root}")

def build_pos_map(alphabet:str):
    # preserve order; map char -> bit position
    return {ch:i for i,ch in enumerate(alphabet)}

def mask_from_letters(s:str, pos_map:dict)->int:
    # casefold for robust matching; keep only chars present in alphabet
    s_cf = nfc(s).casefold()
    m = 0
    for ch in s_cf:
        i = pos_map.get(ch, -1)
        if i >= 0:
            bit = 1 << i
            # reject duplicates for EXACT intent? not needed for mask; duplicates don't matter
            m |= bit
    return m

def is_subset(mask:int, allowed:int)->bool:
    # word fits inside selected letters
    return (mask & (~allowed)) == 0

def popcount(n:int)->int:
    return n.bit_count() if hasattr(int, "bit_count") else bin(n).count("1")

def open_maybe_gzip(path:Path):
    # allow optional gzip compression for shards
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")

def stream_ndjson(path:Path):
    with open_maybe_gzip(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            yield json.loads(line)

def reservoir_sample_push(reservoir:list, k_limit:int, item, seen:int):
    # classic reservoir: size k_limit, replace with prob k/seen
    if len(reservoir) < k_limit:
        reservoir.append(item)
    else:
        r = randrange(seen)  # 0..seen-1
        if r < k_limit:
            reservoir[r] = item

def main():
    ap = argparse.ArgumentParser(description="Search sharded NDJSON dictionary by letters.")
    ap.add_argument("--dict-root", required=True, help="Path to dictionary root (e.g., res/dict/pl_PL)")
    ap.add_argument("--letters", required=True, help="Letters to allow (will be casefolded)")
    ap.add_argument("--mode", choices=["subset","exact"], default="subset", help="Match mode")
    ap.add_argument("--limit", type=int, default=100, help="Max results to print")
    ap.add_argument("--shuffle", action="store_true", help="Shuffle via reservoir sampling")
    ap.add_argument("--show-count-only", action="store_true", help="Only print counts, not the list")
    args = ap.parse_args()

    root = Path(args.dict_root)
    man = load_manifest(root)
    alphabet = man["alphabet"]
    files_map = man.get("files", {})
    if not files_map:
        print("Manifest has no 'files' map.", file=sys.stderr); sys.exit(1)

    pos = build_pos_map(alphabet)
    selected_mask = mask_from_letters(args.letters, pos)
    if selected_mask == 0:
        print("Selected letters produced empty mask (no overlap with alphabet).", file=sys.stderr)
        sys.exit(2)

    target_pop = popcount(selected_mask)

    # choose shards
    shard_keys = sorted(int(k) for k in files_map.keys())
    if args.mode == "exact":
        shard_keys = [k for k in shard_keys if k == target_pop]
    else:
        shard_keys = [k for k in shard_keys if 0 < k <= target_pop]

    if not shard_keys:
        print("No shards match the selection/popcount.", file=sys.stderr)
        print("Found: 0 (showing 0)")
        sys.exit(0)

    found = 0
    kept = []  # results list (or reservoir)
    for k in shard_keys:
        rel = files_map[str(k)]
        shard_path = root / rel
        if not shard_path.is_file():
            # tolerate missing shard
            continue
        try:
            for row in stream_ndjson(shard_path):
                # row format: [mask:int, "word"]
                try:
                    m = int(row[0])
                    w = row[1]
                except Exception:
                    continue
                ok = (m == selected_mask) if args.mode == "exact" else is_subset(m, selected_mask)
                if ok:
                    found += 1
                    if args.shuffle:
                        reservoir_sample_push(kept, args.limit, w, found)
                    else:
                        if len(kept) < args.limit:
                            kept.append(w)
        except Exception as e:
            print(f"Warn: failed reading {shard_path}: {e}", file=sys.stderr)
            continue

    # Output
    print(f"Found: {found} (showing {len(kept) if not args.show_count_only else 0})")
    if not args.show_count_only:
        # stable order unless shuffled; optionally sort alpha if not shuffled
        if not args.shuffle:
            try:
                kept.sort()
            except Exception:
                pass
        for w in kept:
            print(w)

if __name__ == "__main__":
    main()
