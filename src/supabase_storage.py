from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import requests

from src.settings import SUPABASE_SCHEMA, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    service_role_key: str
    schema: str = SUPABASE_SCHEMA

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.service_role_key)


def get_supabase_config() -> SupabaseConfig:
    return SupabaseConfig(
        url=SUPABASE_URL,
        service_role_key=SUPABASE_SERVICE_ROLE_KEY,
        schema=SUPABASE_SCHEMA,
    )


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat() if not pd.isna(value) else None
    if isinstance(value, str) and value and value[0] in ("{", "["):
        try:
            import json as _json
            return _json.loads(value)
        except Exception:
            pass
    return value


def dataframe_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    records: list[dict] = []
    for row in df.to_dict("records"):
        records.append({key: _json_safe(value) for key, value in row.items()})
    return records


class SupabaseWarehouseClient:
    def __init__(self, config: SupabaseConfig | None = None):
        self.config = config or get_supabase_config()
        self.session = requests.Session()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def _headers(self, write: bool = False) -> dict[str, str]:
        headers = {
            "apikey": self.config.service_role_key,
            "Authorization": f"Bearer {self.config.service_role_key}",
            "Accept-Profile": self.config.schema,
        }
        if write:
            headers["Content-Profile"] = self.config.schema
            headers["Content-Type"] = "application/json"
        return headers

    def upsert_rows(self, table: str, rows: Iterable[dict], on_conflict: str) -> None:
        payload = list(rows)
        if not payload or not self.enabled:
            return
        response = self.session.post(
            f"{self.config.url}/rest/v1/{table}",
            headers={
                **self._headers(write=True),
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            params={"on_conflict": on_conflict},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()

    def replace_table(self, table: str, rows: Iterable[dict], on_conflict: str) -> None:
        payload = list(rows)
        if not self.enabled:
            return
        delete_response = self.session.delete(
            f"{self.config.url}/rest/v1/{table}",
            headers=self._headers(write=True),
            params={"id": "gt.0"},
            timeout=60,
        )
        if delete_response.status_code not in {200, 204}:
            delete_response.raise_for_status()
        self.upsert_rows(table, payload, on_conflict=on_conflict)

