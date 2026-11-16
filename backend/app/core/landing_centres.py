"""
MatsyaAI Maharashtra — Canonical Landing Centre Registry.

Single source of truth for landing centre locations used by the map UI and
Offline Expedition Mode (route start points, emergency return destinations).

Coordinates come from database/seeds/landing_centres_mock.py and are flagged
``verified=False`` until checked against Maharashtra Fisheries Department data.

NOTE: backend/app/ml/dataset_builder.py keeps its own ``_LANDING_CENTRES`` list.
That list feeds model features (distance to nearest centre) for the frozen
Phase 3 model and must NOT be changed to match this registry, or inference
features would drift from training.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

COORDINATE_SOURCE = "database/seeds/landing_centres_mock.py (unverified)"


@dataclass(frozen=True)
class LandingCentreInfo:
    id: str
    name: str
    name_mr: str
    district: str
    latitude: float
    longitude: float
    verified: bool = False
    source: str = COORDINATE_SOURCE

    def to_dict(self) -> Dict:
        return asdict(self)


LANDING_CENTRES: List[LandingCentreInfo] = [
    LandingCentreInfo("satpati", "Satpati", "सातपाटी", "Palghar", 19.7258, 72.7058),
    LandingCentreInfo("arnala", "Arnala", "अर्नाळा", "Palghar", 19.4589, 72.7483),
    LandingCentreInfo("versova", "Versova", "वर्सोवा", "Mumbai", 19.1334, 72.8146),
    LandingCentreInfo("sassoon_dock", "Sassoon Dock", "ससून डॉक", "Mumbai", 18.9172, 72.8258),
    LandingCentreInfo("alibag", "Alibag", "अलिबाग", "Raigad", 18.6416, 72.8722),
    LandingCentreInfo("murud", "Murud", "मुरुड", "Raigad", 18.3269, 72.9645),
    LandingCentreInfo("harnai", "Harnai", "हर्णै", "Ratnagiri", 17.8131, 73.0908),
    LandingCentreInfo("mirkarwada", "Mirkarwada", "मिरकरवाडा", "Ratnagiri", 16.9958, 73.2758),
    LandingCentreInfo("malvan", "Malvan", "मालवण", "Sindhudurg", 16.0632, 73.4682),
    LandingCentreInfo("vengurla", "Vengurla", "वेंगुर्ला", "Sindhudurg", 15.8617, 73.6267),
]

_BY_ID: Dict[str, LandingCentreInfo] = {lc.id: lc for lc in LANDING_CENTRES}


def get_landing_centre(centre_id: str) -> Optional[LandingCentreInfo]:
    return _BY_ID.get(centre_id)


def landing_centres_as_dicts() -> List[Dict]:
    return [lc.to_dict() for lc in LANDING_CENTRES]
