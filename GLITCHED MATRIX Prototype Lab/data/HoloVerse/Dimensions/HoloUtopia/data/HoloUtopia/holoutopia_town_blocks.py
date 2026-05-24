"""HoloUtopia authored town-block loader and lightweight Panda3D renderer.

Pass 16 keeps this deliberately additive and data-first:
- Town/district definitions live under data/database/utopia/towns.
- City-wide district placement lives in data/database/utopia/city_grid_atlas.json.
- Neighborhood detail lives under data/database/utopia/neighborhoods.
- Residential lots can define 3D massing/capacity profiles for future NPC assignment.
- Residential infill can exist in non-residential districts when it fits the district role.
- Every town block now has a 3D structure_massing_profile so districts render as purposeful exterior volumes.
- City-wide citizens live in data/database/utopia/citizens with authored homes, jobs, schedules, and friends.
- The city atlas is complete as a 3x3 district grid with Civic Commons Delta and Glitched Quarantine Epsilon added.
- Building interiors are authored separately and load only when a building is highlighted.
- Residential buildings sit on authored foundation pads; no arbitrary lines should cut through building bases or roofs.
- NPC identities, schedules, jobs, activities, and friendship links are authored separately from runtime state.
- Building highlight inspection is handled by holoutopia_building_inspector with lazy interiors and read-only authored data.
- This module can validate/load those authored JSON files without Panda3D.
- Panda3D imports happen only inside render helpers, so validators and tools
  stay safe in headless CI or packaging checks.

Drop-in hook for the HoloVerse hub/world once the caller has a root node:

    from holoutopia_town_blocks import attach_holoutopia_town
    self.holoutopia_root = attach_holoutopia_town(self.render, ROOT)

The returned NodePath is named from the town id, for example
``holoutopia_central_core_civic_ring``, ``holoutopia_market_crossing``, ``holoutopia_security_gate``, ``holoutopia_industrial_yard_alpha``, ``holoutopia_harbor_grid_beta``, or ``holoutopia_archive_quarter_gamma``, and
can be removed cleanly with ``removeNode()``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable


DEFAULT_TOWN_ID = "central_core_civic_ring"
DEFAULT_CITY_ATLAS_ID = "utopia_alpha_city_grid"
DEFAULT_NEIGHBORHOOD_ID = "residential_alpha_neighborhood_01"
TOWN_DATA_RELATIVE = Path("../database/utopia/towns")
NEIGHBORHOOD_DATA_RELATIVE = Path("../database/utopia/neighborhoods")
CITY_ATLAS_NAME = "city_grid_atlas.json"

STRUCTURE_VARIANT_RELATIVE = Path("../database/utopia/structure_variants")
STRUCTURE_VARIANT_CATALOG_NAME = "structure_variant_catalog.json"
CITIZEN_DATA_RELATIVE = Path("../database/utopia/citizens")



def structure_variant_dir(holoverse_root: Path | str | None = None) -> Path:
    """Resolve the authored Utopia structure variant catalog folder."""
    return utopia_data_dir(holoverse_root) / "structure_variants"


def structure_variant_catalog_path(holoverse_root: Path | str | None = None) -> Path:
    """Return the district structure variant catalog path."""
    return structure_variant_dir(holoverse_root) / STRUCTURE_VARIANT_CATALOG_NAME


def load_structure_variant_catalog(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load the district structure-variant catalog without mutating runtime state."""
    path = structure_variant_catalog_path(holoverse_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaTownError(f"Structure variant catalog missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaTownError(f"Structure variant catalog JSON error in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaTownError(f"Structure variant catalog must contain a JSON object: {path}")
    return data


def validate_structure_variant_profile(town: dict[str, Any], source_path: Path | None = None) -> None:
    """Validate per-district structure variants, purposes, and block references."""
    label = str(source_path or town.get("id") or "<town>")
    profile = town.get("structure_variant_profile")
    if not isinstance(profile, dict):
        raise HoloUtopiaTownError(f"{label}: missing structure_variant_profile")
    purposes = profile.get("purpose_layers")
    variants = profile.get("variant_library")
    if not isinstance(purposes, list) or not purposes:
        raise HoloUtopiaTownError(f"{label}: structure_variant_profile.purpose_layers must be a non-empty list")
    if not isinstance(variants, list) or not variants:
        raise HoloUtopiaTownError(f"{label}: structure_variant_profile.variant_library must be a non-empty list")
    purpose_ids: set[str] = set()
    for purpose in purposes:
        if not isinstance(purpose, dict):
            raise HoloUtopiaTownError(f"{label}: purpose layer entries must be objects")
        purpose_id = _required_id(purpose, f"{label}.structure_variant_profile.purpose_layers")
        if purpose_id in purpose_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate purpose id {purpose_id!r}")
        purpose_ids.add(purpose_id)
    variant_ids: set[str] = set()
    variant_to_purpose: dict[str, str] = {}
    legal_interiors = {"exterior_only", "highlight_only", "locked_until_story"}
    for variant in variants:
        if not isinstance(variant, dict):
            raise HoloUtopiaTownError(f"{label}: variant entries must be objects")
        variant_id = _required_id(variant, f"{label}.structure_variant_profile.variant_library")
        if variant_id in variant_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate variant id {variant_id!r}")
        variant_ids.add(variant_id)
        purpose_id = str(variant.get("purpose_id", "")).strip()
        if purpose_id not in purpose_ids:
            raise HoloUtopiaTownError(f"{label}: variant {variant_id!r} references missing purpose {purpose_id!r}")
        variant_to_purpose[variant_id] = purpose_id
        if str(variant.get("interior_policy", "")).strip() not in legal_interiors:
            raise HoloUtopiaTownError(f"{label}: variant {variant_id!r} has invalid interior_policy {variant.get('interior_policy')!r}")
        if not isinstance(variant.get("schedule_affordances"), list) or not variant.get("schedule_affordances"):
            raise HoloUtopiaTownError(f"{label}: variant {variant_id!r} must define schedule_affordances")
    for block in town.get("town_blocks", []):
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id", "<block>"))
        variant_id = str(block.get("structure_variant_id", "")).strip()
        purpose_id = str(block.get("purpose_id", "")).strip()
        if variant_id not in variant_ids:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} references missing structure_variant_id {variant_id!r}")
        if purpose_id not in purpose_ids:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} references missing purpose_id {purpose_id!r}")
        if purpose_id != variant_to_purpose.get(variant_id):
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} purpose {purpose_id!r} does not match variant {variant_id!r}")
        if not isinstance(block.get("activity_affordances"), list) or not block.get("activity_affordances"):
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} must define activity_affordances")
        if str(block.get("interior_policy", "")).strip() not in legal_interiors:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} has invalid interior_policy {block.get('interior_policy')!r}")


def validate_structure_massing_profile(town: dict[str, Any], source_path: Path | None = None) -> None:
    """Validate every district block has purposeful 3D exterior massing."""
    label = str(source_path or town.get("id") or "<town>")
    legal_height = {"low", "mid", "tall"}
    legal_floor_bands = {"none", "outer_perimeter_only"}
    for block in town.get("town_blocks", []):
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id", "<block>"))
        profile = block.get("structure_massing_profile")
        if not isinstance(profile, dict):
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} missing structure_massing_profile")
        for key in ("massing_kind", "height_class", "floor_count", "height_units", "footprint_scale", "base_pad_scale", "roof_profile", "visual_policy"):
            if key not in profile:
                raise HoloUtopiaTownError(f"{label}: block {block_id!r} structure_massing_profile missing {key!r}")
        if str(profile.get("height_class")) not in legal_height:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} invalid massing height_class {profile.get('height_class')!r}")
        try:
            floor_count = int(profile.get("floor_count"))
        except Exception as exc:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} floor_count must be an integer") from exc
        if floor_count < 1 or floor_count > 24:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} floor_count must be 1..24")
        height = _positive_float(profile.get("height_units"), f"{label}.{block_id}.structure_massing_profile.height_units")
        if height > 180:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} height_units too high for district massing: {height}")
        for scale_key in ("footprint_scale", "base_pad_scale"):
            sx, sy = _local_size_pair(profile.get(scale_key), f"{label}.{block_id}.{scale_key}")
            if sx > 1.30 or sy > 1.30:
                raise HoloUtopiaTownError(f"{label}: block {block_id!r} {scale_key} must stay <= 1.30")
        visual = profile.get("visual_policy")
        if not isinstance(visual, dict):
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} visual_policy must be an object")
        if visual.get("draw_as_3d") is not True:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} visual_policy.draw_as_3d must be true")
        if visual.get("foundation_first") is not True:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} visual_policy.foundation_first must be true")
        if visual.get("no_arbitrary_diagonals") is not True:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} must not allow arbitrary diagonals")
        if str(visual.get("floor_bands")) not in legal_floor_bands:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} invalid floor_bands {visual.get('floor_bands')!r}")
        if str(visual.get("interior_lines")) != "highlight_only":
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} interior lines must be highlight_only")



class HoloUtopiaTownError(ValueError):
    """Raised when authored HoloUtopia town data is invalid."""


@dataclass(frozen=True)
class TownPoint:
    x: float
    y: float


@dataclass(frozen=True)
class TownBounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


def _data_root_from_holoverse_root(holoverse_root: Path) -> Path:
    """Return the shared data directory for HoloVerse/HoloUtopia runtime folders."""
    root = Path(holoverse_root).resolve()
    if (root / "database" / "utopia").exists():
        return root
    if (root / "data" / "database" / "utopia").exists():
        return root / "data"
    if (root.parent / "database" / "utopia").exists():
        return root.parent
    if root.name.lower() in {"holoverse", "holoutopia"}:
        return root.parent
    return root


def town_data_dir(holoverse_root: Path | str | None = None) -> Path:
    """Resolve the authored Utopia town folder.

    Passing ``ROOT`` from data/HoloVerse/main.py resolves to
    data/database/utopia/towns.  Passing the repository ``data`` folder also
    works for tools.
    """
    if holoverse_root is None:
        here = Path(__file__).resolve().parent
        return _data_root_from_holoverse_root(here) / "database" / "utopia" / "towns"
    return _data_root_from_holoverse_root(Path(holoverse_root)) / "database" / "utopia" / "towns"


def utopia_data_dir(holoverse_root: Path | str | None = None) -> Path:
    """Resolve the authored Utopia database folder."""
    if holoverse_root is None:
        here = Path(__file__).resolve().parent
        return _data_root_from_holoverse_root(here) / "database" / "utopia"
    return _data_root_from_holoverse_root(Path(holoverse_root)) / "database" / "utopia"


def city_atlas_path(holoverse_root: Path | str | None = None) -> Path:
    """Return the city-level HoloUtopia atlas path."""
    return utopia_data_dir(holoverse_root) / CITY_ATLAS_NAME


def neighborhood_data_dir(holoverse_root: Path | str | None = None) -> Path:
    """Resolve the authored Utopia neighborhood folder."""
    return utopia_data_dir(holoverse_root) / "neighborhoods"


def neighborhood_path(neighborhood_id: str = DEFAULT_NEIGHBORHOOD_ID, holoverse_root: Path | str | None = None) -> Path:
    """Return the JSON path for a safe-edit HoloUtopia neighborhood."""
    safe_id = str(neighborhood_id or DEFAULT_NEIGHBORHOOD_ID).strip()
    if not safe_id or any(part in safe_id for part in ("/", "\\", "..")):
        raise HoloUtopiaTownError(f"Unsafe neighborhood id: {neighborhood_id!r}")
    return neighborhood_data_dir(holoverse_root) / f"{safe_id}.json"


def load_neighborhood(neighborhood_id: str = DEFAULT_NEIGHBORHOOD_ID, holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load and validate an authored neighborhood buildout."""
    path = neighborhood_path(neighborhood_id, holoverse_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaTownError(f"Neighborhood file missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaTownError(f"Neighborhood JSON error in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaTownError(f"Neighborhood file must contain a JSON object: {path}")
    validate_neighborhood(data, holoverse_root=holoverse_root, source_path=path)
    return data


def list_neighborhood_ids(holoverse_root: Path | str | None = None) -> list[str]:
    """Return authored neighborhood ids, excluding schema/support files."""
    folder = neighborhood_data_dir(holoverse_root)
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if p.name not in {"neighborhood_schema.json"})


def load_all_neighborhoods(holoverse_root: Path | str | None = None) -> list[dict[str, Any]]:
    """Load and validate all authored neighborhood files."""
    return [load_neighborhood(neighborhood_id, holoverse_root=holoverse_root) for neighborhood_id in list_neighborhood_ids(holoverse_root)]

def validate_neighborhood(neighborhood: dict[str, Any], holoverse_root: Path | str | None = None, source_path: Path | None = None) -> None:
    """Validate neighborhood lot/detail files against their town authority."""
    label = str(source_path or neighborhood.get("id") or "<neighborhood>")
    for key in ("id", "town_id", "lots", "micro_schedule_nodes"):
        if key not in neighborhood:
            raise HoloUtopiaTownError(f"{label}: missing required neighborhood key {key!r}")
    town = load_town(str(neighborhood.get("town_id")), holoverse_root=holoverse_root)
    block_ids = {str(block.get("id")) for block in town.get("town_blocks", []) if isinstance(block, dict)}
    town_node_ids = {str(node.get("id")) for node in town.get("schedule_nodes", []) if isinstance(node, dict)}
    slot_ids = {str(slot.get("id")) for slot in town.get("npc_slots", []) if isinstance(slot, dict)}

    lot_ids: set[str] = set()
    addresses: set[str] = set()
    for index, lot in enumerate(neighborhood.get("lots", [])):
        if not isinstance(lot, dict):
            raise HoloUtopiaTownError(f"{label}: lots[{index}] must be an object")
        lot_id = _required_id(lot, f"{label}.lots[{index}]")
        if lot_id in lot_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate lot id {lot_id!r}")
        lot_ids.add(lot_id)
        address = str(lot.get("address", "")).strip()
        if not address:
            raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} missing address")
        if address in addresses:
            raise HoloUtopiaTownError(f"{label}: duplicate address {address!r}")
        addresses.add(address)
        if str(lot.get("block", "")) not in block_ids:
            raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} references missing block {lot.get('block')!r}")
        if str(lot.get("home_node", "")) not in town_node_ids:
            raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} references missing home_node {lot.get('home_node')!r}")
        resident_slot = str(lot.get("resident_slot", "")).strip()
        if resident_slot and resident_slot not in slot_ids:
            raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} references missing resident_slot {resident_slot!r}")
        footprint = lot.get("footprint")
        if not isinstance(footprint, dict):
            raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} missing footprint object")
        footprint_offset = _local_pair(footprint.get("local_offset", [0, 0]), f"{label}.{lot_id}.footprint.local_offset")
        footprint_size = _local_size_pair(footprint.get("size_blocks", [0.5, 0.5]), f"{label}.{lot_id}.footprint.size_blocks")
        if "height_units" in footprint:
            _positive_float(footprint.get("height_units"), f"{label}.{lot_id}.footprint.height_units")
        foundation = lot.get("foundation_profile")
        if foundation is not None:
            if not isinstance(foundation, dict):
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} foundation_profile must be an object")
            for foundation_key in ("foundation_type", "pad_local_offset", "pad_size_blocks", "clearance_margin_blocks", "anchor_rule", "cover_underlay_grid", "visible_ground_pad", "edge_style"):
                if foundation_key not in foundation:
                    raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} foundation_profile missing {foundation_key!r}")
            pad_offset = _local_pair(foundation.get("pad_local_offset", footprint_offset), f"{label}.{lot_id}.foundation_profile.pad_local_offset")
            pad_size = _local_size_pair(foundation.get("pad_size_blocks", footprint_size), f"{label}.{lot_id}.foundation_profile.pad_size_blocks")
            _positive_float(foundation.get("clearance_margin_blocks", 0.01), f"{label}.{lot_id}.foundation_profile.clearance_margin_blocks")
            if pad_size[0] + 1e-6 < footprint_size[0] or pad_size[1] + 1e-6 < footprint_size[1]:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} foundation pad is smaller than the building footprint")
            if abs(pad_offset[0] - footprint_offset[0]) > 0.25 or abs(pad_offset[1] - footprint_offset[1]) > 0.25:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} foundation pad offset is too far from the building footprint")
        profile = lot.get("building_profile")
        if profile is not None:
            if not isinstance(profile, dict):
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} building_profile must be an object")
            for profile_key in ("building_type", "height_class", "floor_count", "residential_capacity", "current_reserved_capacity", "roof_type", "style_variant", "height_units"):
                if profile_key not in profile:
                    raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} building_profile missing {profile_key!r}")
            if str(profile.get("height_class")) not in {"low", "mid", "tall"}:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} invalid height_class {profile.get('height_class')!r}")
            try:
                floor_count = int(profile.get("floor_count"))
                capacity = int(profile.get("residential_capacity"))
                reserved = int(profile.get("current_reserved_capacity"))
            except Exception as exc:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} building_profile floor/capacity fields must be integers") from exc
            if floor_count < 1 or floor_count > 24:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} floor_count must be 1..24")
            if capacity < 1 or capacity > 500:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} residential_capacity must be 1..500")
            if reserved < 0 or reserved > capacity:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} current_reserved_capacity must be 0..capacity")
            _positive_float(profile.get("height_units"), f"{label}.{lot_id}.building_profile.height_units")
            if str(profile.get("building_type", "")).strip() == "" or str(profile.get("roof_type", "")).strip() == "":
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} building_type and roof_type must be non-empty")
        anchors = lot.get("anchors")
        if not isinstance(anchors, dict) or "front_door" not in anchors:
            raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} must define anchors.front_door")
        for anchor_name, anchor in anchors.items():
            if not isinstance(anchor, dict):
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} anchor {anchor_name!r} must be an object")
            _required_id(anchor, f"{label}.{lot_id}.anchors.{anchor_name}")
            _local_pair(anchor.get("local_offset", [0, 0]), f"{label}.{lot_id}.anchors.{anchor_name}.local_offset")
        for room in lot.get("rooms", []):
            if not isinstance(room, dict):
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} room entries must be objects")
            _required_id(room, f"{label}.{lot_id}.room")
            _local_pair(room.get("local_offset", [0, 0]), f"{label}.{lot_id}.room.local_offset")
        for floor_anchor in lot.get("floor_anchors", []):
            if not isinstance(floor_anchor, dict):
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} floor_anchors entries must be objects")
            _required_id(floor_anchor, f"{label}.{lot_id}.floor_anchor")
            try:
                floor_index = int(floor_anchor.get("floor"))
            except Exception as exc:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} floor anchor must define integer floor") from exc
            if floor_index < 0 or floor_index > 24:
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} floor anchor floor must be 0..24")
        vertical_anchors = lot.get("vertical_anchors", {})
        if vertical_anchors and not isinstance(vertical_anchors, dict):
            raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} vertical_anchors must be an object")
        for anchor_name, anchor in (vertical_anchors.items() if isinstance(vertical_anchors, dict) else []):
            if not isinstance(anchor, dict):
                raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} vertical anchor {anchor_name!r} must be an object")
            _required_id(anchor, f"{label}.{lot_id}.vertical_anchors.{anchor_name}")

    micro_ids: set[str] = set()
    for index, node in enumerate(neighborhood.get("micro_schedule_nodes", [])):
        if not isinstance(node, dict):
            raise HoloUtopiaTownError(f"{label}: micro_schedule_nodes[{index}] must be an object")
        node_id = _required_id(node, f"{label}.micro_schedule_nodes[{index}]")
        if node_id in micro_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate micro node id {node_id!r}")
        micro_ids.add(node_id)
        if str(node.get("block", "")) not in block_ids:
            raise HoloUtopiaTownError(f"{label}: micro node {node_id!r} references missing block {node.get('block')!r}")
        town_node = str(node.get("town_node", "")).strip()
        if town_node and town_node not in town_node_ids:
            raise HoloUtopiaTownError(f"{label}: micro node {node_id!r} references missing town_node {town_node!r}")
        lot_ref = str(node.get("lot", "")).strip()
        if lot_ref and lot_ref not in lot_ids:
            raise HoloUtopiaTownError(f"{label}: micro node {node_id!r} references missing lot {lot_ref!r}")
        _local_pair(node.get("local_offset", [0, 0]), f"{label}.{node_id}.local_offset")

    legal_route_nodes = micro_ids | town_node_ids
    for route in neighborhood.get("neighborhood_routes", []):
        if not isinstance(route, dict):
            raise HoloUtopiaTownError(f"{label}: route entries must be objects")
        route_id = _required_id(route, f"{label}.route")
        for node_id in route.get("nodes", []):
            if str(node_id) not in legal_route_nodes:
                raise HoloUtopiaTownError(f"{label}: route {route_id!r} references missing node {node_id!r}")


def load_city_atlas(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load the HoloUtopia city atlas that places even town frames."""
    path = city_atlas_path(holoverse_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaTownError(f"City atlas missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaTownError(f"City atlas JSON error in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaTownError(f"City atlas must contain a JSON object: {path}")
    return data


def load_town(town_id: str = DEFAULT_TOWN_ID, holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load a town JSON definition by id."""
    safe_id = str(town_id or DEFAULT_TOWN_ID).strip()
    if not safe_id or any(part in safe_id for part in ("/", "\\", "..")):
        raise HoloUtopiaTownError(f"Unsafe town id: {town_id!r}")
    path = town_data_dir(holoverse_root) / f"{safe_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaTownError(f"Town file missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaTownError(f"Town JSON error in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaTownError(f"Town file must contain a JSON object: {path}")
    validate_town(data, source_path=path)
    return data



def list_town_ids(holoverse_root: Path | str | None = None) -> list[str]:
    """Return authored town ids, excluding schema/support files."""
    folder = town_data_dir(holoverse_root)
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if p.name != "town_schema.json")


def validate_town(town: dict[str, Any], source_path: Path | None = None) -> None:
    """Validate the stable, hand-editable parts of a town definition."""
    label = str(source_path or town.get("id") or "<town>")
    required = ["id", "display_name", "district_type", "grid_size", "block_size", "roads", "town_blocks", "schedule_nodes"]
    missing = [key for key in required if key not in town]
    if missing:
        raise HoloUtopiaTownError(f"{label}: missing required town keys: {missing}")

    grid_size = _grid_pair(town["grid_size"], f"{label}.grid_size", minimum=1)
    block_size = _positive_float(town["block_size"], f"{label}.block_size")
    if block_size < 8:
        raise HoloUtopiaTownError(f"{label}: block_size is too small for stable routing: {block_size}")

    district_frame = town.get("district_frame")
    if not isinstance(district_frame, dict):
        raise HoloUtopiaTownError(f"{label}: missing district_frame for even city-grid placement")
    frame_grid = _grid_pair(district_frame.get("canonical_grid_size"), f"{label}.district_frame.canonical_grid_size", minimum=1)
    if frame_grid != grid_size:
        raise HoloUtopiaTownError(f"{label}: district_frame canonical grid {frame_grid!r} must match grid_size {grid_size!r}")
    _grid_pair(district_frame.get("applied_grid_offset", [0, 0]), f"{label}.district_frame.applied_grid_offset", minimum=0)

    portal_hub = town.get("portal_hub")
    district_anchor = town.get("district_anchor")
    if portal_hub is None and district_anchor is None:
        raise HoloUtopiaTownError(f"{label}: town must define portal_hub or district_anchor")
    if portal_hub is not None:
        if not isinstance(portal_hub, dict):
            raise HoloUtopiaTownError(f"{label}: portal_hub must be an object")
        _grid_pair(portal_hub.get("grid"), f"{label}.portal_hub.grid", grid_size=grid_size)
        portals = portal_hub.get("portals")
        if not isinstance(portals, list) or len(portals) < 1:
            raise HoloUtopiaTownError(f"{label}: portal_hub.portals must be a non-empty list")
        _assert_unique([str(p.get("id", "")) for p in portals if isinstance(p, dict)], f"{label}.portal_hub.portals")
    if district_anchor is not None:
        if not isinstance(district_anchor, dict):
            raise HoloUtopiaTownError(f"{label}: district_anchor must be an object")
        _required_id(district_anchor, f"{label}.district_anchor")
        _grid_pair(district_anchor.get("grid"), f"{label}.district_anchor.grid", grid_size=grid_size)
        if "radius" in district_anchor:
            _positive_float(district_anchor.get("radius"), f"{label}.district_anchor.radius")

    roads = town.get("roads")
    if not isinstance(roads, list):
        raise HoloUtopiaTownError(f"{label}: roads must be a list")
    road_ids: set[str] = set()
    for index, road in enumerate(roads):
        if not isinstance(road, dict):
            raise HoloUtopiaTownError(f"{label}: roads[{index}] must be an object")
        road_id = _required_id(road, f"{label}.roads[{index}]")
        if road_id in road_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate road id {road_id!r}")
        road_ids.add(road_id)
        kind = str(road.get("kind", "")).strip()
        if kind == "radial":
            _grid_pair(road.get("from"), f"{label}.{road_id}.from", grid_size=grid_size)
            _grid_pair(road.get("to"), f"{label}.{road_id}.to", grid_size=grid_size)
        elif kind == "ring":
            _grid_pair(road.get("center"), f"{label}.{road_id}.center", grid_size=grid_size)
            _positive_float(road.get("radius_blocks"), f"{label}.{road_id}.radius_blocks")
        else:
            raise HoloUtopiaTownError(f"{label}: road {road_id!r} has unknown kind {kind!r}")

    blocks = town.get("town_blocks")
    if not isinstance(blocks, list):
        raise HoloUtopiaTownError(f"{label}: town_blocks must be a list")
    block_ids: set[str] = set()
    occupied: set[tuple[int, int]] = set()
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise HoloUtopiaTownError(f"{label}: town_blocks[{index}] must be an object")
        block_id = _required_id(block, f"{label}.town_blocks[{index}]")
        if block_id in block_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate block id {block_id!r}")
        block_ids.add(block_id)
        gx, gy = _grid_pair(block.get("grid"), f"{label}.{block_id}.grid", grid_size=grid_size)
        sx, sy = _grid_pair(block.get("size"), f"{label}.{block_id}.size", minimum=1)
        if gx + sx > grid_size[0] or gy + sy > grid_size[1]:
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} exceeds grid bounds")
        if not isinstance(block.get("connectors"), list):
            raise HoloUtopiaTownError(f"{label}: block {block_id!r} connectors must be a list")
        for connector in block.get("connectors", []):
            if str(connector) not in road_ids:
                raise HoloUtopiaTownError(f"{label}: block {block_id!r} references missing road {connector!r}")
        for px in range(gx, gx + sx):
            for py in range(gy, gy + sy):
                if (px, py) in occupied:
                    raise HoloUtopiaTownError(f"{label}: duplicate block occupancy at grid {(px, py)}")
                occupied.add((px, py))

    nodes = town.get("schedule_nodes")
    if not isinstance(nodes, list):
        raise HoloUtopiaTownError(f"{label}: schedule_nodes must be a list")
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise HoloUtopiaTownError(f"{label}: schedule_nodes[{index}] must be an object")
        node_id = _required_id(node, f"{label}.schedule_nodes[{index}]")
        if node_id in node_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate schedule node id {node_id!r}")
        node_ids.add(node_id)
        if "grid" in node:
            _grid_pair(node.get("grid"), f"{label}.{node_id}.grid", grid_size=grid_size)
        if "block" in node and str(node.get("block")) not in block_ids:
            raise HoloUtopiaTownError(f"{label}: node {node_id!r} references missing block {node.get('block')!r}")

    for loop in town.get("patrol_loops", []):
        if not isinstance(loop, dict):
            raise HoloUtopiaTownError(f"{label}: patrol loop entries must be objects")
        loop_id = _required_id(loop, f"{label}.patrol_loop")
        for node_id in loop.get("nodes", []):
            if str(node_id) not in node_ids:
                raise HoloUtopiaTownError(f"{label}: patrol loop {loop_id!r} references missing node {node_id!r}")

    validate_structure_variant_profile(town, source_path=source_path)
    validate_structure_massing_profile(town, source_path=source_path)

    for slot in town.get("npc_slots", []):
        if not isinstance(slot, dict):
            raise HoloUtopiaTownError(f"{label}: npc_slot entries must be objects")
        slot_id = _required_id(slot, f"{label}.npc_slot")
        for ref_key in ("home_node", "work_node"):
            if str(slot.get(ref_key, "")) not in node_ids:
                raise HoloUtopiaTownError(f"{label}: npc slot {slot_id!r} references missing {ref_key} {slot.get(ref_key)!r}")


def town_bounds(town: dict[str, Any]) -> TownBounds:
    width, height = _grid_pair(town["grid_size"], "grid_size", minimum=1)
    block_size = _positive_float(town["block_size"], "block_size")
    half_w = width * block_size * 0.5
    half_h = height * block_size * 0.5
    return TownBounds(-half_w, -half_h, half_w, half_h)


def grid_to_world(town: dict[str, Any], grid: Iterable[float | int]) -> TownPoint:
    """Convert a grid coordinate to centered world X/Y coordinates."""
    gx, gy = _pair_float(grid, "grid")
    width, height = _grid_pair(town["grid_size"], "grid_size", minimum=1)
    block_size = _positive_float(town["block_size"], "block_size")
    x = (gx - (width - 1) * 0.5) * block_size
    y = ((height - 1) * 0.5 - gy) * block_size
    return TownPoint(x, y)


def attach_holoutopia_town(parent: Any, holoverse_root: Path | str | None = None, town_id: str = DEFAULT_TOWN_ID, *, z: float = 0.06, show_roads: bool = True, show_anchor: bool = True, show_structure_massing: bool = True) -> Any:
    """Attach a simple neon town-block visualization to a Panda3D parent.

    ``parent`` should be a NodePath such as ``render`` or an existing world root.
    Panda3D is imported inside this function so file validators can run without
    Panda3D installed.
    """
    town = load_town(town_id, holoverse_root=holoverse_root)
    from panda3d.core import CardMaker, LineSegs, TextNode, TransparencyAttrib, Vec3, Vec4

    root = parent.attachNewNode(f"holoutopia_{town['id']}")
    root.setLightOff(True)
    root.setTransparency(TransparencyAttrib.M_alpha)
    root.setPythonTag("holoutopia_town_root", True)
    root.setPythonTag("holoutopia_town_id", str(town.get("id") or town_id))
    root.setPythonTag("holoutopia_town_display_name", str(town.get("display_name") or town.get("id") or town_id))
    root.setPythonTag("holoutopia_district_type", str(town.get("district_type") or ""))

    palette = _palette(town)
    block_size = float(town["block_size"])

    def draw_polyline(name: str, points: list[TownPoint], color: tuple[float, float, float, float], thickness: float = 2.0, closed: bool = False, z_value: float | None = None) -> Any:
        lines = LineSegs(name)
        lines.setThickness(thickness)
        lines.setColor(*color)
        if not points:
            return root.attachNewNode(lines.create())
        line_z = z if z_value is None else float(z_value)
        first = points[0]
        lines.moveTo(first.x, first.y, line_z)
        for p in points[1:]:
            lines.drawTo(p.x, p.y, line_z)
        if closed:
            lines.drawTo(first.x, first.y, line_z)
        node = root.attachNewNode(lines.create())
        node.setLightOff(True)
        return node

    # Base grid, intentionally subtle so town blocks remain readable.
    bounds = town_bounds(town)
    grid_color = palette["grid"]
    for gx in range(int(town["grid_size"][0]) + 1):
        x = bounds.min_x + gx * block_size
        draw_polyline(f"grid_x_{gx}", [TownPoint(x, bounds.min_y), TownPoint(x, bounds.max_y)], grid_color, 1.0)
    for gy in range(int(town["grid_size"][1]) + 1):
        y = bounds.min_y + gy * block_size
        draw_polyline(f"grid_y_{gy}", [TownPoint(bounds.min_x, y), TownPoint(bounds.max_x, y)], grid_color, 1.0)

    # Roads first, then blocks on top. Neighborhood overlays may hide decorative
    # town roads/anchors so background guide lines do not cut through buildings.
    if show_roads:
        for road in town.get("roads", []):
            kind = str(road.get("kind"))
            if kind == "radial":
                draw_polyline(str(road["id"]), [grid_to_world(town, road["from"]), grid_to_world(town, road["to"])], palette["road"], max(2.0, float(road.get("width", 8)) * 0.2))
            elif kind == "ring":
                center = grid_to_world(town, road["center"])
                radius = float(road["radius_blocks"]) * block_size
                pts = [TownPoint(center.x + math.cos(i / 96.0 * math.tau) * radius, center.y + math.sin(i / 96.0 * math.tau) * radius) for i in range(96)]
                draw_polyline(str(road["id"]), pts, palette["road"], max(2.0, float(road.get("width", 8)) * 0.16), closed=True)

    for block in town.get("town_blocks", []):
        _attach_block(root, town, block, palette, z + 0.025, CardMaker, Vec3, Vec4, TransparencyAttrib, draw_polyline, show_structure_massing=show_structure_massing)

    hub = town.get("portal_hub")
    anchor = town.get("district_anchor") if isinstance(town.get("district_anchor"), dict) else None
    if show_anchor and isinstance(hub, dict):
        center = grid_to_world(town, hub.get("grid", [0, 0]))
        radius = float(hub.get("radius", block_size * 0.8))
        oct_pts = [TownPoint(center.x + math.cos(math.radians(22.5 + i * 45)) * radius, center.y + math.sin(math.radians(22.5 + i * 45)) * radius) for i in range(8)]
        draw_polyline("portal_hub_octagon", oct_pts, palette["portal"], 3.2, closed=True)
        for portal in hub.get("portals", []):
            angle = math.radians(float(portal.get("angle_degrees", 0)))
            p = TownPoint(center.x + math.cos(angle) * (radius + 8.0), center.y + math.sin(angle) * (radius + 8.0))
            draw_polyline(f"portal_marker_{portal.get('id', 'unknown')}", [TownPoint(p.x - 4, p.y - 4), TownPoint(p.x + 4, p.y + 4), TownPoint(p.x + 4, p.y - 4), TownPoint(p.x - 4, p.y + 4)], palette["portal"], 2.0)
    elif show_anchor and anchor is not None:
        center = grid_to_world(town, anchor.get("grid", [0, 0]))
        radius = float(anchor.get("radius", block_size * 0.55))
        diamond_pts = [
            TownPoint(center.x, center.y + radius),
            TownPoint(center.x + radius, center.y),
            TownPoint(center.x, center.y - radius),
            TownPoint(center.x - radius, center.y),
        ]
        draw_polyline(f"district_anchor_{anchor.get('id', 'anchor')}", diamond_pts, palette["anchor"], 3.0, closed=True)
    else:
        center = TownPoint(0.0, 0.0)
        radius = block_size

    label = TextNode("holoutopia_label")
    label.setText(str(town.get("display_name") or town.get("id") or "HoloUtopia Town"))
    label.setAlign(TextNode.ACenter)
    label.setTextColor(*palette["label"])
    label_node = root.attachNewNode(label)
    label_node.setScale(8.0)
    label_node.setPos(center.x, center.y - radius - 30.0, z + 4.0)
    label_node.setHpr(0, -70, 0)
    label_node.setLightOff(True)
    return root


def city_frame_metrics(atlas: dict[str, Any]) -> dict[str, float]:
    """Return frame spacing metrics for placing even HoloUtopia districts."""
    grid_size = _grid_pair(atlas.get("canonical_grid_size", [10, 8]), "city_atlas.canonical_grid_size", minimum=1)
    block_size = _positive_float(atlas.get("block_size", 64), "city_atlas.block_size")
    gap_blocks = float(atlas.get("district_gap_blocks", 2))
    return {
        "grid_w": float(grid_size[0]),
        "grid_h": float(grid_size[1]),
        "block_size": block_size,
        "gap_blocks": gap_blocks,
        "frame_w": (float(grid_size[0]) + gap_blocks) * block_size,
        "frame_h": (float(grid_size[1]) + gap_blocks) * block_size,
    }


def city_atlas_bounds(atlas: dict[str, Any]) -> TownBounds:
    """Return approximate world bounds for the whole city atlas."""
    metrics = city_frame_metrics(atlas)
    xs: list[float] = []
    ys: list[float] = []
    for entry in atlas.get("towns", []):
        if not isinstance(entry, dict):
            continue
        gx, gy = _grid_pair(entry.get("city_grid"), f"city_atlas.{entry.get('town_id', 'town')}.city_grid")
        cx = gx * metrics["frame_w"]
        cy = gy * metrics["frame_h"]
        xs.extend([cx - metrics["frame_w"] * 0.5, cx + metrics["frame_w"] * 0.5])
        ys.extend([cy - metrics["frame_h"] * 0.5, cy + metrics["frame_h"] * 0.5])
    if not xs or not ys:
        return TownBounds(-1.0, -1.0, 1.0, 1.0)
    return TownBounds(min(xs), min(ys), max(xs), max(ys))


def attach_holoutopia_city(parent: Any, holoverse_root: Path | str | None = None, *, z: float = 0.06) -> Any:
    """Attach every town in the city atlas as an evenly spaced district frame."""
    atlas = load_city_atlas(holoverse_root)
    metrics = city_frame_metrics(atlas)
    city_root = parent.attachNewNode(f"holoutopia_city_{atlas.get('id', DEFAULT_CITY_ATLAS_ID)}")
    for entry in atlas.get("towns", []):
        if not isinstance(entry, dict):
            continue
        town_id = str(entry.get("town_id", "")).strip()
        if not town_id:
            continue
        gx, gy = _grid_pair(entry.get("city_grid"), f"city_atlas.{town_id}.city_grid")
        town_root = attach_holoutopia_town(city_root, holoverse_root=holoverse_root, town_id=town_id, z=z, show_structure_massing=True)
        town_root.setPos(gx * metrics["frame_w"], gy * metrics["frame_h"], 0.0)
        town_root.setPythonTag("holoutopia_city_town_root", True)
        town_root.setPythonTag("holoutopia_city_grid", (int(gx), int(gy)))
        town_root.setPythonTag("holoutopia_city_frame_size", (float(metrics["frame_w"]), float(metrics["frame_h"])))
    return city_root

def attach_holoutopia_city_neighborhoods(parent: Any, holoverse_root: Path | str | None = None, *, z: float = 0.10, neighborhood_ids: list[str] | None = None) -> Any:
    """Attach authored neighborhood overlays at their city-atlas district positions.

    This is intended for previews and later runtime integration.  It preserves
    the same safe-edit neighborhood renderer while placing each neighborhood in
    the even city frame.  If multiple neighborhoods target one town, each is
    still isolated as a removable child so highlight/lazy-interior work can stay
    scoped.
    """
    atlas = load_city_atlas(holoverse_root)
    metrics = city_frame_metrics(atlas)
    town_grid: dict[str, tuple[int, int]] = {}
    for entry in atlas.get("towns", []):
        if isinstance(entry, dict) and str(entry.get("town_id", "")).strip():
            town_grid[str(entry.get("town_id"))] = _grid_pair(entry.get("city_grid"), f"city_atlas.{entry.get('town_id')}.city_grid")
    ids = list(neighborhood_ids) if neighborhood_ids is not None else list_neighborhood_ids(holoverse_root)
    root = parent.attachNewNode("holoutopia_city_neighborhoods")
    for neighborhood_id in ids:
        neighborhood = load_neighborhood(neighborhood_id, holoverse_root=holoverse_root)
        town_id = str(neighborhood.get("town_id") or "")
        if town_id not in town_grid:
            continue
        gx, gy = town_grid[town_id]
        node = attach_holoutopia_neighborhood(root, holoverse_root=holoverse_root, neighborhood_id=neighborhood_id, z=z)
        node.setPos(gx * metrics["frame_w"], gy * metrics["frame_h"], 0.0)
        node.setPythonTag("holoutopia_neighborhood_city_root", True)
        node.setPythonTag("holoutopia_town_id", town_id)
        node.setPythonTag("holoutopia_city_grid", (int(gx), int(gy)))
    return root


def block_center_point(town: dict[str, Any], block: dict[str, Any]) -> TownPoint:
    """Return the centered world point for a town block."""
    gx, gy = block.get("grid", [0, 0])
    sx, sy = block.get("size", [1, 1])
    return grid_to_world(town, [float(gx) + (float(sx) - 1.0) * 0.5, float(gy) + (float(sy) - 1.0) * 0.5])


def neighborhood_local_point(town: dict[str, Any], block: dict[str, Any], local_offset: Iterable[float | int]) -> TownPoint:
    """Convert a neighborhood-local offset inside a block to town world coordinates."""
    ox, oy = _pair_float(local_offset, "local_offset")
    center = block_center_point(town, block)
    block_size = _positive_float(town["block_size"], "block_size")
    return TownPoint(center.x + ox * block_size, center.y + oy * block_size)


def attach_holoutopia_neighborhood(parent: Any, holoverse_root: Path | str | None = None, neighborhood_id: str = DEFAULT_NEIGHBORHOOD_ID, *, z: float = 0.12) -> Any:
    """Attach one detailed neighborhood over its town frame."""
    neighborhood = load_neighborhood(neighborhood_id, holoverse_root=holoverse_root)
    town_id = str(neighborhood.get("town_id") or DEFAULT_TOWN_ID)
    town = load_town(town_id, holoverse_root=holoverse_root)
    from panda3d.core import CardMaker, LineSegs, TextNode, TransparencyAttrib, Vec4

    root = attach_holoutopia_town(parent, holoverse_root=holoverse_root, town_id=town_id, z=z, show_roads=False, show_anchor=False, show_structure_massing=False)
    overlay = root.attachNewNode(f"holoutopia_neighborhood_{neighborhood.get('id', neighborhood_id)}")
    overlay.setLightOff(True)
    overlay.setTransparency(TransparencyAttrib.M_alpha)
    block_by_id = {str(block.get("id")): block for block in town.get("town_blocks", []) if isinstance(block, dict)}

    def draw_polyline(name: str, points: list[TownPoint], color: tuple[float, float, float, float], thickness: float = 2.0, closed: bool = False, z_value: float | None = None) -> Any:
        lines = LineSegs(name)
        lines.setThickness(thickness)
        lines.setColor(*color)
        if not points:
            return overlay.attachNewNode(lines.create())
        line_z = z + 0.16 if z_value is None else float(z_value)
        first = points[0]
        lines.moveTo(first.x, first.y, line_z)
        for p in points[1:]:
            lines.drawTo(p.x, p.y, line_z)
        if closed:
            lines.drawTo(first.x, first.y, line_z)
        node = overlay.attachNewNode(lines.create())
        node.setLightOff(True)
        return node

    def _height_color(height_class: str) -> tuple[float, float, float, float]:
        if height_class == "tall":
            return (0.85, 0.38, 1.0, 0.96)
        if height_class == "mid":
            return (0.22, 0.95, 1.0, 0.94)
        return (0.94, 1.0, 0.82, 0.92)

    def _rect_corners(center: TownPoint, half_w: float, half_h: float) -> list[TownPoint]:
        return [
            TownPoint(center.x - half_w, center.y - half_h),
            TownPoint(center.x + half_w, center.y - half_h),
            TownPoint(center.x + half_w, center.y + half_h),
            TownPoint(center.x - half_w, center.y + half_h),
        ]

    def draw_foundation_pad(lot_id: str, center: TownPoint, half_w: float, half_h: float, foundation: dict[str, Any]) -> tuple[float, float, float, float]:
        pad_z = z + 0.135
        slab_color = (0.015, 0.070, 0.085, 0.96) if bool(foundation.get("cover_underlay_grid", True)) else (0.015, 0.070, 0.085, 0.55)
        if bool(foundation.get("visible_ground_pad", True)):
            cm = CardMaker(f"{lot_id}_foundation_slab")
            cm.setFrame(-half_w, half_w, -half_h, half_h)
            card = overlay.attachNewNode(cm.generate())
            card.setPos(center.x, center.y, pad_z)
            card.setHpr(0, -90, 0)
            card.setColor(Vec4(*slab_color))
            card.setTransparency(TransparencyAttrib.M_alpha)
            card.setLightOff(True)
        corners = _rect_corners(center, half_w, half_h)
        edge_color = (0.36, 1.0, 0.92, 0.92)
        draw_polyline(f"{lot_id}_foundation_edge", corners, edge_color, 2.8, closed=True, z_value=pad_z + 0.055)
        # Small corner ticks communicate footing without drawing lines through the building volume.
        tick = min(half_w, half_h) * 0.18
        for i, corner in enumerate(corners):
            sx = 1.0 if corner.x < center.x else -1.0
            sy = 1.0 if corner.y < center.y else -1.0
            draw_polyline(f"{lot_id}_foundation_tick_{i}_x", [corner, TownPoint(corner.x + sx * tick, corner.y)], edge_color, 1.4, z_value=pad_z + 0.08)
            draw_polyline(f"{lot_id}_foundation_tick_{i}_y", [corner, TownPoint(corner.x, corner.y + sy * tick)], edge_color, 1.4, z_value=pad_z + 0.08)
        return (center.x - half_w, center.y - half_h, center.x + half_w, center.y + half_h)

    def draw_building_wireframe(lot_id: str, corners: list[TownPoint], profile: dict[str, Any]) -> None:
        height_class = str(profile.get("height_class", "low"))
        color = _height_color(height_class)
        floor_count = max(1, int(profile.get("floor_count", 1)))
        height = float(profile.get("height_units", max(18.0, floor_count * 16.0)))
        base_z = z + 0.32
        top_z = base_z + height
        draw_polyline(f"{lot_id}_building_base_on_foundation", corners, color, 2.2, closed=True, z_value=base_z)
        draw_polyline(f"{lot_id}_building_roof_perimeter", corners, color, 2.6, closed=True, z_value=top_z)
        for i, corner in enumerate(corners):
            lines = LineSegs(f"{lot_id}_building_vertical_edge_{i}")
            lines.setThickness(2.0)
            lines.setColor(*color)
            lines.moveTo(corner.x, corner.y, base_z)
            lines.drawTo(corner.x, corner.y, top_z)
            node = overlay.attachNewNode(lines.create())
            node.setLightOff(True)
        # Floor bands are only perimeter loops; no arbitrary diagonal lines cross roofs or walls.
        for floor in range(1, floor_count):
            fz = base_z + height * (floor / floor_count)
            draw_polyline(f"{lot_id}_floor_perimeter_band_{floor}", corners, (color[0], color[1], color[2], 0.52), 1.1, closed=True, z_value=fz)
        roof_type = str(profile.get("roof_type", ""))
        if "garden" in roof_type:
            inset = 0.20
            cx = sum(p.x for p in corners) * 0.25
            cy = sum(p.y for p in corners) * 0.25
            inner = [TownPoint(cx + (p.x - cx) * (1.0 - inset), cy + (p.y - cy) * (1.0 - inset)) for p in corners]
            draw_polyline(f"{lot_id}_roof_garden_perimeter", inner, (0.55, 1.0, 0.60, 0.66), 1.0, closed=True, z_value=top_z + 0.35)
        elif "signal" in roof_type:
            cx = sum(p.x for p in corners) * 0.25
            cy = sum(p.y for p in corners) * 0.25
            lines = LineSegs(f"{lot_id}_roof_signal_mast")
            lines.setThickness(1.6)
            lines.setColor(1.0, 0.84, 0.35, 0.70)
            lines.moveTo(cx, cy, top_z + 0.2)
            lines.drawTo(cx, cy, top_z + 8.0)
            node = overlay.attachNewNode(lines.create())
            node.setLightOff(True)

    lot_color = (0.94, 1.0, 0.82, 0.92)
    door_color = (1.0, 0.42, 0.25, 0.95)
    node_color = (0.25, 1.0, 0.78, 0.90)
    building_exclusion_boxes: list[tuple[float, float, float, float]] = []
    for lot in neighborhood.get("lots", []):
        if not isinstance(lot, dict):
            continue
        block = block_by_id.get(str(lot.get("block")))
        if block is None:
            continue
        footprint = lot.get("footprint", {}) if isinstance(lot.get("footprint"), dict) else {}
        foundation = lot.get("foundation_profile", {}) if isinstance(lot.get("foundation_profile"), dict) else {}
        center = neighborhood_local_point(town, block, footprint.get("local_offset", [0, 0]))
        sx, sy = _local_size_pair(footprint.get("size_blocks", [0.55, 0.55]), "footprint.size_blocks")
        block_size = float(town["block_size"])
        half_w = sx * block_size * 0.5
        half_h = sy * block_size * 0.5
        pad_center = neighborhood_local_point(town, block, foundation.get("pad_local_offset", footprint.get("local_offset", [0, 0]))) if foundation else center
        pad_sx, pad_sy = _local_size_pair(foundation.get("pad_size_blocks", [sx + 0.12, sy + 0.12]), "foundation.pad_size_blocks") if foundation else (sx + 0.12, sy + 0.12)
        foundation_box = draw_foundation_pad(str(lot.get('id', 'lot')), pad_center, pad_sx * block_size * 0.5, pad_sy * block_size * 0.5, foundation)
        building_exclusion_boxes.append(foundation_box)
        corners = _rect_corners(center, half_w, half_h)
        profile = lot.get("building_profile", {}) if isinstance(lot.get("building_profile"), dict) else {}
        if profile:
            draw_building_wireframe(str(lot.get('id', 'lot')), corners, profile)
        else:
            draw_polyline(f"{lot.get('id', 'lot')}_footprint", corners, lot_color, 2.4, closed=True)
        anchors = lot.get("anchors", {}) if isinstance(lot.get("anchors"), dict) else {}
        door = anchors.get("front_door") if isinstance(anchors.get("front_door"), dict) else None
        if door:
            point = neighborhood_local_point(town, block, door.get("local_offset", [0, 0]))
            # Door is drawn as a short threshold on the foundation edge, not as an X through the wall.
            draw_polyline(f"{lot.get('id', 'lot')}_door_threshold", [TownPoint(point.x - 5, point.y), TownPoint(point.x + 5, point.y)], door_color, 2.4)

    def _inside_foundation_box(point: TownPoint) -> bool:
        for min_x, min_y, max_x, max_y in building_exclusion_boxes:
            if min_x <= point.x <= max_x and min_y <= point.y <= max_y:
                return True
        return False

    for node in neighborhood.get("micro_schedule_nodes", []):
        if not isinstance(node, dict):
            continue
        block = block_by_id.get(str(node.get("block")))
        if block is None:
            continue
        if str(node.get("kind", "")) in {"front_door", "door"}:
            continue
        point = neighborhood_local_point(town, block, node.get("local_offset", [0, 0]))
        kind = str(node.get("kind", ""))
        if _inside_foundation_box(point) and kind not in {"porch", "mailbox"}:
            # Interior/ambiguous markers are rendered only by the highlight-only interior overlay.
            continue
        if kind == "mailbox":
            draw_polyline(str(node.get("id", "micro_node")), [TownPoint(point.x - 2.5, point.y - 2.5), TownPoint(point.x + 2.5, point.y - 2.5), TownPoint(point.x + 2.5, point.y + 2.5), TownPoint(point.x - 2.5, point.y + 2.5)], node_color, 1.4, closed=True)
        else:
            draw_polyline(str(node.get("id", "micro_node")), [TownPoint(point.x - 3, point.y), TownPoint(point.x + 3, point.y)], node_color, 1.5)

    label = TextNode("holoutopia_neighborhood_label")
    label.setText(str(neighborhood.get("display_name") or neighborhood.get("id") or "HoloUtopia Neighborhood"))
    label.setAlign(TextNode.ACenter)
    label.setTextColor(0.96, 1.0, 0.90, 0.94)
    label_node = overlay.attachNewNode(label)
    bounds = town_bounds(town)
    label_node.setScale(6.5)
    label_node.setPos((bounds.min_x + bounds.max_x) * 0.5, bounds.min_y - 62.0, z + 5.0)
    label_node.setHpr(0, -70, 0)
    label_node.setLightOff(True)
    return root


INTERIOR_DATA_RELATIVE = Path("../database/utopia/interiors")
NPC_DATA_RELATIVE = Path("../database/utopia/npcs")


def interior_data_dir(holoverse_root: Path | str | None = None) -> Path:
    """Resolve the authored Utopia interior blueprint folder."""
    return utopia_data_dir(holoverse_root) / "interiors"


def npc_data_dir(holoverse_root: Path | str | None = None) -> Path:
    """Resolve the authored Utopia NPC database folder."""
    return utopia_data_dir(holoverse_root) / "npcs"


def interior_path(interior_id: str, holoverse_root: Path | str | None = None) -> Path:
    """Return the JSON path for one lazy-load interior blueprint."""
    safe_id = str(interior_id or "").strip()
    if not safe_id or any(part in safe_id for part in ("/", "\\", "..")):
        raise HoloUtopiaTownError(f"Unsafe interior id: {interior_id!r}")
    return interior_data_dir(holoverse_root) / f"{safe_id}.json"


def load_interior_blueprint(interior_id: str, holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load and validate one highlight-only building interior blueprint."""
    path = interior_path(interior_id, holoverse_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaTownError(f"Interior blueprint missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaTownError(f"Interior blueprint JSON error in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaTownError(f"Interior blueprint must contain a JSON object: {path}")
    validate_interior_blueprint(data, holoverse_root=holoverse_root, source_path=path)
    return data


def validate_interior_blueprint(interior: dict[str, Any], holoverse_root: Path | str | None = None, source_path: Path | None = None) -> None:
    """Validate a lazy-load interior against neighborhood lot data."""
    label = str(source_path or interior.get("id") or "<interior>")
    for key in ("id", "town_id", "neighborhood_id", "lot_id", "load_policy", "floors", "activity_nodes", "resident_unit_slots"):
        if key not in interior:
            raise HoloUtopiaTownError(f"{label}: missing required interior key {key!r}")
    neighborhood = load_neighborhood(str(interior.get("neighborhood_id")), holoverse_root=holoverse_root)
    lot_id = str(interior.get("lot_id"))
    lots = {str(lot.get("id")): lot for lot in neighborhood.get("lots", []) if isinstance(lot, dict)}
    if lot_id not in lots:
        raise HoloUtopiaTownError(f"{label}: references missing lot_id {lot_id!r}")
    lot = lots[lot_id]
    if str(lot.get("interior_blueprint_id", "")).strip() and str(lot.get("interior_blueprint_id")) != str(interior.get("id")):
        raise HoloUtopiaTownError(f"{label}: lot {lot_id!r} points to {lot.get('interior_blueprint_id')!r}, not {interior.get('id')!r}")
    policy = interior.get("load_policy")
    if not isinstance(policy, dict) or policy.get("mode") != "highlight_only":
        raise HoloUtopiaTownError(f"{label}: load_policy.mode must be 'highlight_only'")
    profile = lot.get("building_profile", {}) if isinstance(lot.get("building_profile"), dict) else {}
    try:
        lot_floors = int(profile.get("floor_count", 0))
        lot_capacity = int(profile.get("residential_capacity", 0))
    except Exception as exc:
        raise HoloUtopiaTownError(f"{label}: source lot has invalid floor/capacity profile") from exc
    floors = interior.get("floors", [])
    if not isinstance(floors, list) or not floors:
        raise HoloUtopiaTownError(f"{label}: floors must be a non-empty list")
    floor_indexes: set[int] = set()
    for floor in floors:
        if not isinstance(floor, dict):
            raise HoloUtopiaTownError(f"{label}: floor entries must be objects")
        try:
            floor_index = int(floor.get("floor"))
        except Exception as exc:
            raise HoloUtopiaTownError(f"{label}: floor index must be an integer") from exc
        if floor_index < 0 or floor_index > lot_floors:
            raise HoloUtopiaTownError(f"{label}: floor {floor_index} outside lot floor range 0..{lot_floors}")
        if floor_index in floor_indexes:
            raise HoloUtopiaTownError(f"{label}: duplicate floor {floor_index}")
        floor_indexes.add(floor_index)
        for room in floor.get("rooms", []):
            if not isinstance(room, dict):
                raise HoloUtopiaTownError(f"{label}: floor {floor_index} room entries must be objects")
            _required_id(room, f"{label}.floor_{floor_index}.room")
            offset = room.get("local_offset_3d", [0, 0, floor_index])
            if not isinstance(offset, list) or len(offset) != 3:
                raise HoloUtopiaTownError(f"{label}: room {room.get('id')} local_offset_3d must be [x,y,z]")
    units = interior.get("resident_unit_slots", [])
    if not isinstance(units, list):
        raise HoloUtopiaTownError(f"{label}: resident_unit_slots must be a list")
    unit_ids: set[str] = set()
    total_capacity = 0
    for unit in units:
        if not isinstance(unit, dict):
            raise HoloUtopiaTownError(f"{label}: resident unit entries must be objects")
        unit_id = _required_id(unit, f"{label}.resident_unit")
        if unit_id in unit_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate resident unit id {unit_id!r}")
        unit_ids.add(unit_id)
        try:
            floor_index = int(unit.get("floor"))
            cap = int(unit.get("capacity"))
            reserved = int(unit.get("reserved_capacity", 0))
        except Exception as exc:
            raise HoloUtopiaTownError(f"{label}: unit {unit_id!r} floor/capacity fields must be integers") from exc
        if floor_index < 1 or floor_index > lot_floors:
            raise HoloUtopiaTownError(f"{label}: unit {unit_id!r} floor outside 1..{lot_floors}")
        if cap < 1 or cap > 16:
            raise HoloUtopiaTownError(f"{label}: unit {unit_id!r} capacity must be 1..16")
        if reserved < 0 or reserved > cap:
            raise HoloUtopiaTownError(f"{label}: unit {unit_id!r} reserved_capacity must be 0..capacity")
        total_capacity += cap
    if total_capacity != lot_capacity:
        raise HoloUtopiaTownError(f"{label}: resident unit capacity {total_capacity} does not match lot capacity {lot_capacity}")
    activity_ids: set[str] = set()
    for node in interior.get("activity_nodes", []):
        if not isinstance(node, dict):
            raise HoloUtopiaTownError(f"{label}: activity_nodes entries must be objects")
        node_id = _required_id(node, f"{label}.activity_node")
        if node_id in activity_ids:
            raise HoloUtopiaTownError(f"{label}: duplicate activity node id {node_id!r}")
        activity_ids.add(node_id)
        try:
            node_floor = int(node.get("floor", 0))
        except Exception as exc:
            raise HoloUtopiaTownError(f"{label}: activity node {node_id!r} floor must be integer") from exc
        if node_floor < 0 or node_floor > lot_floors:
            raise HoloUtopiaTownError(f"{label}: activity node {node_id!r} floor outside 0..{lot_floors}")


def load_npc_database(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load NPC manifest/schedules/relationships for authored HoloUtopia citizens."""
    folder = npc_data_dir(holoverse_root)
    try:
        manifest = json.loads((folder / "npc_manifest.json").read_text(encoding="utf-8"))
        schedules = json.loads((folder / "npc_schedules.json").read_text(encoding="utf-8"))
        relationships = json.loads((folder / "npc_relationships.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaTownError(f"NPC database file missing: {exc.filename}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaTownError(f"NPC database JSON error: {exc}") from exc
    data = {"manifest": manifest, "schedules": schedules, "relationships": relationships}
    validate_npc_database(data, holoverse_root=holoverse_root)
    return data


def validate_npc_database(data: dict[str, Any], holoverse_root: Path | str | None = None) -> None:
    """Validate authored NPC identity, schedule, job, and friendship references."""
    manifest = data.get("manifest") if isinstance(data.get("manifest"), dict) else {}
    schedules = data.get("schedules") if isinstance(data.get("schedules"), dict) else {}
    relationships = data.get("relationships") if isinstance(data.get("relationships"), dict) else {}
    npcs = manifest.get("npcs", [])
    if not isinstance(npcs, list) or not npcs:
        raise HoloUtopiaTownError("NPC manifest must contain a non-empty npcs list")
    neighborhood = load_neighborhood(str(manifest.get("neighborhood_id") or DEFAULT_NEIGHBORHOOD_ID), holoverse_root=holoverse_root)
    town = load_town(str(manifest.get("town_id") or neighborhood.get("town_id") or DEFAULT_TOWN_ID), holoverse_root=holoverse_root)
    lot_ids = {str(lot.get("id")) for lot in neighborhood.get("lots", []) if isinstance(lot, dict)}
    town_node_ids = {str(node.get("id")) for node in town.get("schedule_nodes", []) if isinstance(node, dict)}
    micro_node_ids = {str(node.get("id")) for node in neighborhood.get("micro_schedule_nodes", []) if isinstance(node, dict)}
    valid_target_ids = town_node_ids | micro_node_ids
    npc_ids: set[str] = set()
    all_unit_ids: dict[str, set[str]] = {}
    all_activity_ids: set[str] = set()
    for lot in neighborhood.get("lots", []):
        if not isinstance(lot, dict):
            continue
        interior_id = str(lot.get("interior_blueprint_id", "")).strip()
        if not interior_id:
            continue
        interior = load_interior_blueprint(interior_id, holoverse_root=holoverse_root)
        all_unit_ids[interior_id] = {str(unit.get("id")) for unit in interior.get("resident_unit_slots", []) if isinstance(unit, dict)}
        all_activity_ids.update(str(node.get("id")) for node in interior.get("activity_nodes", []) if isinstance(node, dict))
        for unit in interior.get("resident_unit_slots", []):
            if isinstance(unit, dict):
                anchor = str(unit.get("schedule_anchor", "")).strip()
                if anchor:
                    all_activity_ids.add(anchor)
    valid_target_ids |= all_activity_ids
    schedule_map = schedules.get("schedules", {}) if isinstance(schedules.get("schedules"), dict) else {}
    for npc in npcs:
        if not isinstance(npc, dict):
            raise HoloUtopiaTownError("NPC manifest entries must be objects")
        npc_id = _required_id(npc, "npc_manifest.npc")
        if npc_id in npc_ids:
            raise HoloUtopiaTownError(f"Duplicate NPC id {npc_id!r}")
        npc_ids.add(npc_id)
        if str(npc.get("home_lot_id", "")) not in lot_ids:
            raise HoloUtopiaTownError(f"NPC {npc_id!r} references missing home_lot_id {npc.get('home_lot_id')!r}")
        interior_id = str(npc.get("home_interior_id", ""))
        if interior_id not in all_unit_ids:
            raise HoloUtopiaTownError(f"NPC {npc_id!r} references missing home_interior_id {interior_id!r}")
        if str(npc.get("home_unit_id", "")) not in all_unit_ids[interior_id]:
            raise HoloUtopiaTownError(f"NPC {npc_id!r} references missing home_unit_id {npc.get('home_unit_id')!r}")
        job = npc.get("job") if isinstance(npc.get("job"), dict) else {}
        if str(job.get("work_node", "")) not in valid_target_ids:
            raise HoloUtopiaTownError(f"NPC {npc_id!r} references missing job.work_node {job.get('work_node')!r}")
        if npc_id not in schedule_map:
            raise HoloUtopiaTownError(f"NPC {npc_id!r} has no schedule entry")
    for npc in npcs:
        for friend in npc.get("friends", []):
            if str(friend) not in npc_ids:
                raise HoloUtopiaTownError(f"NPC {npc.get('id')!r} references unknown friend {friend!r}")
    for npc_id, schedule in schedule_map.items():
        if str(npc_id) not in npc_ids:
            raise HoloUtopiaTownError(f"Schedule exists for unknown NPC {npc_id!r}")
        for block in schedule.get("blocks", []):
            if not isinstance(block, dict):
                raise HoloUtopiaTownError(f"Schedule {npc_id!r} block entries must be objects")
            target = str(block.get("target", ""))
            if target and target not in valid_target_ids:
                raise HoloUtopiaTownError(f"Schedule {npc_id!r} references missing target {target!r}")
    for rel in relationships.get("relationships", []):
        if not isinstance(rel, dict):
            raise HoloUtopiaTownError("Relationship entries must be objects")
        if str(rel.get("a")) not in npc_ids or str(rel.get("b")) not in npc_ids:
            raise HoloUtopiaTownError(f"Relationship references unknown NPCs: {rel!r}")



def citizen_data_dir(holoverse_root: Path | str | None = None) -> Path:
    """Resolve city-wide authored citizen database folder."""
    return utopia_data_dir(holoverse_root) / "citizens"


def load_citizen_database(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load and validate city-wide authored citizens/schedules/relationships."""
    folder = citizen_data_dir(holoverse_root)
    try:
        manifest = json.loads((folder / "citizen_manifest.json").read_text(encoding="utf-8"))
        schedules = json.loads((folder / "citizen_schedules.json").read_text(encoding="utf-8"))
        relationships = json.loads((folder / "citizen_relationships.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaTownError(f"Citizen database file missing: {exc.filename}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaTownError(f"Citizen database JSON error: {exc}") from exc
    data = {"manifest": manifest, "schedules": schedules, "relationships": relationships}
    validate_citizen_database(data, holoverse_root=holoverse_root)
    return data


def validate_citizen_database(data: dict[str, Any], holoverse_root: Path | str | None = None) -> None:
    """Validate city-wide citizens against authored towns/neighborhoods."""
    manifest = data.get("manifest") if isinstance(data.get("manifest"), dict) else {}
    schedules_doc = data.get("schedules") if isinstance(data.get("schedules"), dict) else {}
    relationships_doc = data.get("relationships") if isinstance(data.get("relationships"), dict) else {}
    citizens = manifest.get("citizens", [])
    if not isinstance(citizens, list) or not citizens:
        raise HoloUtopiaTownError("Citizen manifest must contain a non-empty citizens list")
    neighborhoods = {n["id"]: n for n in load_all_neighborhoods(holoverse_root)}
    towns = {town_id: load_town(town_id, holoverse_root=holoverse_root) for town_id in list_town_ids(holoverse_root)}
    town_nodes: dict[str, set[str]] = {}
    for town_id, town in towns.items():
        town_nodes[town_id] = {str(node.get("id")) for node in town.get("schedule_nodes", []) if isinstance(node, dict)}
    neighborhood_lots: dict[str, set[str]] = {}
    neighborhood_home_nodes: dict[str, set[str]] = {}
    neighborhood_micro_nodes: dict[str, set[str]] = {}
    for nid, neighborhood in neighborhoods.items():
        neighborhood_lots[nid] = {str(lot.get("id")) for lot in neighborhood.get("lots", []) if isinstance(lot, dict)}
        neighborhood_home_nodes[nid] = {str(lot.get("home_node")) for lot in neighborhood.get("lots", []) if isinstance(lot, dict)}
        neighborhood_micro_nodes[nid] = {str(node.get("id")) for node in neighborhood.get("micro_schedule_nodes", []) if isinstance(node, dict)}
    citizen_ids: set[str] = set()
    schedule_map = schedules_doc.get("schedules", {}) if isinstance(schedules_doc.get("schedules"), dict) else {}
    for citizen in citizens:
        if not isinstance(citizen, dict):
            raise HoloUtopiaTownError("Citizen manifest entries must be objects")
        cid = _required_id(citizen, "citizen_manifest.citizen")
        if cid in citizen_ids:
            raise HoloUtopiaTownError(f"Duplicate citizen id {cid!r}")
        citizen_ids.add(cid)
        town_id = str(citizen.get("town_id", ""))
        nid = str(citizen.get("neighborhood_id", ""))
        if town_id not in towns:
            raise HoloUtopiaTownError(f"Citizen {cid!r} references missing town_id {town_id!r}")
        if nid not in neighborhoods:
            raise HoloUtopiaTownError(f"Citizen {cid!r} references missing neighborhood_id {nid!r}")
        if str(neighborhoods[nid].get("town_id")) != town_id:
            raise HoloUtopiaTownError(f"Citizen {cid!r} town/neighborhood mismatch")
        if str(citizen.get("home_lot_id", "")) not in neighborhood_lots[nid]:
            raise HoloUtopiaTownError(f"Citizen {cid!r} references missing home_lot_id {citizen.get('home_lot_id')!r}")
        home_node = str(citizen.get("home_node", ""))
        if home_node not in town_nodes[town_id] and home_node not in neighborhood_home_nodes[nid] and home_node not in neighborhood_micro_nodes[nid]:
            raise HoloUtopiaTownError(f"Citizen {cid!r} references missing home_node {home_node!r}")
        job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
        work_town = str(job.get("work_town_id") or town_id)
        work_node = str(job.get("work_node", ""))
        if work_town not in towns or work_node not in town_nodes[work_town]:
            raise HoloUtopiaTownError(f"Citizen {cid!r} references missing job work node {work_town}:{work_node}")
        if cid not in schedule_map:
            raise HoloUtopiaTownError(f"Citizen {cid!r} has no schedule entry")
    for cid, schedule in schedule_map.items():
        if str(cid) not in citizen_ids:
            raise HoloUtopiaTownError(f"Schedule exists for unknown citizen {cid!r}")
        citizen = next(c for c in citizens if c.get("id") == cid)
        town_id = str(citizen.get("town_id"))
        nid = str(citizen.get("neighborhood_id"))
        job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
        work_town = str(job.get("work_town_id") or town_id)
        valid_targets = set(town_nodes.get(town_id, set())) | set(town_nodes.get(work_town, set())) | set(neighborhood_home_nodes.get(nid, set())) | set(neighborhood_micro_nodes.get(nid, set()))
        for block in schedule.get("blocks", []):
            if not isinstance(block, dict):
                raise HoloUtopiaTownError(f"Citizen schedule {cid!r} block entries must be objects")
            target = str(block.get("target", ""))
            if target and target not in valid_targets:
                raise HoloUtopiaTownError(f"Citizen schedule {cid!r} references missing target {target!r}")
        for friend in schedule.get("friend_visit_targets", []):
            if str(friend) not in citizen_ids:
                raise HoloUtopiaTownError(f"Citizen schedule {cid!r} references missing friend {friend!r}")
    for citizen in citizens:
        for friend in citizen.get("friends", []):
            if str(friend) not in citizen_ids:
                raise HoloUtopiaTownError(f"Citizen {citizen.get('id')!r} references missing friend {friend!r}")
    for rel in relationships_doc.get("relationships", []):
        if not isinstance(rel, dict):
            raise HoloUtopiaTownError("Citizen relationship entries must be objects")
        if str(rel.get("a")) not in citizen_ids or str(rel.get("b")) not in citizen_ids:
            raise HoloUtopiaTownError(f"Citizen relationship references unknown citizens: {rel!r}")


def attach_holoutopia_highlighted_interior(parent: Any, holoverse_root: Path | str | None = None, neighborhood_id: str = DEFAULT_NEIGHBORHOOD_ID, lot_id: str = "res_alpha_lot_07", *, z: float = 0.12) -> Any:
    """Attach one neighborhood plus the selected building interior cutaway.

    This is a preview/runtime hook for the highlight-only policy: callers should
    remove the returned node before loading another building interior.
    """
    neighborhood = load_neighborhood(neighborhood_id, holoverse_root=holoverse_root)
    lot = next((item for item in neighborhood.get("lots", []) if isinstance(item, dict) and str(item.get("id")) == str(lot_id)), None)
    if lot is None:
        raise HoloUtopiaTownError(f"Neighborhood {neighborhood_id!r} has no lot {lot_id!r}")
    interior = load_interior_blueprint(str(lot.get("interior_blueprint_id")), holoverse_root=holoverse_root)
    root = attach_holoutopia_neighborhood(parent, holoverse_root=holoverse_root, neighborhood_id=neighborhood_id, z=z)
    town = load_town(str(neighborhood.get("town_id") or DEFAULT_TOWN_ID), holoverse_root=holoverse_root)
    block_by_id = {str(block.get("id")): block for block in town.get("town_blocks", []) if isinstance(block, dict)}
    block = block_by_id.get(str(lot.get("block")))
    if block is None:
        raise HoloUtopiaTownError(f"Lot {lot_id!r} references missing block {lot.get('block')!r}")
    from panda3d.core import LineSegs, TextNode, TransparencyAttrib
    overlay = root.attachNewNode(f"holoutopia_highlighted_interior_{lot_id}")
    overlay.setLightOff(True)
    overlay.setTransparency(TransparencyAttrib.M_alpha)
    profile = lot.get("building_profile", {}) if isinstance(lot.get("building_profile"), dict) else {}
    footprint = lot.get("footprint", {}) if isinstance(lot.get("footprint"), dict) else {}
    center = neighborhood_local_point(town, block, footprint.get("local_offset", [0, 0]))
    block_size = float(town["block_size"])
    sx, sy = _local_size_pair(footprint.get("size_blocks", [0.55, 0.55]), "highlight.footprint.size_blocks")
    half_w = sx * block_size * 0.34
    half_h = sy * block_size * 0.34
    floors = max(1, int(profile.get("floor_count", 1)))
    height = float(profile.get("height_units", floors * 16.0))
    base_z = z + 0.6
    color = (1.0, 0.96, 0.45, 0.98)
    room_color = (0.18, 1.0, 0.86, 0.82)
    npc_color = (1.0, 0.38, 0.24, 0.95)

    def line(name: str, pts: list[tuple[float, float, float]], col=color, thickness: float = 2.0) -> Any:
        lines = LineSegs(name)
        lines.setThickness(thickness)
        lines.setColor(*col)
        if not pts:
            return overlay.attachNewNode(lines.create())
        lines.moveTo(*pts[0])
        for p in pts[1:]:
            lines.drawTo(*p)
        node = overlay.attachNewNode(lines.create())
        node.setLightOff(True)
        return node

    # Highlight halo around selected building base.
    corners = [
        (center.x - half_w * 1.65, center.y - half_h * 1.65, base_z),
        (center.x + half_w * 1.65, center.y - half_h * 1.65, base_z),
        (center.x + half_w * 1.65, center.y + half_h * 1.65, base_z),
        (center.x - half_w * 1.65, center.y + half_h * 1.65, base_z),
        (center.x - half_w * 1.65, center.y - half_h * 1.65, base_z),
    ]
    line(f"{lot_id}_highlight_halo", corners, (1.0, 0.88, 0.18, 0.96), 3.4)
    # Interior cutaway floors are placed outside the selected building footprint.
    # They should never visually cut through or occupy the same space as the massing.
    outward = 1.0 if center.x >= 0.0 else -1.0
    cut_x = center.x + outward * (half_w * 4.2 + 42.0)
    cut_y = center.y
    floor_h = height / floors
    for floor in range(0, floors + 1):
        fz = base_z + floor * floor_h
        rect = [
            (cut_x - half_w, cut_y - half_h, fz),
            (cut_x + half_w, cut_y - half_h, fz),
            (cut_x + half_w, cut_y + half_h, fz),
            (cut_x - half_w, cut_y + half_h, fz),
            (cut_x - half_w, cut_y - half_h, fz),
        ]
        line(f"{lot_id}_interior_floor_{floor:02d}", rect, color if floor in {0, floors} else (0.95, 1.0, 0.55, 0.58), 1.9 if floor in {0, floors} else 1.2)
    for x, y in [(cut_x-half_w, cut_y-half_h), (cut_x+half_w, cut_y-half_h), (cut_x+half_w, cut_y+half_h), (cut_x-half_w, cut_y+half_h)]:
        line(f"{lot_id}_cutaway_edge_{x:.1f}_{y:.1f}", [(x, y, base_z), (x, y, base_z + height)], color, 1.6)
    # Room/activity markers.
    for node in interior.get("activity_nodes", []):
        if not isinstance(node, dict):
            continue
        floor = int(node.get("floor", 0))
        ox, oy, _oz = node.get("local_offset_3d", [0, 0, floor])
        px = cut_x + float(ox) * block_size * 0.55
        py = cut_y + float(oy) * block_size * 0.55
        pz = base_z + floor * floor_h + 1.4
        line(str(node.get("id", "activity")), [(px-3, py-3, pz), (px+3, py+3, pz), (px+3, py-3, pz), (px-3, py+3, pz)], room_color, 1.7)
    for unit in interior.get("resident_unit_slots", []):
        if not isinstance(unit, dict):
            continue
        if unit.get("assigned_npc_ids"):
            floor = int(unit.get("floor", 1))
            pz = base_z + floor * floor_h + 2.2
            px = cut_x - half_w * 0.62
            py = cut_y + half_h * 0.58
            line(f"{unit.get('id')}_assigned_resident_marker", [(px-4, py, pz), (px+4, py, pz), (px, py-4, pz), (px, py+4, pz)], npc_color, 2.2)
    label = TextNode("highlighted_interior_label")
    label.setText(f"HIGHLIGHTED: {lot.get('display_name', lot_id)}\\ninterior loads on selection only")
    label.setAlign(TextNode.ACenter)
    label.setTextColor(1.0, 0.96, 0.52, 0.95)
    label_node = overlay.attachNewNode(label)
    label_node.setScale(4.8)
    label_node.setPos(cut_x, cut_y - half_h * 2.0, base_z + height + 8.0)
    label_node.setHpr(0, -68, 0)
    label_node.setLightOff(True)
    return root


def _attach_block(root: Any, town: dict[str, Any], block: dict[str, Any], palette: dict[str, tuple[float, float, float, float]], z: float, CardMaker: Any, Vec3: Any, Vec4: Any, TransparencyAttrib: Any, draw_polyline: Any, *, show_structure_massing: bool = True) -> None:
    """Render one town block as either a clean footprint or purposeful 3D massing."""
    block_size = float(town["block_size"])
    gx, gy = block["grid"]
    sx, sy = block.get("size", [1, 1])
    center_grid = [float(gx) + (float(sx) - 1.0) * 0.5, float(gy) + (float(sy) - 1.0) * 0.5]
    center = grid_to_world(town, center_grid)
    color = _block_color(block, palette)
    profile = block.get("structure_massing_profile", {}) if isinstance(block.get("structure_massing_profile"), dict) else {}
    footprint_scale = profile.get("footprint_scale", [0.74, 0.74]) if show_structure_massing else [0.74, 0.74]
    base_pad_scale = profile.get("base_pad_scale", [0.82, 0.82]) if show_structure_massing else [0.74, 0.74]
    try:
        fsx, fsy = float(footprint_scale[0]), float(footprint_scale[1])
        psx, psy = float(base_pad_scale[0]), float(base_pad_scale[1])
    except Exception:
        fsx, fsy, psx, psy = 0.74, 0.74, 0.82, 0.82
    pad_w = float(sx) * block_size * max(0.20, min(psx, 1.30))
    pad_h = float(sy) * block_size * max(0.20, min(psy, 1.30))
    w = float(sx) * block_size * max(0.16, min(fsx, 1.30))
    h = float(sy) * block_size * max(0.16, min(fsy, 1.30))

    def rect(half_w: float, half_h: float) -> list[TownPoint]:
        return [
            TownPoint(center.x - half_w, center.y - half_h),
            TownPoint(center.x + half_w, center.y - half_h),
            TownPoint(center.x + half_w, center.y + half_h),
            TownPoint(center.x - half_w, center.y + half_h),
        ]

    # Foundation/ground-contact pad first. It covers the local grid under the massing
    # so visual guide lines do not appear to slice through the structure.
    cm = CardMaker(f"{block.get('id', 'block')}_foundation")
    cm.setFrame(-pad_w * 0.5, pad_w * 0.5, -pad_h * 0.5, pad_h * 0.5)
    card = root.attachNewNode(cm.generate())
    card.setPos(center.x, center.y, z)
    card.setHpr(0, -90, 0)
    card.setColorScale(color[0], color[1], color[2], 0.12 if show_structure_massing else 0.08)
    card.setTransparency(TransparencyAttrib.M_alpha)
    card.setLightOff(True)
    draw_polyline(f"{block.get('id', 'block')}_foundation_outline", rect(pad_w * 0.5, pad_h * 0.5), color, 1.8, closed=True)

    if not show_structure_massing:
        draw_polyline(f"{block.get('id', 'block')}_outline", rect(w * 0.5, h * 0.5), color, 1.6, closed=True)
        return

    massing_kind = str(profile.get("massing_kind", "district_structure"))
    floor_count = max(1, int(profile.get("floor_count", 1)))
    height_units = float(profile.get("height_units", max(10.0, floor_count * 14.0)))
    visual = profile.get("visual_policy", {}) if isinstance(profile.get("visual_policy"), dict) else {}
    floor_bands = str(visual.get("floor_bands", "outer_perimeter_only"))
    base_z = z + 0.18
    top_z = base_z + max(4.0, height_units)
    corners = rect(w * 0.5, h * 0.5)
    # Purposeful open spaces are still 3D, but represented as low perimeter volumes/posts.
    low_volume = massing_kind in {"open_water_basin_edge_volume", "public_open_space_marker"}
    draw_polyline(f"{block.get('id', 'block')}_massing_base", corners, color, 2.0, closed=True, z_value=base_z)
    draw_polyline(f"{block.get('id', 'block')}_massing_top", corners, color, 2.2 if not low_volume else 1.6, closed=True, z_value=top_z)
    for idx, c in enumerate(corners):
        # Use a tiny local LineSegs directly for verticals.
        from panda3d.core import LineSegs
        seg = LineSegs(f"{block.get('id', 'block')}_vertical_segment_{idx}")
        seg.setThickness(1.6 if not low_volume else 1.2)
        seg.setColor(*color)
        seg.moveTo(c.x, c.y, base_z)
        seg.drawTo(c.x, c.y, top_z)
        node = root.attachNewNode(seg.create())
        node.setLightOff(True)
    if floor_bands == "outer_perimeter_only" and floor_count > 1 and not low_volume:
        for floor in range(1, floor_count):
            fz = base_z + (height_units / float(floor_count)) * floor
            draw_polyline(f"{block.get('id', 'block')}_floor_band_{floor:02d}", corners, (color[0], color[1], color[2], min(color[3], 0.52)), 0.9, closed=True, z_value=fz)

    _attach_district_facade_details(
        root,
        town,
        block,
        center,
        w,
        h,
        base_z,
        top_z,
        floor_count,
        low_volume,
        color,
        CardMaker,
        TransparencyAttrib,
        draw_polyline,
    )


def _attach_district_facade_details(root: Any, town: dict[str, Any], block: dict[str, Any], center: TownPoint, width: float, depth: float, base_z: float, top_z: float, floor_count: int, low_volume: bool, base_color: tuple[float, float, float, float], CardMaker: Any, TransparencyAttrib: Any, draw_polyline: Any) -> None:
    """Add district-colored windows, facade glow, and roof accents to 3D blocks.

    This keeps the original wireframe look, but makes each district read more like
    a real game-space by tinting facade details per district instead of drawing
    every building with the same generic color language.
    """
    if low_volume:
        return
    height = max(4.0, float(top_z) - float(base_z))
    if height < 8.0 or width < 10.0 or depth < 10.0:
        return

    theme = _district_facade_theme(town, block, base_color)
    body_glow = theme["body_glow"]
    window_glow = theme["window_glow"]
    accent_glow = theme["accent_glow"]
    side_window_glow = theme["side_window_glow"]

    def add_panel(name: str, px: float, py: float, pz: float, panel_w: float, panel_h: float, heading: float, color: tuple[float, float, float, float], *, pulse_strength: float = 0.0, pulse_speed: float = 0.0, pulse_phase: float = 0.0) -> Any:
        cm = CardMaker(name)
        cm.setFrame(-panel_w * 0.5, panel_w * 0.5, -panel_h * 0.5, panel_h * 0.5)
        node = root.attachNewNode(cm.generate())
        node.setPos(px, py, pz)
        node.setHpr(heading, 0.0, 0.0)
        node.setColorScale(*color)
        node.setTransparency(TransparencyAttrib.M_alpha)
        node.setTwoSided(True)
        node.setLightOff(True)
        if pulse_strength > 0.0:
            _tag_pulse_node(node, color, pulse_strength, pulse_speed, pulse_phase)
        return node

    def add_line3d(name: str, points: list[tuple[float, float, float]], color: tuple[float, float, float, float], thickness: float = 1.4, *, pulse_strength: float = 0.0, pulse_speed: float = 0.0, pulse_phase: float = 0.0) -> Any:
        from panda3d.core import LineSegs

        seg = LineSegs(name)
        seg.setThickness(thickness)
        seg.setColor(*color)
        if not points:
            node = root.attachNewNode(seg.create())
        else:
            seg.moveTo(*points[0])
            for point in points[1:]:
                seg.drawTo(*point)
            node = root.attachNewNode(seg.create())
        node.setLightOff(True)
        if pulse_strength > 0.0:
            _tag_pulse_node(node, color, pulse_strength, pulse_speed, pulse_phase)
        return node

    def add_vertical_bar_pair(name: str, x1: float, x2: float, y: float, z1: float, z2: float, color: tuple[float, float, float, float]) -> None:
        add_line3d(f"{name}_left", [(x1, y, z1), (x1, y, z2)], color, 1.45, pulse_strength=0.10, pulse_speed=0.72, pulse_phase=0.3)
        add_line3d(f"{name}_right", [(x2, y, z1), (x2, y, z2)], color, 1.45, pulse_strength=0.10, pulse_speed=0.72, pulse_phase=1.1)

    power_key = _block_key_text(block)
    power_open_pad = any(token in power_key for token in ("open_equipment_yard", "service_pad", "low_profile", "transformer_parts_service_pad"))

    half_w = width * 0.5
    half_d = depth * 0.5
    body_w = max(8.0, width * 0.76)
    body_d = max(8.0, depth * 0.76)
    body_h = max(8.0, height * 0.86)
    body_z = base_z + height * 0.50
    skin_offset = 0.42

    if power_open_pad:
        # Open equipment pads should not read as glassy apartment blocks.  Keep
        # the clickable/scheduled block ID intact, but show only low electric
        # yard hardware and roof/power cues.
        _attach_industrial_power_plant_details(
            block,
            center,
            half_w,
            half_d,
            base_z,
            top_z,
            theme,
            accent_glow,
            window_glow,
            add_line3d,
        )
        _attach_district_roof_silhouette(
            block,
            center,
            half_w,
            half_d,
            top_z,
            theme,
            accent_glow,
            window_glow,
            add_line3d,
        )
        return

    add_panel(f"{block.get('id', 'block')}_facade_front", center.x, center.y - half_d - skin_offset, body_z, body_w, body_h, 0.0, body_glow, pulse_strength=0.035, pulse_speed=0.45, pulse_phase=theme["pulse_phase"])
    add_panel(f"{block.get('id', 'block')}_facade_back", center.x, center.y + half_d + skin_offset, body_z, body_w, body_h, 180.0, body_glow, pulse_strength=0.030, pulse_speed=0.45, pulse_phase=theme["pulse_phase"] + 0.7)
    add_panel(f"{block.get('id', 'block')}_facade_left", center.x - half_w - skin_offset, center.y, body_z, body_d, body_h, 90.0, _mix_color(body_glow, side_window_glow, 0.35), pulse_strength=0.025, pulse_speed=0.45, pulse_phase=theme["pulse_phase"] + 1.2)
    add_panel(f"{block.get('id', 'block')}_facade_right", center.x + half_w + skin_offset, center.y, body_z, body_d, body_h, -90.0, _mix_color(body_glow, side_window_glow, 0.35), pulse_strength=0.025, pulse_speed=0.45, pulse_phase=theme["pulse_phase"] + 1.8)

    # Pass 58 performance: keep the district-colored window language, but cap
    # the facade grid so one skyline block does not create dozens of tiny draw
    # calls per face.  Taller buildings still read as tall through floor bands
    # and roof silhouettes; window rows are a representative visual layer.
    floors = max(1, min(int(floor_count), 5))
    vertical_margin = max(3.2, min(8.0, height * 0.12))
    usable_height = max(6.0, height - vertical_margin * 2.0)
    row_step = usable_height / float(floors)
    front_cols = max(1, min(4, int(width / 20.0)))
    side_cols = max(1, min(3, int(depth / 22.0)))
    front_window_w = max(3.8, min(8.0, body_w / max(2.4, front_cols * 2.0)))
    side_window_w = max(3.4, min(7.2, body_d / max(2.2, side_cols * 2.0)))
    window_h = max(2.8, min(8.2, row_step * 0.44))

    def x_positions(span: float, count: int) -> list[float]:
        if count <= 1:
            return [0.0]
        usable = span * 0.74
        start = -usable * 0.5
        step = usable / float(count - 1)
        return [start + step * i for i in range(count)]

    front_xs = x_positions(body_w, front_cols)
    side_ys = x_positions(body_d, side_cols)

    for row in range(floors):
        z_row = base_z + vertical_margin + row_step * (row + 0.5)
        row_mix = 0.08 + (row / max(1.0, floors - 1.0)) * 0.18 if floors > 1 else 0.12
        row_color = _mix_color(window_glow, accent_glow, row_mix)
        row_side_color = _mix_color(side_window_glow, accent_glow, row_mix * 0.65)
        for local_x in front_xs:
            add_panel(
                f"{block.get('id', 'block')}_window_front_{row}_{int((local_x + 9999) * 10)}",
                center.x + local_x,
                center.y - half_d - skin_offset - 0.10,
                z_row,
                front_window_w,
                window_h,
                0.0,
                row_color,
            )
            add_panel(
                f"{block.get('id', 'block')}_window_back_{row}_{int((local_x + 9999) * 10)}",
                center.x + local_x,
                center.y + half_d + skin_offset + 0.10,
                z_row,
                front_window_w,
                window_h,
                180.0,
                row_color,
            )
        for local_y in side_ys:
            add_panel(
                f"{block.get('id', 'block')}_window_left_{row}_{int((local_y + 9999) * 10)}",
                center.x - half_w - skin_offset - 0.10,
                center.y + local_y,
                z_row,
                side_window_w,
                window_h,
                90.0,
                row_side_color,
            )
            add_panel(
                f"{block.get('id', 'block')}_window_right_{row}_{int((local_y + 9999) * 10)}",
                center.x + half_w + skin_offset + 0.10,
                center.y + local_y,
                z_row,
                side_window_w,
                window_h,
                -90.0,
                row_side_color,
            )

    # Player-facing entrance cues: every inspectable building now has a readable
    # front door glow, thin portal pylons, and a small landing strip.  These are
    # visual-only and deliberately tiny so they do not become collision or pathing
    # promises before gameplay entry is wired.
    entrance_w = max(5.0, min(12.0, width * 0.18))
    entrance_h = max(5.5, min(13.0, height * 0.22))
    entrance_z = base_z + entrance_h * 0.50 + 0.55
    entrance_y = center.y - half_d - skin_offset - 0.24
    entrance_color = _mix_color(accent_glow, window_glow, 0.42)
    add_panel(
        f"{block.get('id', 'block')}_entrance_portal",
        center.x,
        entrance_y - 0.08,
        entrance_z,
        entrance_w,
        entrance_h,
        0.0,
        entrance_color,
        pulse_strength=0.18,
        pulse_speed=0.88,
        pulse_phase=theme["pulse_phase"] + 2.4,
    )
    landing_w = max(entrance_w * 1.55, min(width * 0.34, 18.0))
    landing_d = max(4.0, min(depth * 0.18, 10.0))
    landing = [
        TownPoint(center.x - landing_w * 0.5, center.y - half_d - landing_d),
        TownPoint(center.x + landing_w * 0.5, center.y - half_d - landing_d),
        TownPoint(center.x + landing_w * 0.5, center.y - half_d - 0.8),
        TownPoint(center.x - landing_w * 0.5, center.y - half_d - 0.8),
    ]
    draw_polyline(f"{block.get('id', 'block')}_entrance_landing_glow", landing, entrance_color, 1.25, closed=True, z_value=base_z + 0.42)
    add_vertical_bar_pair(
        f"{block.get('id', 'block')}_entrance_pylon",
        center.x - entrance_w * 0.62,
        center.x + entrance_w * 0.62,
        entrance_y - 0.16,
        base_z + 0.65,
        base_z + entrance_h + 1.6,
        entrance_color,
    )

    _attach_district_roof_silhouette(
        block,
        center,
        half_w,
        half_d,
        top_z,
        theme,
        accent_glow,
        window_glow,
        add_line3d,
    )
    _attach_industrial_power_plant_details(
        block,
        center,
        half_w,
        half_d,
        base_z,
        top_z,
        theme,
        accent_glow,
        window_glow,
        add_line3d,
    )

    roof_outline = [
        TownPoint(center.x - half_w, center.y - half_d),
        TownPoint(center.x + half_w, center.y - half_d),
        TownPoint(center.x + half_w, center.y + half_d),
        TownPoint(center.x - half_w, center.y + half_d),
    ]
    draw_polyline(f"{block.get('id', 'block')}_roof_accent_outer", roof_outline, accent_glow, 2.0, closed=True, z_value=top_z + 1.0)
    draw_polyline(
        f"{block.get('id', 'block')}_roof_accent_inner",
        [
            TownPoint(center.x - body_w * 0.42, center.y - body_d * 0.42),
            TownPoint(center.x + body_w * 0.42, center.y - body_d * 0.42),
            TownPoint(center.x + body_w * 0.42, center.y + body_d * 0.42),
            TownPoint(center.x - body_w * 0.42, center.y + body_d * 0.42),
        ],
        _mix_color(accent_glow, window_glow, 0.30),
        1.2,
        closed=True,
        z_value=top_z + 2.2,
    )



def _tag_pulse_node(node: Any, base_color: tuple[float, float, float, float], strength: float, speed: float, phase: float) -> None:
    """Mark a facade NodePath for the runtime's lightweight glow pulse."""
    try:
        node.setPythonTag(
            "holoutopia_facade_pulse",
            {
                "base_color": tuple(float(v) for v in base_color),
                "strength": max(0.0, min(0.30, float(strength))),
                "speed": max(0.02, min(2.0, float(speed or 0.65))),
                "phase": float(phase or 0.0),
            },
        )
    except Exception:
        pass



def _block_key_text(block: dict[str, Any]) -> str:
    return " ".join(
        [
            str(block.get("id", "")),
            str(block.get("type", "")),
            str(block.get("style", "")),
            str(block.get("structure_variant_id", "")),
            str(block.get("purpose_id", "")),
            " ".join(str(tag) for tag in block.get("tags", [])),
        ]
    ).lower()


def _attach_industrial_power_plant_details(block: dict[str, Any], center: TownPoint, half_w: float, half_d: float, base_z: float, top_z: float, theme: dict[str, Any], accent_glow: tuple[float, float, float, float], window_glow: tuple[float, float, float, float], add_line3d: Any) -> None:
    """Add power-plant silhouettes to Industrial Yard Alpha without touching gameplay state.

    These are visual-only wire details layered onto existing safe block massing.  They
    avoid collision/pathing changes and use tags from the town data so the same code
    can style future power blocks without another one-off renderer branch.
    """
    key = _block_key_text(block)
    if not any(token in key for token in ("electric_plant", "power_plant", "substation", "transformer", "cooling_tower", "tesla_coil", "fusion_core", "thermal_storage", "transmission_tower", "turbine_hall", "generator_hall")):
        return
    block_id = str(block.get("id") or "industrial_power_block")
    phase = float(theme.get("pulse_phase") or 0.0) + (abs(hash(block_id)) % 29) * 0.07
    power_yellow = _mix_color((1.0, 0.96, 0.22, 0.96), accent_glow, 0.28)
    power_lime = _mix_color((0.55, 1.0, 0.18, 0.96), window_glow, 0.24)
    power_cyan = (0.30, 1.0, 0.92, 0.82)
    z0 = float(base_z) + 1.2
    z_mid = float(base_z) + max(8.0, (float(top_z) - float(base_z)) * 0.48)
    z_top = float(top_z) + 3.0
    w = max(7.0, min(float(half_w) * 0.82, 27.0))
    d = max(6.0, min(float(half_d) * 0.82, 25.0))

    def line(name: str, pts: list[tuple[float, float, float]], color=power_yellow, thickness: float = 1.35, strength: float = 0.13, speed: float = 0.70, offset: float = 0.0) -> None:
        add_line3d(f"{block_id}_{name}", pts, color, thickness, pulse_strength=strength, pulse_speed=speed, pulse_phase=phase + offset)

    def rect3(name: str, cx: float, cy: float, z: float, rw: float, rd: float, color=power_yellow, thickness: float = 1.2, offset: float = 0.0) -> None:
        line(
            name,
            [
                (cx - rw * 0.5, cy - rd * 0.5, z),
                (cx + rw * 0.5, cy - rd * 0.5, z),
                (cx + rw * 0.5, cy + rd * 0.5, z),
                (cx - rw * 0.5, cy + rd * 0.5, z),
                (cx - rw * 0.5, cy - rd * 0.5, z),
            ],
            color,
            thickness,
            offset=offset,
        )

    def arc(name: str, cx: float, cy: float, z: float, radius: float, color=power_lime, thickness: float = 1.15, offset: float = 0.0) -> None:
        pts = []
        for i in range(33):
            a = math.tau * i / 32.0
            pts.append((cx + math.cos(a) * radius, cy + math.sin(a) * radius, z))
        line(name, pts, color, thickness, strength=0.11, offset=offset)

    # Shared electric-yard language: bus bars and pad rails.
    rect3("electrical_pad_bus_outer", center.x, center.y, z0 + 0.8, w * 1.55, d * 1.25, _mix_color(power_yellow, power_cyan, 0.20), 1.05, 0.1)
    line("main_busbar_a", [(center.x - w * 0.70, center.y - d * 0.38, z0 + 2.2), (center.x + w * 0.70, center.y - d * 0.38, z0 + 2.2)], power_yellow, 1.55, offset=0.2)
    line("main_busbar_b", [(center.x - w * 0.70, center.y + d * 0.38, z0 + 2.2), (center.x + w * 0.70, center.y + d * 0.38, z0 + 2.2)], power_lime, 1.35, offset=0.5)

    if "cooling_tower" in key or "coolant_loop" in key:
        for idx, ox in enumerate((-w * 0.26, w * 0.26)):
            x = center.x + ox
            for ring, zf in enumerate((z0 + 4.0, z_mid, z_top)):
                arc(f"cooling_tower_{idx}_ring_{ring}", x, center.y, zf, max(4.0, w * (0.18 + 0.03 * ring)), power_cyan if ring == 1 else power_lime, 1.25, idx + ring * 0.2)
            for side in (-1, 1):
                line(f"cooling_tower_{idx}_leg_{side}", [(x + side * w * 0.18, center.y - d * 0.18, z0 + 3.0), (x + side * w * 0.12, center.y - d * 0.06, z_top)], power_lime, 1.2, offset=idx + side * 0.3)
        return

    if "fusion_core" in key or "reactor_core" in key:
        for level, zf in enumerate((z0 + 5.0, z_mid, z_top - 2.0)):
            arc(f"reactor_containment_ring_{level}", center.x, center.y, zf, max(6.0, w * (0.30 + level * 0.04)), power_yellow if level != 1 else power_cyan, 1.45, level * 0.35)
        for i in range(8):
            a = math.tau * i / 8.0
            x = center.x + math.cos(a) * w * 0.38
            y = center.y + math.sin(a) * d * 0.38
            line(f"reactor_containment_strut_{i}", [(x, y, z0 + 4.0), (center.x, center.y, z_top + 6.0)], power_lime, 1.05, offset=i * 0.2)
        line("reactor_core_spire", [(center.x, center.y, z0 + 5.0), (center.x, center.y, z_top + 11.0)], power_yellow, 1.8, offset=1.3)
        return

    if "transmission_tower" in key or "relay_spire" in key:
        base = z0 + 1.0
        top = max(z_top + 18.0, top_z + 18.0)
        for sx in (-1, 1):
            line(f"tower_leg_{sx}", [(center.x + sx * w * 0.18, center.y - d * 0.22, base), (center.x + sx * w * 0.07, center.y, top)], power_lime, 1.4, offset=sx * 0.5)
            line(f"tower_leg_back_{sx}", [(center.x + sx * w * 0.18, center.y + d * 0.22, base), (center.x + sx * w * 0.07, center.y, top)], power_lime, 1.4, offset=0.4 + sx * 0.5)
        for level, frac in enumerate((0.28, 0.48, 0.68, 0.84)):
            zf = base + (top - base) * frac
            line(f"tower_crossarm_{level}", [(center.x - w * 0.62, center.y, zf), (center.x + w * 0.62, center.y, zf)], power_yellow, 1.4, offset=level * 0.22)
            line(f"tower_crossbrace_{level}", [(center.x - w * 0.26, center.y, zf - 3.0), (center.x + w * 0.26, center.y, zf + 3.0)], power_cyan, 0.95, offset=level * 0.31)
        return

    if "tesla_coil" in key or "coil_yard" in key:
        for idx, ox in enumerate((-w * 0.35, 0.0, w * 0.35)):
            x = center.x + ox
            line(f"coil_spire_{idx}", [(x, center.y, z0 + 2.0), (x, center.y, z_mid + 12.0)], power_lime, 1.6, offset=idx * 0.4)
            for ring in range(4):
                arc(f"coil_{idx}_ring_{ring}", x, center.y, z0 + 6.0 + ring * 5.0, max(2.4, w * 0.105), power_yellow if ring % 2 else power_cyan, 1.0, idx * 0.4 + ring * 0.15)
        return

    if "transformer" in key or "capacitor_bank" in key or "substation" in key or "inverter_field" in key or "open_equipment_yard" in key:
        for idx, ox in enumerate((-w * 0.42, -w * 0.14, w * 0.14, w * 0.42)):
            cx = center.x + ox
            rect3(f"transformer_unit_{idx}_base", cx, center.y, z0 + 3.4, max(4.0, w * 0.20), max(4.0, d * 0.30), power_yellow if idx % 2 else power_cyan, 1.15, idx * 0.18)
            line(f"transformer_unit_{idx}_post_a", [(cx - w * 0.08, center.y, z0 + 2.8), (cx - w * 0.08, center.y, z0 + 12.0)], power_lime, 1.05, offset=idx * 0.22)
            line(f"transformer_unit_{idx}_post_b", [(cx + w * 0.08, center.y, z0 + 2.8), (cx + w * 0.08, center.y, z0 + 12.0)], power_lime, 1.05, offset=idx * 0.22 + 0.1)
        return

    if "thermal_storage" in key or "silo" in key:
        for level, zf in enumerate((z0 + 4.0, z_mid, z_top)):
            arc(f"thermal_silo_ring_{level}", center.x, center.y, zf, max(5.5, w * 0.27), power_yellow if level != 1 else power_cyan, 1.25, level * 0.28)
        for i in range(6):
            a = math.tau * i / 6.0
            x = center.x + math.cos(a) * w * 0.28
            y = center.y + math.sin(a) * d * 0.28
            line(f"thermal_silo_leg_{i}", [(x, y, z0 + 4.0), (x * 0.96 + center.x * 0.04, y * 0.96 + center.y * 0.04, z_top + 1.0)], power_lime, 1.05, offset=i * 0.17)
        return

    if "turbine_hall" in key or "generator_hall" in key:
        for idx, oy in enumerate((-d * 0.28, d * 0.28)):
            line(f"turbine_rotor_axis_{idx}", [(center.x - w * 0.48, center.y + oy, z_mid), (center.x + w * 0.48, center.y + oy, z_mid)], power_cyan, 1.6, offset=idx * 0.55)
            for step in range(5):
                x = center.x - w * 0.42 + step * w * 0.21
                line(f"turbine_rotor_{idx}_{step}", [(x, center.y + oy - 4.5, z_mid - 3.0), (x, center.y + oy + 4.5, z_mid + 3.0)], power_yellow, 1.05, offset=idx + step * 0.16)
        return

def _attach_district_roof_silhouette(block: dict[str, Any], center: TownPoint, half_w: float, half_d: float, top_z: float, theme: dict[str, Any], accent_glow: tuple[float, float, float, float], window_glow: tuple[float, float, float, float], add_line3d: Any) -> None:
    """Add small district-specific silhouettes so skylines no longer share one box shape."""
    block_id = str(block.get("id") or "block")
    roof = str(theme.get("roof_profile") or "civic_spire")
    phase = float(theme.get("pulse_phase") or 0.0)
    z = float(top_z) + 2.2
    color = _mix_color(accent_glow, window_glow, 0.22)
    strong = _mix_color(accent_glow, (1.0, 1.0, 1.0, accent_glow[3]), 0.15)
    w = max(6.0, min(half_w * 0.62, 24.0))
    d = max(5.0, min(half_d * 0.62, 22.0))

    def pulse_line(name: str, points: list[tuple[float, float, float]], c: tuple[float, float, float, float] = color, thick: float = 1.35, offset: float = 0.0) -> None:
        add_line3d(f"{block_id}_{name}", points, c, thick, pulse_strength=0.12, pulse_speed=0.62, pulse_phase=phase + offset)

    # All profiles are tiny visual rooftop signatures, not collision or gameplay blockers.
    if roof == "electric_plant":
        pulse_line("roof_power_bus_left", [(center.x - w, center.y - d * 0.58, z + 1.0), (center.x - w, center.y + d * 0.58, z + 1.0)], strong, 1.35, 0.1)
        pulse_line("roof_power_bus_right", [(center.x + w, center.y - d * 0.58, z + 1.0), (center.x + w, center.y + d * 0.58, z + 1.0)], strong, 1.35, 0.5)
        pulse_line("roof_power_crossbar", [(center.x - w * 0.72, center.y, z + 5.0), (center.x + w * 0.72, center.y, z + 5.0)], color, 1.35, 0.9)
        pulse_line("roof_power_spike", [(center.x, center.y, z + 1.0), (center.x, center.y, z + 13.0)], strong, 1.35, 1.2)
    elif roof == "industrial_stacks":
        for idx, ox in enumerate((-w * 0.38, w * 0.28)):
            x = center.x + ox
            y = center.y + d * (0.12 + idx * 0.18)
            h = 9.0 + idx * 2.5
            pulse_line(f"roof_stack_{idx}_a", [(x - 2.0, y, z), (x - 2.0, y, z + h)], strong, 1.5, idx * 0.5)
            pulse_line(f"roof_stack_{idx}_b", [(x + 2.0, y, z), (x + 2.0, y, z + h)], strong, 1.5, idx * 0.5 + 0.2)
            pulse_line(f"roof_stack_{idx}_cap", [(x - 3.0, y, z + h), (x + 3.0, y, z + h)], strong, 1.2, idx * 0.5 + 0.4)
        pulse_line("roof_pipe_run", [(center.x - w, center.y + d * 0.45, z + 2.2), (center.x + w, center.y + d * 0.45, z + 2.2)], color, 1.2, 1.1)
    elif roof == "market_canopy":
        y = center.y - d * 0.62
        pts = []
        for i in range(7):
            x = center.x - w + (2.0 * w / 6.0) * i
            pts.append((x, y, z + (4.0 if i % 2 else 0.4)))
        pulse_line("roof_canopy_zigzag", pts, strong, 1.5, 0.0)
        pulse_line("roof_canopy_back", [(center.x - w, center.y - d * 0.15, z + 1.2), (center.x + w, center.y - d * 0.15, z + 1.2)], color, 1.1, 0.8)
    elif roof == "harbor_mast":
        pulse_line("roof_mast", [(center.x, center.y, z), (center.x, center.y, z + 15.0)], strong, 1.45, 0.0)
        pulse_line("roof_mast_arm", [(center.x - w * 0.62, center.y, z + 10.5), (center.x + w * 0.62, center.y, z + 10.5)], color, 1.2, 0.7)
        pulse_line("roof_signal_flag", [(center.x, center.y, z + 15.0), (center.x + w * 0.38, center.y + 2.2, z + 11.5), (center.x, center.y, z + 11.5)], strong, 1.1, 1.2)
    elif roof == "archive_spires":
        for idx, ox in enumerate((-w * 0.42, 0.0, w * 0.42)):
            h = 10.0 if idx != 1 else 15.0
            pulse_line(f"roof_archive_spire_{idx}", [(center.x + ox, center.y, z), (center.x + ox, center.y, z + h)], strong, 1.3, idx * 0.35)
            pulse_line(f"roof_archive_spire_cap_{idx}", [(center.x + ox - 2.8, center.y, z + h - 2.8), (center.x + ox, center.y, z + h), (center.x + ox + 2.8, center.y, z + h - 2.8)], color, 1.1, idx * 0.35 + 0.2)
    elif roof == "residential_garden":
        y1 = center.y - d * 0.45
        y2 = center.y + d * 0.45
        for x in (center.x - w * 0.45, center.x, center.x + w * 0.45):
            pulse_line(f"roof_garden_post_{int(x * 10)}", [(x, y1, z), (x, y1, z + 4.8), (x, y2, z + 4.8), (x, y2, z)], color, 1.0, abs(x) * 0.015)
        pulse_line("roof_garden_rail", [(center.x - w, y1, z + 2.0), (center.x + w, y1, z + 2.0), (center.x + w, y2, z + 2.0), (center.x - w, y2, z + 2.0), (center.x - w, y1, z + 2.0)], strong, 1.2, 1.1)
    elif roof == "security_crenel":
        y = center.y + d * 0.58
        for i in range(6):
            x1 = center.x - w + (2.0 * w / 6.0) * i
            x2 = x1 + (2.0 * w / 6.0) * 0.52
            pulse_line(f"roof_guard_tooth_{i}", [(x1, y, z), (x1, y, z + 4.8), (x2, y, z + 4.8), (x2, y, z)], strong, 1.15, i * 0.25)
        pulse_line("roof_guard_beacon", [(center.x, center.y, z), (center.x, center.y, z + 11.0)], color, 1.25, 1.6)
    elif roof == "glitch_spikes":
        pts = []
        for i in range(9):
            x = center.x - w + (2.0 * w / 8.0) * i
            y = center.y + (-d * 0.35 if i % 2 else d * 0.28)
            pts.append((x, y, z + (2.0 + (i % 3) * 4.0)))
        pulse_line("roof_glitch_jagged", pts, strong, 1.55, 0.0)
        for i, point in enumerate(pts[1::2]):
            pulse_line(f"roof_glitch_drop_{i}", [point, (point[0] + 3.0, point[1] - 2.5, z + 0.6)], color, 1.05, i * 0.5)
    elif roof == "civic_dome":
        pts = []
        for i in range(13):
            a = math.pi * i / 12.0
            pts.append((center.x - w + 2.0 * w * i / 12.0, center.y, z + math.sin(a) * 8.0))
        pulse_line("roof_civic_dome_arc", pts, strong, 1.35, 0.0)
        pulse_line("roof_civic_dome_base", [(center.x - w, center.y, z), (center.x + w, center.y, z)], color, 1.15, 0.8)
    else:
        pulse_line("roof_core_spire", [(center.x, center.y, z), (center.x, center.y, z + 16.0)], strong, 1.45, 0.0)
        pulse_line("roof_core_diamond", [(center.x, center.y - 4.5, z + 9.5), (center.x + 4.5, center.y, z + 13.8), (center.x, center.y + 4.5, z + 9.5), (center.x - 4.5, center.y, z + 13.8), (center.x, center.y - 4.5, z + 9.5)], color, 1.15, 0.8)


def _district_facade_theme(town: dict[str, Any], block: dict[str, Any], base_color: tuple[float, float, float, float]) -> dict[str, tuple[float, float, float, float]]:
    district = str(town.get("district_type") or "").lower()
    style = str(block.get("style") or "").lower()
    tags = " ".join(str(tag).lower() for tag in block.get("tags", []))
    key = f"{district} {style} {tags}"
    themes: list[tuple[tuple[str, ...], dict[str, tuple[float, float, float, float]]]] = [
        (("central_core", "matrixcore", "core"), {"window_glow": (0.76, 0.98, 1.0, 0.96), "accent_glow": (1.0, 0.32, 0.86, 0.96), "body_glow": (0.16, 0.56, 0.78, 0.16), "roof_profile": "core_spire", "pulse_phase": 0.1}),
        (("market_social", "market", "vendor"), {"window_glow": (1.0, 0.42, 0.92, 0.96), "accent_glow": (1.0, 0.78, 0.30, 0.94), "body_glow": (0.42, 0.12, 0.44, 0.16), "roof_profile": "market_canopy", "pulse_phase": 0.7}),
        (("electric_plant", "power_plant", "substation", "transformer", "cooling_tower", "tesla_coil", "fusion_core", "transmission_tower", "thermal_storage", "turbine_hall", "generator_hall"), {"window_glow": (1.0, 0.96, 0.34, 0.96), "accent_glow": (0.52, 1.0, 0.20, 0.97), "body_glow": (0.28, 0.32, 0.08, 0.16), "roof_profile": "electric_plant", "pulse_phase": 1.05}),
        (("industrial", "repair", "factory"), {"window_glow": (0.90, 1.0, 0.38, 0.95), "accent_glow": (0.44, 1.0, 0.22, 0.96), "body_glow": (0.24, 0.34, 0.10, 0.18), "roof_profile": "industrial_stacks", "pulse_phase": 1.3}),
        (("harbor_waterfront", "harbor", "water", "dock"), {"window_glow": (0.40, 1.0, 1.0, 0.96), "accent_glow": (0.20, 0.90, 1.0, 0.96), "body_glow": (0.10, 0.30, 0.60, 0.16), "roof_profile": "harbor_mast", "pulse_phase": 2.1}),
        (("archive_matrixcore", "archive", "memory", "research"), {"window_glow": (0.82, 0.58, 1.0, 0.96), "accent_glow": (0.96, 0.42, 1.0, 0.95), "body_glow": (0.24, 0.14, 0.52, 0.18), "roof_profile": "archive_spires", "pulse_phase": 2.8}),
        (("residential", "home", "garden"), {"window_glow": (0.70, 1.0, 0.84, 0.94), "accent_glow": (0.28, 1.0, 0.62, 0.95), "body_glow": (0.10, 0.36, 0.26, 0.16), "roof_profile": "residential_garden", "pulse_phase": 3.4}),
        (("security_checkpoint", "security", "guard", "command"), {"window_glow": (0.72, 1.0, 0.54, 0.95), "accent_glow": (1.0, 0.86, 0.28, 0.96), "body_glow": (0.14, 0.32, 0.14, 0.16), "roof_profile": "security_crenel", "pulse_phase": 4.0}),
        (("education_civic_commons", "education", "civic", "culture"), {"window_glow": (0.66, 0.96, 1.0, 0.95), "accent_glow": (1.0, 0.88, 0.34, 0.95), "body_glow": (0.16, 0.28, 0.44, 0.16), "roof_profile": "civic_dome", "pulse_phase": 4.7}),
        (("glitched_quarantine_restricted", "glitch", "quarantine", "restricted"), {"window_glow": (1.0, 0.56, 0.26, 0.96), "accent_glow": (1.0, 0.24, 0.34, 0.98), "body_glow": (0.40, 0.12, 0.10, 0.18), "roof_profile": "glitch_spikes", "pulse_phase": 5.4}),
    ]
    chosen = None
    for aliases, theme in themes:
        if any(alias in key for alias in aliases):
            chosen = dict(theme)
            break
    if chosen is None:
        chosen = {
            "window_glow": _mix_color(base_color, (0.86, 0.96, 1.0, 0.96), 0.55),
            "accent_glow": _mix_color(base_color, (1.0, 0.78, 0.36, 0.96), 0.45),
            "body_glow": _mix_color(base_color, (0.06, 0.16, 0.22, 0.18), 0.45),
            "roof_profile": "civic_dome",
            "pulse_phase": 0.0,
        }
    chosen["window_glow"] = _mix_color(chosen["window_glow"], base_color, 0.18)
    chosen["accent_glow"] = _mix_color(chosen["accent_glow"], base_color, 0.10)
    chosen["body_glow"] = _mix_color(chosen["body_glow"], base_color, 0.12)
    chosen["side_window_glow"] = _mix_color(chosen["window_glow"], chosen["body_glow"], 0.36)
    return chosen


def _mix_color(a: tuple[float, float, float, float], b: tuple[float, float, float, float], t: float) -> tuple[float, float, float, float]:
    t = max(0.0, min(1.0, float(t)))
    return tuple((float(a[i]) * (1.0 - t)) + (float(b[i]) * t) for i in range(4))


def _palette(town: dict[str, Any]) -> dict[str, tuple[float, float, float, float]]:
    return {
        "grid": (0.08, 0.72, 0.82, 0.28),
        "road": (0.05, 0.95, 1.0, 0.75),
        "portal": (0.95, 0.18, 1.0, 0.9),
        "anchor": (0.95, 0.88, 0.18, 0.86),
        "label": (0.90, 0.96, 1.0, 0.92),
        "civic": (0.30, 0.82, 1.0, 0.72),
        "home": (0.30, 1.0, 0.72, 0.64),
        "market": (1.0, 0.32, 0.92, 0.68),
        "security": (0.42, 1.0, 0.42, 0.70),
        "restricted": (1.0, 0.26, 0.18, 0.72),
        "command": (1.0, 0.82, 0.20, 0.74),
        "future": (0.70, 0.78, 0.88, 0.42),
        "matrixcore": (1.0, 0.18, 0.22, 0.76),
        "industrial": (0.58, 1.0, 0.32, 0.64),
        "transit": (0.28, 0.48, 1.0, 0.68),
        "service": (0.42, 0.98, 0.92, 0.66),
        "garden": (0.32, 1.0, 0.48, 0.58),
        "harbor": (0.12, 0.92, 1.0, 0.68),
        "water": (0.08, 0.42, 1.0, 0.52),
        "dock": (0.20, 0.80, 0.92, 0.66),
        "archive": (0.72, 0.46, 1.0, 0.70),
        "memory": (0.86, 0.36, 1.0, 0.66),
        "research": (0.48, 0.86, 1.0, 0.68),
        "purpose_power": (1.0, 0.95, 0.36, 0.70),
        "purpose_production": (0.60, 1.0, 0.30, 0.70),
        "purpose_logistics": (0.42, 0.74, 1.0, 0.70),
        "purpose_housing": (0.35, 1.0, 0.62, 0.70),
        "purpose_trade": (1.0, 0.32, 0.88, 0.70),
        "purpose_security": (0.46, 1.0, 0.42, 0.72),
        "purpose_water": (0.14, 0.86, 1.0, 0.70),
        "purpose_archive": (0.78, 0.48, 1.0, 0.72),
        "education": (0.48, 0.93, 1.0, 0.72),
        "culture": (1.0, 0.46, 0.95, 0.70),
        "glitch": (1.0, 0.18, 0.28, 0.78),
        "quarantine": (1.0, 0.45, 0.22, 0.74),
    }


def _block_color(block: dict[str, Any], palette: dict[str, tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    tags = set(str(t).lower() for t in block.get("tags", []))
    block_type = str(block.get("type", "")).lower()
    style = str(block.get("style", "")).lower()
    if "glitch" in tags or "quarantine" in tags or "glitch" in style:
        return palette["glitch"]
    if "education" in tags or "school" in tags or "learning" in style:
        return palette["education"]
    if "culture" in tags or "theater" in tags or "culture" in style:
        return palette["culture"]
    if "matrixcore" in tags or "matrixcore" in style:
        return palette["matrixcore"]
    if "electric_plant" in tags or "power" in tags or "substation" in tags or "transformer_yard" in tags or "power_plant" in tags:
        return palette["purpose_power"]
    if "memory" in tags or "memory" in style:
        return palette["memory"]
    if "research" in tags or "simulation" in tags or "research" in style or "sim_lab" in style:
        return palette["research"]
    if "archive" in tags or "archive" in style or "records" in tags:
        return palette["archive"]
    if "water" in tags or "ocean" in tags or "water" in style or "ocean" in style:
        return palette["water"]
    if "dock" in tags or "pier" in tags or "ferry" in tags:
        return palette["dock"]
    if "harbor" in tags or "harbor" in style:
        return palette["harbor"]
    if "future" in tags:
        return palette["future"]
    if "restricted" in tags:
        return palette["restricted"]
    if "command" in tags or "command" in style:
        return palette["command"]
    if "guard" in tags or "security" in style:
        return palette["security"]
    if "market" in tags or "vendor" in tags:
        return palette["market"]
    if "garden" in tags or "park" in tags:
        return palette["garden"]
    if "home" in tags:
        return palette["home"]
    if "repair" in tags or "industrial" in style:
        return palette["industrial"]
    if "clinic" in tags or "service" in tags or "supply" in tags:
        return palette["service"]
    if "transit" in tags:
        return palette["transit"]
    if "portal" in tags or "portal" in block_type:
        return palette["portal"]
    return palette["civic"]


def _required_id(obj: dict[str, Any], label: str) -> str:
    value = str(obj.get("id", "")).strip()
    if not value:
        raise HoloUtopiaTownError(f"{label}: missing id")
    if any(part in value for part in ("/", "\\", "..")):
        raise HoloUtopiaTownError(f"{label}: unsafe id {value!r}")
    return value


def _grid_pair(value: Any, label: str, grid_size: tuple[int, int] | None = None, minimum: int = 0) -> tuple[int, int]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise HoloUtopiaTownError(f"{label}: expected [x, y]")
    try:
        x = int(value[0])
        y = int(value[1])
    except Exception as exc:
        raise HoloUtopiaTownError(f"{label}: expected integer coordinates") from exc
    if x < minimum or y < minimum:
        raise HoloUtopiaTownError(f"{label}: coordinates must be >= {minimum}")
    if grid_size is not None and (x < 0 or y < 0 or x >= grid_size[0] or y >= grid_size[1]):
        raise HoloUtopiaTownError(f"{label}: coordinates {value!r} outside grid {grid_size!r}")
    return x, y


def _pair_float(value: Iterable[float | int], label: str) -> tuple[float, float]:
    try:
        items = list(value)
    except Exception as exc:
        raise HoloUtopiaTownError(f"{label}: expected pair") from exc
    if len(items) != 2:
        raise HoloUtopiaTownError(f"{label}: expected pair")
    try:
        return float(items[0]), float(items[1])
    except Exception as exc:
        raise HoloUtopiaTownError(f"{label}: expected numeric pair") from exc


def _local_pair(value: Any, label: str) -> tuple[float, float]:
    x, y = _pair_float(value, label)
    if x < -0.75 or x > 0.75 or y < -0.75 or y > 0.75:
        raise HoloUtopiaTownError(f"{label}: local offsets should stay inside or near one block, got {value!r}")
    return x, y


def _local_size_pair(value: Any, label: str) -> tuple[float, float]:
    x, y = _pair_float(value, label)
    if x <= 0 or y <= 0 or x > 1.5 or y > 1.5:
        raise HoloUtopiaTownError(f"{label}: local sizes should be > 0 and <= 1.5 blocks, got {value!r}")
    return x, y


def _positive_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise HoloUtopiaTownError(f"{label}: expected positive number") from exc
    if result <= 0:
        raise HoloUtopiaTownError(f"{label}: expected positive number")
    return result


def _assert_unique(values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if not value:
            raise HoloUtopiaTownError(f"{label}: blank id")
        if value in seen:
            raise HoloUtopiaTownError(f"{label}: duplicate id {value!r}")
        seen.add(value)
