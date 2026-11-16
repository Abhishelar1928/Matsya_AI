"""
MatsyaAI Maharashtra — Expedition sync (device -> server).

Idempotent: every record carries a device-generated ``client_uuid``; inserts use
``ON CONFLICT (client_uuid) DO NOTHING`` so retries after flaky reconnections
never create duplicates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.expedition import (
    CatchRecord,
    Expedition,
    ExpeditionTrackPoint,
    FieldObservation,
)


def _point_wkt(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    if lat is None or lon is None:
        return None
    return f"SRID=4326;POINT({lon} {lat})"


async def _insert_idempotent(db: AsyncSession, model, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(model).values(rows).on_conflict_do_nothing(index_elements=["client_uuid"])
    stmt = stmt.returning(model.client_uuid)
    result = await db.execute(stmt)
    return len(result.fetchall())


async def apply_sync(
    db: AsyncSession,
    expedition: Expedition,
    track_points: List[Dict[str, Any]],
    catches: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    tp_rows = [{
        "client_uuid": t["client_uuid"],
        "expedition_id": expedition.id,
        "recorded_at": t["recorded_at"],
        "latitude": t["latitude"],
        "longitude": t["longitude"],
        "geom": _point_wkt(t["latitude"], t["longitude"]),
        "speed_mps": t.get("speed_mps"),
        "heading_deg": t.get("heading_deg"),
        "accuracy_m": t.get("accuracy_m"),
        "synced_at": now,
    } for t in track_points]

    catch_rows = [{
        "client_uuid": c["client_uuid"],
        "expedition_id": expedition.id,
        "recorded_at": c["recorded_at"],
        "latitude": c.get("latitude"),
        "longitude": c.get("longitude"),
        "geom": _point_wkt(c.get("latitude"), c.get("longitude")),
        "species": c["species"],
        "weight_kg": c.get("weight_kg"),
        "notes": c.get("notes"),
        "synced_at": now,
    } for c in catches]

    obs_rows = [{
        "client_uuid": o["client_uuid"],
        "expedition_id": expedition.id,
        "recorded_at": o["recorded_at"],
        "latitude": o.get("latitude"),
        "longitude": o.get("longitude"),
        "geom": _point_wkt(o.get("latitude"), o.get("longitude")),
        "observation_type": o["observation_type"],
        "value": o.get("value"),
        "notes": o.get("notes"),
        "synced_at": now,
    } for o in observations]

    try:
        inserted = {
            "track_points": await _insert_idempotent(db, ExpeditionTrackPoint, tp_rows),
            "catches": await _insert_idempotent(db, CatchRecord, catch_rows),
            "observations": await _insert_idempotent(db, FieldObservation, obs_rows),
        }
        expedition.last_synced_at = now
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    received = {"track_points": len(tp_rows), "catches": len(catch_rows), "observations": len(obs_rows)}
    return {
        "received": received,
        "inserted": inserted,
        "duplicates": {k: received[k] - inserted[k] for k in received},
        "acknowledged_uuids": [r["client_uuid"] for r in tp_rows + catch_rows + obs_rows],
        "synced_at": now.isoformat(),
    }
