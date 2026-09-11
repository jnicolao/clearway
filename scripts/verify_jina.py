"""Make one real Jina call and print exactly what comes back.

Run this the moment you have a key. It answers the three things the client
in clearway.models.embeddings currently guesses at:

    uv run python scripts/verify_jina.py            # text, multivector on
    uv run python scripts/verify_jina.py --no-multi # text, multivector off
    uv run python scripts/verify_jina.py --image URL

Then prune the dead branch in embeddings.py and drop the UNVERIFIED note.
"""

import argparse
import json
import os
import sys

import httpx2 as httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from clearway.models.embeddings import API_URL, build_request  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="image URL to embed instead of text")
    ap.add_argument("--no-multi", action="store_true", help="omit return_multivector")
    args = ap.parse_args()

    key = os.environ.get("JINA_API_KEY", "").strip()
    if not key:
        print("JINA_API_KEY is not set — get one at https://jina.ai/embeddings")
        return 1

    inputs = [{"image": args.image}] if args.image else [{"text": "bill of lading"}]
    body = build_request(inputs, multivector=not args.no_multi)
    print("REQUEST\n" + json.dumps(body, indent=2)[:600] + "\n")

    r = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=120.0,
    )
    print(f"HTTP {r.status_code}")
    if r.status_code >= 400:
        print(r.text[:1000])
        return 1

    payload = r.json()
    print("TOP-LEVEL KEYS:", sorted(payload))
    for i, item in enumerate(payload.get("data", [])[:1]):
        print(f"data[{i}] keys:", sorted(item))
        vecs = item.get("embedding") or item.get("embeddings") or []
        if vecs and isinstance(vecs[0], list):
            print(f"  MULTI-VECTOR: {len(vecs)} rows x {len(vecs[0])} dims")
        elif vecs:
            print(f"  SINGLE VECTOR: {len(vecs)} dims")
    print("\nusage:", payload.get("usage"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
