"""Fetch data/raw from config/corpus.json and rewrite data/raw/manifest.json.

Usage:
    python scripts/fetch_raw.py            # download missing files, verify hashes, write manifest
    python scripts/fetch_raw.py --discover # list candidate MOM URLs for the quarters still missing
"""

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.json"
CORPUS = json.loads((ROOT / "config" / "corpus.json").read_text())

UA = {"User-Agent": "policy-agent-data-fetch/0.1 (research prototype; public data only)"}
POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/poll-download"
META = "https://api-production.data.gov.sg/v2/public/api/datasets/{id}/metadata"
MOM_SITEMAP = "https://www.mom.gov.sg/sitemap.xml"


def get(url: str, retries: int = 5) -> tuple[bytes, int, str]:
    """GET with exponential backoff on 429/5xx and transient network errors; paced politely."""
    for attempt in range(retries):
        try:
            time.sleep(0.5)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read(), r.status, r.geturl()
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < retries - 1:
                time.sleep(2 ** (attempt + 2))
                continue
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 2))
                continue
            raise
    raise RuntimeError(url)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write(rel: str, content: bytes, record: dict, old: dict[str, dict], out: list[dict]) -> None:
    path = RAW / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256(content)
    prev = old.get(rel)
    if prev and prev["sha256"] != digest:
        print(f"CHANGED  {rel} (upstream content differs from recorded hash)")
    path.write_bytes(content)
    out.append(
        {
            "path": rel,
            "sha256": digest,
            "bytes": len(content),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            **record,
        }
    )


def fetch_datagov(item: dict, old: dict, out: list[dict]) -> None:
    did = item["dataset_id"]
    poll = json.loads(get(POLL.format(id=did))[0])
    csv_url = poll["data"]["url"]
    body, status, _ = get(csv_url)
    rec = {
        "source": "datagov",
        "key": item["key"],
        "dataset_id": did,
        "indicator": item["indicator"],
        "period_type": item["period_type"],
        "url": f"https://data.gov.sg/datasets/{did}/view",
        "licence": "sg_odl",
        "http_status": status,
    }
    write(f"datagov/{item['key']}.csv", body, rec, old, out)
    meta, status, _ = get(META.format(id=did))
    write(f"datagov/{item['key']}.meta.json", meta, {**rec, "http_status": status}, old, out)


def fetch_mom(key: str, prior: dict, old: dict, out: list[dict]) -> None:
    body, status, final = get(prior["url"])
    rec = {k: prior[k] for k in ("source", "key", "url", "licence")}
    write(prior["path"], body, {**rec, "final_url": final, "http_status": status}, old, out)


def title_of(html: bytes) -> str:
    m = re.search(rb"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1).decode("utf8", "ignore")).strip() if m else ""


def discover() -> None:
    index, _, _ = get(MOM_SITEMAP)
    children = re.findall(r"<loc>([^<]+)</loc>", index.decode("utf8", "ignore"))
    pat = re.compile(r"labour-market|labour-force", re.I)
    hits: set[str] = set()
    for child in children:
        if not re.search(r"newsroom|others", child):
            continue
        body, _, _ = get(child)
        locs = re.findall(r"<loc>([^<]+)</loc>", body.decode("utf8", "ignore"))
        hits |= {u for u in locs if pat.search(u)}
    print("\n".join(sorted(hits)))


def main() -> None:
    if "--discover" in sys.argv:
        return discover()

    prior_rows = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    old = {r["path"]: r for r in prior_rows}
    mom_prior = {r["key"]: r for r in prior_rows if r["source"] == "mom"}
    out: list[dict] = []

    for item in CORPUS["datagov"]:
        fetch_datagov(item, old, out)
        print("ok", item["key"])

    for key in CORPUS["mom_pages"]["keep"]:
        if key not in mom_prior:
            print("MISSING  no recorded URL for", key)
            continue
        fetch_mom(key, mom_prior[key], old, out)
        print("ok", key)

    for item in CORPUS["mom_pages"]["add"]:
        prior = {
            "source": "mom",
            "key": item["key"],
            "url": item["url"],
            "licence": "mom_terms",
            "path": f"mom/{item['key']}.html",
        }
        body, status, final = get(item["url"])
        rec = {k: prior[k] for k in ("source", "key", "url", "licence")}
        rec |= {
            "final_url": final,
            "http_status": status,
            "reference_period": item["reference_period"],
            "release_type": item["release_type"],
            "title": title_of(body),
        }
        write(prior["path"], body, rec, old, out)
        print("ok", item["key"], "|", rec["title"])

    for u in CORPUS["mom_pages"]["unresolved"]:
        print("UNRESOLVED", u["reference_period"], u["release_type"], "-", u["reason"])

    out.sort(key=lambda r: r["path"])
    MANIFEST.write_text(json.dumps(out, indent=2) + "\n")
    print(f"manifest: {len(out)} files")


if __name__ == "__main__":
    main()
