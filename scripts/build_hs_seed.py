"""Build the checked-in HS code seed from the USITC HTS bulk export.

Run occasionally to refresh; the generator reads the checked-in JSON so it
stays offline and deterministic rather than depending on a 12MB download at
generation time.

    uv run python scripts/build_hs_seed.py

HTS descriptions are hierarchical. A ten-digit line often reads only "Other"
or "Brushless" — meaningless alone. Each entry's full description is composed
by walking up the indent tree, so an invoice line says what it actually is.
"""

import json
import pathlib
import re
import urllib.request

URL = "https://hts.usitc.gov/reststop/exportList?from=0101&to=9999&format=JSON&styles=false"
OUT = pathlib.Path(__file__).parent.parent / "src/clearway/corpus/seeds/hs_codes.json"

# Chapters that carry real East African trade, so generated invoices read
# plausibly rather than as a random walk through the tariff schedule.
CHAPTERS = {
    "06": "cut flowers and plants",
    "07": "vegetables",
    "09": "coffee, tea and spices",
    "15": "oils and fats",
    "40": "rubber",
    "52": "cotton",
    "61": "knitted apparel",
    "62": "woven apparel",
    "64": "footwear",
    "73": "iron and steel articles",
    "84": "machinery",
    "85": "electrical machinery",
    "87": "vehicles",
    "94": "furniture",
}
PER_CHAPTER = 18
NOISE = {"other", "others", "n.e.s.", "nesoi"}


def compose(rows: list[dict], i: int) -> str:
    """Full description for row i, walking up through shallower indents."""
    row = rows[i]
    parts = [(row.get("description") or "").strip()]
    indent = int(row.get("indent") or 0)
    for j in range(i - 1, -1, -1):
        if indent <= 0:
            break
        prev = rows[j]
        prev_indent = int(prev.get("indent") or 0)
        if prev_indent < indent:
            text = (prev.get("description") or "").strip()
            if text:
                parts.append(text)
            indent = prev_indent
    parts = [p.rstrip(":").strip() for p in reversed(parts) if p]
    return ", ".join(dict.fromkeys(parts))


def main() -> None:
    print(f"fetching {URL}")
    with urllib.request.urlopen(URL, timeout=180) as r:
        rows = json.load(r)
    print(f"  {len(rows)} rows")

    by_chapter: dict[str, list[dict]] = {c: [] for c in CHAPTERS}
    for i, row in enumerate(rows):
        hts = (row.get("htsno") or "").strip()
        if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\.\d{2}", hts):
            continue
        chapter = hts[:2]
        if chapter not in by_chapter or len(by_chapter[chapter]) >= PER_CHAPTER:
            continue
        desc = compose(rows, i)
        # A composed description that is still just noise tells a reader nothing.
        if len(desc) < 18 or desc.lower() in NOISE:
            continue
        units = row.get("units") or []
        by_chapter[chapter].append(
            {
                "hts": hts,
                "description": desc[:150],
                "unit": (units[0] if units else "No."),
                "chapter": chapter,
                "chapter_name": CHAPTERS[chapter],
            }
        )

    entries = [e for c in sorted(by_chapter) for e in by_chapter[c]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(entries)} entries to {OUT.relative_to(OUT.parent.parent.parent.parent)}")
    for e in entries[:3]:
        print(f"  {e['hts']}  {e['description'][:72]}")


if __name__ == "__main__":
    main()
