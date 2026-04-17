from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"

BASE_MAP_PATH = ASSETS_DIR / "base_map.png"
COORDS_PATH = DATA_DIR / "planet_coords.json"

COMMUNITY_WAR_STATUS = "https://api.helldivers2.dev/raw/api/v1/war/status"
COMMUNITY_WAR_INFO = "https://api.helldivers2.dev/raw/api/v1/war/info"
COMMUNITY_PLANETS = "https://api.helldivers2.dev/raw/api/v1/planets"

FALLBACK_WAR_STATUS = "https://helldiverstrainingmanual.com/api/v1/war/status"
FALLBACK_WAR_INFO = "https://helldiverstrainingmanual.com/api/v1/war/info"
FALLBACK_PLANETS = "https://helldiverstrainingmanual.com/api/v1/planets"

TIMEOUT = 20

OWNER_COLORS = {
    "Human": (70, 140, 255, 255),
    "Super Earth": (70, 140, 255, 255),
    "Terminid": (255, 205, 70, 255),
    "Automaton": (255, 90, 90, 255),
    "Illuminate": (185, 100, 255, 255),
    "Unknown": (170, 170, 170, 255),
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def fetch_json(primary_url: str, fallback_url: str, headers: dict[str, str] | None = None) -> Any:
    last_error = None
    attempts = [
        (primary_url, headers or {}),
        (fallback_url, {"Accept": "application/json"}),
    ]

    for url, hdrs in attempts:
        try:
            response = requests.get(url, headers=hdrs, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Failed to fetch both primary and fallback endpoints: {last_error}")


def derive_pages_base_url() -> str:
    explicit = os.getenv("PAGES_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not repo or "/" not in repo:
        raise RuntimeError(
            "Could not derive GitHub Pages base URL. Set PAGES_BASE_URL or GITHUB_REPOSITORY."
        )

    owner, repo_name = repo.split("/", 1)
    owner = owner.lower()

    if repo_name.lower() == f"{owner}.github.io":
        return f"https://{owner}.github.io"

    return f"https://{owner}.github.io/{repo_name}"


def first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_owner(owner_value: Any) -> str:
    if isinstance(owner_value, str):
        s = owner_value.strip().lower()
        if s in ("human", "super earth"):
            return "Human"
        if s == "terminid":
            return "Terminid"
        if s == "automaton":
            return "Automaton"
        if s == "illuminate":
            return "Illuminate"
        return owner_value.strip() or "Unknown"

    faction_map = {
        1: "Human",
        2: "Terminid",
        3: "Automaton",
        4: "Illuminate",
    }
    return faction_map.get(owner_value, "Unknown")


def looks_like_planet_info_record(item: Any) -> bool:
    if not isinstance(item, dict):
        return False

    has_index = "index" in item
    has_position = isinstance(item.get("position"), dict) and (
        "x" in item["position"] and "y" in item["position"]
    )
    has_name = "name" in item
    has_sector = "sector" in item

    return has_index and (has_position or has_name or has_sector)


def collect_planet_info_records(payload: Any, found: dict[int, dict[str, Any]] | None = None) -> dict[int, dict[str, Any]]:
    if found is None:
        found = {}

    if isinstance(payload, dict):
        if looks_like_planet_info_record(payload):
            idx = as_int(payload.get("index"), -1)
            if idx >= 0:
                found[idx] = payload

        for value in payload.values():
            collect_planet_info_records(value, found)

    elif isinstance(payload, list):
        for item in payload:
            collect_planet_info_records(item, found)

    return found


def looks_like_status_record(item: Any) -> bool:
    if not isinstance(item, dict):
        return False

    has_index = "index" in item or "planetIndex" in item
    has_live_fields = any(
        key in item
        for key in (
            "health",
            "maxHealth",
            "owner",
            "currentOwner",
            "statistics",
            "players",
            "playerCount",
            "regenPerSecond",
            "attacking",
            "event",
            "liberation",
        )
    )
    return has_index and has_live_fields


def collect_status_records(payload: Any, found: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if found is None:
        found = []

    if isinstance(payload, dict):
        if looks_like_status_record(payload):
            found.append(payload)

        for value in payload.values():
            collect_status_records(value, found)

    elif isinstance(payload, list):
        for item in payload:
            collect_status_records(item, found)

    return found


def dedupe_status_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_index: dict[int, dict[str, Any]] = {}

    for record in records:
        idx = as_int(first_non_null(record.get("index"), record.get("planetIndex")), -1)
        if idx >= 0:
            by_index[idx] = record

    return list(by_index.values())


def get_planet_position(meta: dict[str, Any]) -> tuple[float | None, float | None]:
    pos = meta.get("position")
    if isinstance(pos, dict):
        x = first_non_null(pos.get("x"), pos.get("X"), pos.get("positionX"))
        y = first_non_null(pos.get("y"), pos.get("Y"), pos.get("positionY"))
        if x is not None and y is not None:
            return as_float(x), as_float(y)

    x = first_non_null(meta.get("x"), meta.get("X"), meta.get("positionX"))
    y = first_non_null(meta.get("y"), meta.get("Y"), meta.get("positionY"))
    if x is not None and y is not None:
        return as_float(x), as_float(y)

    return None, None


def compute_position_bounds(planet_lookup: dict[int, dict[str, Any]]) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []
    for meta in planet_lookup.values():
        x, y = get_planet_position(meta)
        if x is not None and y is not None:
            points.append((x, y))

    if not points:
        return -1.0, 1.0, -1.0, 1.0

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if math.isclose(min_x, max_x):
        min_x, max_x = -1.0, 1.0
    if math.isclose(min_y, max_y):
        min_y, max_y = -1.0, 1.0

    return min_x, max_x, min_y, max_y


def get_projected_coords(
    index: int,
    meta: dict[str, Any],
    manual_coords: dict[str, Any],
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, str]:
    manual = manual_coords.get(str(index))
    if isinstance(manual, dict) and "x" in manual and "y" in manual:
        return clamp(as_float(manual["x"]), 0.0, 1.0), clamp(as_float(manual["y"]), 0.0, 1.0), "manual"

    raw_x, raw_y = get_planet_position(meta)
    if raw_x is None or raw_y is None:
        return 0.5, 0.5, "fallback"

    # HD2 coordinates are centered around Super Earth at (0, 0),
    # so project directly into the circular board.
    norm_x = 0.5 + (raw_x * 0.5)
    norm_y = 0.5 - (raw_y * 0.5)

    return clamp(norm_x, 0.0, 1.0), clamp(norm_y, 0.0, 1.0), "auto"


def get_players(status_entry: dict[str, Any]) -> int:
    stats = status_entry.get("statistics", {})
    if isinstance(stats, dict):
        value = first_non_null(stats.get("playerCount"), stats.get("players"))
        if value is not None:
            return as_int(value, 0)

    return as_int(first_non_null(status_entry.get("playerCount"), status_entry.get("players")), 0)


def get_attacking(status_entry: dict[str, Any]) -> list[int]:
    raw = status_entry.get("attacking")
    if raw is None:
        return []

    if isinstance(raw, list):
        out: list[int] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(as_int(first_non_null(item.get("index"), item.get("planetIndex")), -1))
            else:
                out.append(as_int(item, -1))
        return [x for x in out if x >= 0]

    return []


def get_liberation(status_entry: dict[str, Any]) -> float:
    direct = first_non_null(
        status_entry.get("liberation"),
        status_entry.get("liberationPercent"),
        status_entry.get("percentage"),
        status_entry.get("progress"),
    )
    if direct is not None:
        value = as_float(direct, 0.0)
        if value <= 1.0:
            value *= 100.0
        return clamp(value, 0.0, 100.0)

    health = as_float(status_entry.get("health"), 0.0)
    max_health = as_float(status_entry.get("maxHealth"), 0.0)
    if max_health > 0:
        return clamp(100.0 * (1.0 - (health / max_health)), 0.0, 100.0)

    return 0.0


def get_event_type(status_entry: dict[str, Any], attacking: list[int], players: int) -> str:
    if status_entry.get("event") is not None:
        return "event"
    if attacking:
        return "attack"
    if players > 0:
        return "active"
    return "none"


def build_planet_records(
    status_list: list[dict[str, Any]],
    war_info_lookup: dict[int, dict[str, Any]],
    biome_lookup: dict[int, dict[str, Any]],
    manual_coords: dict[str, Any],
) -> list[dict[str, Any]]:
    bounds = compute_position_bounds(war_info_lookup)
    records: list[dict[str, Any]] = []

    for status in status_list:
        index = as_int(first_non_null(status.get("index"), status.get("planetIndex")), -1)
        if index < 0:
            continue

        info = war_info_lookup.get(index, {})
        biome_meta = biome_lookup.get(index, {})

        x, y, coord_source = get_projected_coords(index, info, manual_coords, bounds)

        name = str(first_non_null(info.get("name"), biome_meta.get("name"), status.get("name"), f"Planet {index}"))
        sector = str(first_non_null(info.get("sector"), status.get("sector"), ""))

        owner = normalize_owner(
            first_non_null(
                status.get("owner"),
                status.get("currentOwner"),
                info.get("currentOwner"),
                info.get("owner"),
            )
        )

        players = get_players(status)
        attacking = get_attacking(status)
        liberation = round(get_liberation(status), 2)
        event_type = get_event_type(status, attacking, players)

        biome = first_non_null(biome_meta.get("biome"), biome_meta.get("environment"), "")
        if isinstance(biome, dict):
            biome = biome.get("name", "")

        hazards = biome_meta.get("environmentals", [])
        if not isinstance(hazards, list):
            hazards = []

        normalized_hazards: list[str] = []
        for item in hazards:
            if isinstance(item, dict):
                hv = first_non_null(item.get("name"), item.get("description"))
                if hv:
                    normalized_hazards.append(str(hv))
            elif item:
                normalized_hazards.append(str(item))

        records.append(
            {
                "index": index,
                "name": name,
                "sector": sector,
                "x": round(x, 6),
                "y": round(y, 6),
                "owner": owner,
                "liberation": liberation,
                "players": players,
                "eventType": event_type,
                "attacking": attacking,
                "biome": biome or "",
                "hazards": normalized_hazards,
                "coordSource": coord_source,
            }
        )

    records.sort(key=lambda p: (p["name"].lower(), p["index"]))
    return records


def ensure_base_map() -> Image.Image:
    if BASE_MAP_PATH.exists():
        return Image.open(BASE_MAP_PATH).convert("RGBA")

    img = Image.new("RGBA", (1920, 1080), (5, 10, 24, 255))
    draw = ImageDraw.Draw(img)
    for i in range(0, img.width, 120):
        draw.line((i, 0, i, img.height), fill=(15, 25, 45, 255), width=1)
    for i in range(0, img.height, 120):
        draw.line((0, i, img.width, i), fill=(15, 25, 45, 255), width=1)
    return img


def draw_ring(draw: ImageDraw.ImageDraw, x: int, y: int, r: int, color: tuple[int, int, int, int], width: int = 2):
    for offset in range(width):
        draw.ellipse((x - r - offset, y - r - offset, x + r + offset, y + r + offset), outline=color)


def render_map(planets: list[dict[str, Any]], output_path: Path) -> None:
    base = ensure_base_map()
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    width, height = base.size
    by_index = {p["index"]: p for p in planets}

    for planet in planets:
        if not planet["attacking"]:
            continue

        x1 = int(planet["x"] * width)
        y1 = int(planet["y"] * height)

        for target_idx in planet["attacking"]:
            target = by_index.get(target_idx)
            if not target:
                continue

            x2 = int(target["x"] * width)
            y2 = int(target["y"] * height)
            draw.line((x1, y1, x2, y2), fill=(255, 120, 120, 140), width=2)

    for planet in planets:
        x = int(planet["x"] * width)
        y = int(planet["y"] * height)

        color = OWNER_COLORS.get(planet["owner"], OWNER_COLORS["Unknown"])
        players = planet["players"]
        event_type = planet["eventType"]

        radius = 4
        if players >= 5000:
            radius = 6
        if event_type in ("event", "attack"):
            radius = 8

        glow = (color[0], color[1], color[2], 80)
        draw.ellipse((x - radius - 5, y - radius - 5, x + radius + 5, y + radius + 5), fill=glow)

        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline=(255, 255, 255, 220))

        if event_type in ("event", "attack"):
            draw_ring(draw, x, y, radius + 5, (255, 255, 255, 220), width=2)

        if players >= 5000 or event_type in ("event", "attack"):
            label = planet["name"]
            draw.text((x + 10, y - 8), label, font=font, fill=(255, 255, 255, 230))

    final_image = Image.alpha_composite(base, overlay)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_image.save(output_path, format="PNG")


def build_index_html(updated_at: str, base_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Helldivers 2 VRChat Map Relay</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      background: #0b1020;
      color: #e8ecff;
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 2rem;
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    img {{
      width: 100%;
      height: auto;
      border-radius: 12px;
      border: 1px solid #2d3a67;
      background: #050814;
    }}
    code {{
      background: #131a31;
      padding: 0.2rem 0.4rem;
      border-radius: 6px;
    }}
    a {{
      color: #90b8ff;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Helldivers 2 VRChat Map Relay</h1>
    <p>Updated: <strong>{updated_at}</strong></p>
    <p>Files:</p>
    <ul>
      <li><a href="{base_url}/map.png">map.png</a></li>
      <li><a href="{base_url}/state.json">state.json</a></li>
    </ul>
    <img src="{base_url}/map.png" alt="Galactic map">
  </div>
</body>
</html>
"""


def main() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    headers = {
        "Accept": "application/json",
        "X-Super-Client": os.getenv("HD2_SUPER_CLIENT", "dakota-vrchat-galactic-map"),
    }

    contact = os.getenv("HD2_SUPER_CONTACT", "").strip()
    if contact:
        headers["X-Super-Contact"] = contact

    war_status_payload = fetch_json(COMMUNITY_WAR_STATUS, FALLBACK_WAR_STATUS, headers=headers)
    war_info_payload = fetch_json(COMMUNITY_WAR_INFO, FALLBACK_WAR_INFO, headers=headers)
    planets_payload = fetch_json(COMMUNITY_PLANETS, FALLBACK_PLANETS, headers=headers)

    war_info_lookup = collect_planet_info_records(war_info_payload)
    biome_lookup = collect_planet_info_records(planets_payload)

    status_candidates = collect_status_records(war_status_payload)
    status_list = dedupe_status_records(status_candidates)

    manual_coords = load_json_file(COORDS_PATH, default={})

    print(f"war_info planets found: {len(war_info_lookup)}")
    print(f"biome planets found: {len(biome_lookup)}")
    print(f"status records found: {len(status_list)}")

    planets = build_planet_records(status_list, war_info_lookup, biome_lookup, manual_coords)

    base_url = derive_pages_base_url()
    updated_at = datetime.now(timezone.utc).isoformat()

    state = {
        "version": 2,
        "updatedAt": updated_at,
        "backgroundImage": f"{base_url}/map.png",
        "planets": planets,
    }

    save_json_file(SITE_DIR / "state.json", state)
    render_map(planets, SITE_DIR / "map.png")

    with (SITE_DIR / "index.html").open("w", encoding="utf-8") as f:
        f.write(build_index_html(updated_at, base_url))

    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Generated {SITE_DIR / 'state.json'}")
    print(f"Generated {SITE_DIR / 'map.png'}")
    print(f"Generated {SITE_DIR / 'index.html'}")
    print(f"Planet count: {len(planets)}")
    print(f"Base URL: {base_url}")


if __name__ == "__main__":
    main()
