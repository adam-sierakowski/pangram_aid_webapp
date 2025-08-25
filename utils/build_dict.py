#!/usr/bin/env python3
# build_dict.py
# Convert a large wordlist (one word per line) into sharded NDJSON `[mask,"word"]` files by popcount.
# - Keeps ONLY words made of UNIQUE letters, all inside the given alphabet (Polish by default).
# - Outputs: dict/manifest.json and dict/pop-<k>.jsonl shards.

import argparse, json, os, sys, unicodedata
from pathlib import Path

DEFAULT_ALPHABET = "aąbcćdeęfghijklłmnńoóprsśtuwyzźż"  # must match your app's config.json order

def load_alphabet(args):
    if args.alphabet:
        a = args.alphabet
    elif args.config and Path(args.config).is_file():
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            a = cfg.get("letters") or cfg.get("alphabet") or DEFAULT_ALPHABET
    else:
        a = DEFAULT_ALPHABET
    # sanitize: strip whitespace, dedupe preserving order
    seen, out = set(), []
    for ch in "".join(a.split()):
        if ch not in seen:
            seen.add(ch); out.append(ch)
    return "".join(out)

def mask_and_valid(word_cf, pos_map):
    """Return (mask,int),valid<bool>. Valid if all chars in alphabet and no repeats."""
    m = 0
    for ch in word_cf:
        i = pos_map.get(ch, -1)
        if i < 0: return 0, False                     # char outside alphabet → reject
        bit = 1 << i
        if m & bit: return 0, False                    # repeated letter → reject
        m |= bit
    return m, True

def popcount(n:int) -> int:
    return n.bit_count() if hasattr(int, "bit_count") else bin(n).count("1")

def main():
    p = argparse.ArgumentParser(description="Build pangram helper NDJSON shards from wordlist.")
    p.add_argument("input", help="Path to wordlist .txt (one word per line).")
    p.add_argument("outdir", help="Output directory, e.g., ./dict")
    p.add_argument("--alphabet", help="Alphabet string (overrides config).")
    p.add_argument("--ensure-vowels", help="Provide a vowels string and discard words that don't contain them.")  # TODO
    p.add_argument("--config", help="Path to config.json (uses its 'letters').")
    p.add_argument("--lower", action="store_true", help="Store words lowercased (default).")
    p.add_argument("--keep-original", action="store_true", help="Store original form instead of lowercase.")
    args = p.parse_args()

    alphabet = load_alphabet(args)
    pos = {ch:i for i,ch in enumerate(alphabet)}
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Open shard writers lazily
    writers = {}  # pop -> file handle
    files = {}    # pop -> relative path for manifest
    max_pop = 0

    def get_writer(k:int):
        nonlocal max_pop
        if k not in writers:
            path = outdir / f"pop-{k}.jsonl"
            fh = open(path, "w", encoding="utf-8", buffering=1024*1024)
            writers[k] = fh
            files[str(k)] = str(path.as_posix())
            max_pop = max(max_pop, k)
        return writers[k]

    total = kept = 0
    with open(args.input, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total += 1
            w_raw = line.strip()
            if not w_raw: continue

            # Normalize + choose stored form
            w_nfc = unicodedata.normalize("NFC", w_raw)
            w_cf  = w_nfc.casefold()  # robust lower for Unicode
            store = w_nfc if args.keep_original else w_cf

            # Reject if any whitespace or punctuation present
            # (only letters from alphabet allowed)
            m, ok = mask_and_valid(w_cf, pos)
            if not ok: continue

            k = popcount(m)
            fh = get_writer(k)
            fh.write(json.dumps([m, store], ensure_ascii=False) + "\n")
            kept += 1

    # Close files
    for fh in writers.values():
        fh.close()

    # Manifest
    manifest = {
        "alphabet": alphabet,
        "maxPop": max_pop,
        "files": files,
        "count": {"total_lines_read": total, "kept_unique_letter_words": kept}
    }
    with open(outdir / "manifest.json", "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)

    print(f"Done. Read {total}, kept {kept}. Shards in {outdir}/ pop-<k>.jsonl and manifest.json", file=sys.stderr)

if __name__ == "__main__":
    main()
