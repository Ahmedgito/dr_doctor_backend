from __future__ import annotations

# Allow running the script directly (python scrapers/tools/import_db.py ...)
# by ensuring the package root is on sys.path. This makes `import scrapers...`
# work even when executing the file path instead of using `-m`.
import sys
import pathlib

root = pathlib.Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import argparse
import csv
import json
from typing import Any, Dict, Iterable, List, Optional

from scrapers.database.mongo_client import MongoClientManager


def load_json_lines(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_json_array(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
            return data
        raise ValueError("JSON file does not contain an array")


def load_csv(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: (v if v != "" else None) for k, v in row.items()}


def import_collection(mongo: MongoClientManager, collection_name: str, in_path: str, fmt: str, upsert: bool = True) -> None:
    coll = mongo.db[collection_name]
    docs: Iterable[Dict[str, Any]]
    if fmt == "jsonl":
        docs = load_json_lines(in_path)
    elif fmt == "json":
        docs = load_json_array(in_path)
    elif fmt == "csv":
        docs = load_csv(in_path)
    else:
        raise ValueError("Unsupported format")

    inserted = 0
    updated = 0
    for d in docs:
        # Remove _id if present
        d.pop("_id", None)

        if upsert:
            # Choose key for upsert: doctors -> profile_url, hospitals -> url
            if collection_name == "doctors" and d.get("profile_url"):
                res = coll.update_one({"profile_url": d.get("profile_url")}, {"$set": d}, upsert=True)
                if getattr(res, "matched_count", 0):
                    updated += 1
                else:
                    inserted += 1
                continue

            if collection_name == "hospitals" and d.get("url"):
                res = coll.update_one({"url": d.get("url")}, {"$set": d}, upsert=True)
                if getattr(res, "matched_count", 0):
                    updated += 1
                else:
                    inserted += 1
                continue

        # Fallback: insert
        try:
            coll.insert_one(d)
            inserted += 1
        except Exception:
            # ignore duplicates/failures
            pass

    print(f"Inserted: {inserted}, Updated: {updated}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import JSON/CSV data into MongoDB collection")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--in", dest="infile", required=True)
    parser.add_argument("--format", choices=["jsonl", "json", "csv"], default="jsonl")
    parser.add_argument("--no-upsert", dest="upsert", action="store_false", help="Do not upsert, always insert")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mongo = MongoClientManager()
    try:
        import_collection(mongo, args.collection, args.infile, args.format, upsert=args.upsert)
    finally:
        mongo.close()


if __name__ == "__main__":
    main()
