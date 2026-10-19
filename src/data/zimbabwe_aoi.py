"""
Hardcoded AOI helpers for Zimbabwe provinces / major cities.

Used only as last-resort fallback when GAUL files and Nominatim both fail,
so CLI runs for any of the 10 provinces still resolve a usable bbox.
"""
from __future__ import annotations

from typing import Optional

# Approximate WGS84 bboxes: (minx, miny, maxx, maxy)
# Sources: indicative admin extents — good enough for streaming QA, not cadastral.

ZIMBABWE_COUNTRY = (25.2, -22.5, 33.1, -15.6)

PROVINCE_BBOX: dict[str, tuple[float, float, float, float]] = {
    "harare": (30.85, -18.05, 31.25, -17.65),
    "bulawayo": (28.45, -20.25, 28.75, -19.95),
    "manicaland": (31.4, -21.0, 33.1, -17.2),
    "mashonaland central": (30.2, -17.8, 32.0, -15.6),
    "mashonaland east": (30.8, -19.5, 33.0, -16.8),
    "mashonaland west": (28.5, -18.8, 30.9, -15.6),
    "masvingo": (29.8, -22.4, 32.5, -19.2),
    "matabeleland north": (25.2, -19.0, 29.5, -15.6),
    "matabeleland south": (26.5, -22.5, 31.2, -19.8),
    "midlands": (28.3, -20.8, 30.8, -18.0),
}

# Common aliases / city names → province key
ALIASES: dict[str, str] = {
    "harare province": "harare",
    "harare urban": "harare",
    "harare rural": "harare",
    "bulawayo province": "bulawayo",
    "mutare": "manicaland",
    "gweru": "midlands",
    "kwekwe": "midlands",
    "chinhoyi": "mashonaland west",
    "bindura": "mashonaland central",
    "marondera": "mashonaland east",
    "victoria falls": "matabeleland north",
    "hwange": "matabeleland north",
    "beitbridge": "matabeleland south",
    "gwanda": "matabeleland south",
    "chiredzi": "masvingo",
    "mbare": "harare",
    "highlands": "harare",
    "avondale": "harare",
}


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    return " ".join(str(s).strip().lower().replace("_", " ").split())


def lookup_zimbabwe_bbox(
    country: Optional[str] = None,
    adm1: Optional[str] = None,
    adm2: Optional[str] = None,
    adm3: Optional[str] = None,
) -> Optional[tuple[tuple[float, float, float, float], str]]:
    """
    Return (bounds, label) if we can resolve from hardcoded table, else None.
    Prefer finer admin when aliased; else province; else country.
    """
    c = _norm(country)
    if c and c not in ("zimbabwe", "zw", "rep. of zimbabwe", "republic of zimbabwe"):
        # Still allow if adm1 matches a known ZW province (user omitted country)
        pass

    for candidate in (adm3, adm2, adm1):
        key = _norm(candidate)
        if not key:
            continue
        if key in ALIASES:
            key = ALIASES[key]
        if key in PROVINCE_BBOX:
            return PROVINCE_BBOX[key], f"hardcoded:{key}"

    # Partial contains match
    for candidate in (adm1, adm2, adm3):
        key = _norm(candidate)
        if not key:
            continue
        for prov, bbox in PROVINCE_BBOX.items():
            if key in prov or prov in key:
                return bbox, f"hardcoded_partial:{prov}"

    if c in ("zimbabwe", "zw", "") or not c:
        if adm1 or adm2 or adm3 or c == "zimbabwe" or c == "zw":
            return ZIMBABWE_COUNTRY, "hardcoded:zimbabwe"
    return None


def parse_adm_list(value: Optional[str | list]) -> list[str]:
    """Split comma/semicolon-separated admin names into a clean list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        parts = []
        for v in value:
            parts.extend(parse_adm_list(str(v)))
        return parts
    s = str(value).replace(";", ",")
    return [p.strip().strip('"').strip("'") for p in s.split(",") if p.strip()]


def merge_bboxes(
    boxes: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Union of WGS84 bboxes (minx, miny, maxx, maxy)."""
    if not boxes:
        raise ValueError("No bboxes to merge")
    minx = min(b[0] for b in boxes)
    miny = min(b[1] for b in boxes)
    maxx = max(b[2] for b in boxes)
    maxy = max(b[3] for b in boxes)
    return (float(minx), float(miny), float(maxx), float(maxy))


def lookup_multi_province_bbox(
    country: Optional[str],
    adm1_list: list[str],
) -> Optional[tuple[tuple[float, float, float, float], str, list[str]]]:
    """
    Resolve one or more Zimbabwe provinces to a merged bbox.
    Returns (bounds, label, resolved_names) or None.
    """
    boxes = []
    names = []
    for name in adm1_list:
        hit = lookup_zimbabwe_bbox(country, name, None, None)
        if hit is None:
            continue
        boxes.append(hit[0])
        names.append(name)
    if not boxes:
        return None
    return merge_bboxes(boxes), f"hardcoded_multi:{','.join(names)}", names
