"""Data merging logic for Marham scrapers."""

from __future__ import annotations

from typing import Optional
from datetime import datetime

from scrapers.models.doctor_model import DoctorModel


class DataMerger:
    """Handles merging of existing and new doctor records."""

    @staticmethod
    def merge_doctor_records(existing: dict, new_model: DoctorModel) -> Optional[dict]:
        """Merge existing doctor document with data from new_model.

        Returns a dict of fields to set (for MongoDB $set) or None if no change.
        - Preserves existing richer fields when new_model has empty/None values.
        - Merges `hospitals` lists deduplicating by URL.

        Args:
            existing: Existing doctor document from database
            new_model: New DoctorModel instance to merge

        Returns:
            Dictionary of fields to update, or None if no changes needed
        """
        if not existing:
            return new_model.dict()

        existing_data = {k: v for k, v in existing.items() if k not in ("_id", "scraped_at")}
        new_data = {k: v for k, v in new_model.dict().items() if k not in ("_id", "scraped_at")}

        updated: dict = {}

        # Merge hospitals (list of dicts with possible fee/timings)
        existing_hospitals = existing_data.get("hospitals") or []
        if not isinstance(existing_hospitals, list):
            existing_hospitals = []
        new_hospitals = new_data.get("hospitals") or []

        # Build mapping by url (fallback to name if url missing)
        merged_map = {}
        for h in existing_hospitals:
            if isinstance(h, dict):
                key = h.get("url") or h.get("name")
                if key:
                    merged_map[key] = dict(h)

        for h in new_hospitals:
            if not isinstance(h, dict):
                continue
            key = h.get("url") or h.get("name")
            if not key:
                continue
            if key in merged_map:
                # update fields if new provides non-empty values
                for fk, fv in h.items():
                    if fv is None or (isinstance(fv, (list, str)) and len(fv) == 0):
                        continue
                    if merged_map[key].get(fk) != fv:
                        merged_map[key][fk] = fv
            else:
                merged_map[key] = dict(h)

        merged_hospitals = list(merged_map.values())
        # Update hospitals if:
        # 1. The merged list is different from existing (different content)
        # 2. Existing is None/missing but new has hospitals (even if empty list, we want to set it)
        # 3. Existing is None and new is empty list (initialize the field)
        existing_hospitals_is_none = existing_data.get("hospitals") is None
        if merged_hospitals != existing_hospitals or (existing_hospitals_is_none and new_hospitals is not None):
            updated["hospitals"] = merged_hospitals

        # For other fields, prefer non-empty values from new_data; otherwise keep existing
        for key, val in new_data.items():
            if key == "hospitals":
                continue
            if val is None or (isinstance(val, (list, str)) and len(val) == 0):
                # skip empty new values
                continue
            if existing_data.get(key) != val:
                updated[key] = val

        if not updated:
            return None

        updated["scraped_at"] = datetime.utcnow()
        return updated

