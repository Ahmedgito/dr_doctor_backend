from __future__ import annotations

# Allow running the script directly (python scrapers/tools/export_db.py ...)
# by ensuring the package root is on sys.path. This makes `import scrapers...`
# work even when executing the file path instead of using `-m`.
import sys
import pathlib

root = pathlib.Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import argparse
import json
from typing import Any, Dict, Iterable, List, Optional

from scrapers.database.mongo_client import MongoClientManager


def normalize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    # Convert non-serializable types (ObjectId, datetime) to strings
    out: Dict[str, Any] = {}
    for k, v in doc.items():
        if k == "_id":
            out[k] = str(v)
            continue
        try:
            json.dumps({k: v})
            out[k] = v
        except TypeError:
            out[k] = str(v)
    return out


def export_collection(mongo: MongoClientManager, collection_name: str, out_path: str, fmt: str, query: Optional[Dict] = None, limit: Optional[int] = None, pretty: bool = False) -> None:
    coll = mongo.db[collection_name]
    cursor = coll.find(query or {})
    if limit:
        cursor = cursor.limit(limit)

    if fmt == "json":
        docs: List[Dict] = [normalize_doc(d) for d in cursor]
        with open(out_path, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(docs, f, indent=2, ensure_ascii=False)
            else:
                for d in docs:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"Exported {len(docs)} documents to {out_path}")
        return

    if fmt == "csv":
        import csv

        rows = [normalize_doc(d) for d in cursor]
        if not rows:
            print("No documents to export")
            return

        # union of all keys
        keys = sorted({k for r in rows for k in r.keys()})
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in keys})

        print(f"Exported {len(rows)} documents to {out_path}")
        return

    raise ValueError("Unsupported format: choose 'json' or 'csv'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a MongoDB collection to JSON or CSV")
    parser.add_argument("--collection", required=True, help="Collection name to export (e.g. doctors, hospitals)")
    parser.add_argument("--out", required=True, help="Output file path")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON array instead of JSON-lines")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mongo = MongoClientManager()
    try:
        export_collection(mongo, args.collection, args.out, args.format, limit=args.limit, pretty=args.pretty)
    finally:
        mongo.close()


if __name__ == "__main__":
    main()
