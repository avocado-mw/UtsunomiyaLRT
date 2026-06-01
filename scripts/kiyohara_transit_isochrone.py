#!/usr/bin/env python
"""Create 30/60 minute public-transport isochrones to Kiyohara industrial area.

The workflow follows the specification in the project request:

    origin area -> walk X min -> bus stop / conventional rail node
    -> feeder bus / rail Y min -> LRT stop -> LRT Z min -> destination LRT stop

Travel speeds are intentionally simple scenario assumptions:

* LRT: 20 km/h, estimated from cumulative distance through lrt_stops.shp.
* Feeder bus: 20 km/h, estimated along N07 bus route lines when present.
* Waiting: expected wait = average headway / 2; bus wait is rounded to
  8 minutes, LRT wait is rounded to 5 minutes, and conventional rail wait
  is set to 10 minutes.
* Walking: 80 m/min along road lines when the required N13 road meshes are present.

Outputs are written under outputs/kiyohara_isochrone/ and include GeoPackage
layers, shapefiles, CSV diagnostics, and a PNG map.
"""

from __future__ import annotations

import argparse
import heapq
import math
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import networkx as nx
except ImportError:  # pragma: no cover - handled at runtime
    nx = None

gpd = None
plt = None
np = None
pd = None
LineString = None
MultiLineString = None
Point = None
Polygon = None
box = None
unary_union = None


def ensure_geospatial_dependencies() -> None:
    """Import heavy GIS dependencies only when the full analysis is executed."""
    global gpd, plt, np, pd, LineString, MultiLineString, Point, Polygon, box, unary_union
    if gpd is not None:
        return
    try:
        import geopandas as _gpd
        import matplotlib.pyplot as _plt
        import numpy as _np
        import pandas as _pd
        from shapely.geometry import LineString as _LineString
        from shapely.geometry import MultiLineString as _MultiLineString
        from shapely.geometry import Point as _Point
        from shapely.geometry import Polygon as _Polygon
        from shapely.geometry import box as _box
        from shapely.ops import unary_union as _unary_union
    except ImportError as exc:  # pragma: no cover - depends on runtime environment
        raise ImportError(
            "The full isochrone analysis requires geopandas, pandas, numpy, "
            "matplotlib, shapely, and pyogrio/fiona. Install the geospatial "
            "requirements before running analysis cells, e.g. "
            "`pip install geopandas pandas numpy matplotlib shapely pyogrio networkx`."
        ) from exc

    gpd = _gpd
    plt = _plt
    np = _np
    pd = _pd
    LineString = _LineString
    MultiLineString = _MultiLineString
    Point = _Point
    Polygon = _Polygon
    box = _box
    unary_union = _unary_union


CRS_WGS84 = "EPSG:4326"
CRS_JGD2011_GEOG = "EPSG:6668"
CRS_ANALYSIS = "EPSG:6678"

LRT_SPEED_M_PER_MIN = 20_000 / 60
BUS_SPEED_M_PER_MIN = 20_000 / 60
RAIL_SPEED_M_PER_MIN = 40_000 / 60
WALK_SPEED_M_PER_MIN = 80
ROAD_DISTANCE_FACTOR = 1.1666
WALK_CORRIDOR_BUFFER_M = 40
BUS_WAIT_TIME_MIN = 8.0
LRT_WAIT_TIME_MIN = 5.0
RAIL_WAIT_TIME_MIN = 10.0
BUS_TRANSFER_RADIUS_M = 250
TRANSFER_PENALTY_MIN = 0.0
BUS_TARGET_SNAP_MAX_M = 750
RAIL_TARGET_WALK_MAX_M = 1_000

DEFAULT_THRESHOLDS = (30, 60)
DEFAULT_TARGET_STOP_REGEX = r"清原|工業団地"
REQUIRED_ROAD_MESH_IDS = ("5439", "5440", "5539", "5540")
EXPECTED_ROAD_MESH_FILES = {
    "5439": "N13-24_5439.shp",
    "5440": "N13-24-5440.shp",
    "5539": "N13-24-5539.shp",
    "5540": "N13-24-5540.shp",
}

LAYER_PATTERNS = {
    "lrt_stops": [
        "lrt_stops.shp",
        "*lrt*stop*.shp",
        "*lightline*stop*.shp",
        "*ライトライン*停*.shp",
    ],
    "bus_stops": [
        "P11-22_09.shp",
        "P11*.shp",
        "*bus*stop*.shp",
        "*バス停*.shp",
    ],
    "bus_routes": [
        "N07-11_09_GML.shp",
        "N07*.shp",
        "*bus*route*.shp",
        "*バス*路線*.shp",
    ],
    "rail_lines": [
        "N05-25_RailroadSection2.shp",
        "*RailroadSection*.shp",
        "*rail*line*.shp",
        "*鉄道*区間*.shp",
    ],
    "rail_stations": [
        "N05-25_Station2.shp",
        "*Station2.shp",
        "*Station*.shp",
        "*rail*station*.shp",
        "*鉄道*駅*.shp",
    ],
    "roads": [
        "N13-24_5439.shp",
        "N13-24-5439.shp",
        "N13-24_5440.shp",
        "N13-24-5440.shp",
        "N13-24_5539.shp",
        "N13-24-5539.shp",
        "N13-24_5540.shp",
        "N13-24-5540.shp",
        "N13*.shp",
        "*road*.shp",
        "*道路*.shp",
    ],
    "adm2": [
        "gadm41_JPN_2.shp",
        "*JPN*2*.shp",
        "*adm*2*.shp",
    ],
}

NAME_CANDIDATES = {
    "lrt_stops": ["stop_name", "name", "station", "駅名", "停留場名", "N05_011", "S12_001"],
    "bus_stops": ["P11_001", "stop_name", "name", "バス停名"],
    "bus_routes": ["N07_003", "route_name", "name", "路線名"],
    "rail_stations": ["N05_011", "station_name", "name", "駅名"],
}

ORDER_CANDIDATES = [
    "stop_order",
    "order",
    "seq",
    "sequence",
    "station_no",
    "station_id",
    "id",
]


@dataclass
class GraphBundle:
    graph: object
    nodes: gpd.GeoDataFrame
    edges: gpd.GeoDataFrame
    length_weight: str = "length_m"


def log(message: str) -> None:
    print(message, flush=True)


def find_layers(data_dir: Path, key: str) -> list[Path]:
    matches: list[Path] = []
    for pattern in LAYER_PATTERNS[key]:
        matches.extend(sorted(data_dir.rglob(pattern)))

    seen: set[Path] = set()
    unique: list[Path] = []
    for match in matches:
        resolved = match.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(match)
    return unique


def find_layer(data_dir: Path, key: str) -> Path | None:
    matches = find_layers(data_dir, key)
    return matches[0] if matches else None


def shapefile_sidecars_missing(path: Path) -> list[str]:
    required = [".shp", ".shx", ".dbf"]
    return [path.with_suffix(s).name for s in required if not path.with_suffix(s).exists()]


def road_mesh_id(path: Path) -> str | None:
    match = re.search(r"N13-24[-_](\d{4})\.shp$", path.name, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def required_road_mesh_errors(road_paths: list[Path]) -> list[str]:
    by_mesh: dict[str, Path] = {}
    for path in road_paths:
        mesh_id = road_mesh_id(path)
        if mesh_id in REQUIRED_ROAD_MESH_IDS and mesh_id not in by_mesh:
            by_mesh[mesh_id] = path

    errors: list[str] = []
    for mesh_id in REQUIRED_ROAD_MESH_IDS:
        path = by_mesh.get(mesh_id)
        expected_name = EXPECTED_ROAD_MESH_FILES[mesh_id]
        if path is None:
            errors.append(f"roads: missing required N13 mesh {expected_name}")
            continue
        missing = shapefile_sidecars_missing(path)
        if missing:
            errors.append(f"roads: {path} missing {', '.join(missing)}")
    return errors


def validate_required_inputs(layers: dict[str, Path | list[Path] | None]) -> list[str]:
    errors: list[str] = []
    lrt_path = layers.get("lrt_stops")
    if not isinstance(lrt_path, Path):
        errors.append("lrt_stops: no matching .shp")
    else:
        missing = shapefile_sidecars_missing(lrt_path)
        if missing:
            errors.append(f"lrt_stops: missing {', '.join(missing)}")

    for key, label in [("rail_lines", "N05-25_RailroadSection2.shp"), ("rail_stations", "N05-25_Station2.shp")]:
        path = layers.get(key)
        if not isinstance(path, Path):
            errors.append(f"{key}: missing required {label}")
        else:
            missing = shapefile_sidecars_missing(path)
            if missing:
                errors.append(f"{key}: {path} missing {', '.join(missing)}")

    road_paths = layers.get("roads") if isinstance(layers.get("roads"), list) else []
    errors.extend(required_road_mesh_errors(road_paths))
    return errors


def discover_layers(data_dir: Path) -> dict[str, Path | list[Path] | None]:
    layers: dict[str, Path | list[Path] | None] = {}
    for key in LAYER_PATTERNS:
        if key == "roads":
            paths = find_layers(data_dir, key)
            layers[key] = paths
            if not paths:
                log(f"{key:12s}: not found")
            else:
                log(f"{key:12s}: {len(paths)} layer(s)")
                for path in paths:
                    missing = shapefile_sidecars_missing(path)
                    suffix = f" (missing sidecars: {', '.join(missing)})" if missing else ""
                    log(f"{'':12s}  - {path}{suffix}")
        else:
            path = find_layer(data_dir, key)
            layers[key] = path
            if path is None:
                log(f"{key:12s}: not found")
            else:
                missing = shapefile_sidecars_missing(path)
                suffix = f" (missing sidecars: {', '.join(missing)})" if missing else ""
                log(f"{key:12s}: {path}{suffix}")
    return layers


def check_inputs(data_dir: Path) -> bool:
    layers = discover_layers(data_dir)
    input_errors = validate_required_inputs(layers)

    if layers["bus_routes"] is None:
        log("\nWARNING: N07 bus route lines were not found. Y minutes will fall back to straight-line distance.")

    if input_errors:
        log("\nRequired inputs are incomplete:")
        for item in input_errors:
            log(f" - {item}")
        log("\nPlace the complete shapefile sets under data/ before running the analysis.")
        return False

    return True


def read_layer(path: Path | None, default_crs: str = CRS_JGD2011_GEOG) -> gpd.GeoDataFrame | None:
    if path is None:
        return None
    missing = shapefile_sidecars_missing(path)
    if missing:
        raise FileNotFoundError(f"{path} is missing required shapefile sidecars: {', '.join(missing)}")

    last_error: Exception | None = None
    for encoding in ("utf-8", "cp932", "shift_jis"):
        try:
            gdf = gpd.read_file(path, encoding=encoding)
            break
        except Exception as exc:  # pragma: no cover - depends on local data encoding
            last_error = exc
    else:
        assert last_error is not None
        raise last_error

    gdf = gdf[~gdf.geometry.isna()].copy()
    if gdf.empty:
        return gdf.set_crs(default_crs, allow_override=True).to_crs(CRS_ANALYSIS)
    if gdf.crs is None:
        warnings.warn(f"{path.name} has no CRS; assuming {default_crs}.", stacklevel=2)
        gdf = gdf.set_crs(default_crs, allow_override=True)
    return gdf.to_crs(CRS_ANALYSIS)


def read_layers(paths: list[Path] | None, default_crs: str = CRS_JGD2011_GEOG) -> gpd.GeoDataFrame | None:
    if not paths:
        return None
    layers = [read_layer(path, default_crs=default_crs) for path in paths]
    layers = [layer for layer in layers if layer is not None and not layer.empty]
    if not layers:
        return None
    return gpd.GeoDataFrame(pd.concat(layers, ignore_index=True), geometry="geometry", crs=CRS_ANALYSIS)


def first_existing_col(gdf: gpd.GeoDataFrame | None, candidates: list[str]) -> str | None:
    if gdf is None:
        return None
    lower_lookup = {str(col).lower(): col for col in gdf.columns}
    for candidate in candidates:
        if candidate in gdf.columns:
            return candidate
        if candidate.lower() in lower_lookup:
            return lower_lookup[candidate.lower()]
    return None


def clean_name(value: object) -> str:
    return re.sub(r"\s+", "", str(value)).replace("\u3000", "")


def force_points(gdf: gpd.GeoDataFrame, name_col: str | None = None) -> gpd.GeoDataFrame:
    points = gdf.copy()
    points["geometry"] = points.geometry.apply(lambda geom: geom if geom.geom_type == "Point" else geom.representative_point())
    if name_col and name_col in points.columns:
        points["_clean_name"] = points[name_col].map(clean_name)
        points = points.dissolve(by="_clean_name", as_index=False).copy()
        points["geometry"] = points.geometry.apply(lambda geom: geom if geom.geom_type == "Point" else geom.representative_point())
        points[name_col] = points["_clean_name"]
    return points


def explode_lines(gdf: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame | None:
    if gdf is None:
        return None
    lines = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if lines.empty:
        return lines
    return lines.explode(index_parts=False).reset_index(drop=True)


def geom_union(gdf: gpd.GeoDataFrame | None):
    if gdf is None or gdf.empty:
        return None
    try:
        return gdf.geometry.union_all()
    except AttributeError:  # geopandas < 1.0
        return gdf.unary_union


def clip_to_polygon(gdf: gpd.GeoDataFrame | None, polygon: Polygon) -> gpd.GeoDataFrame | None:
    if gdf is None or gdf.empty:
        return gdf
    try:
        return gpd.clip(gdf, gpd.GeoDataFrame(geometry=[polygon], crs=CRS_ANALYSIS))
    except Exception:
        return gdf[gdf.intersects(polygon)].copy()


def order_lrt_stops(lrt_stops: gpd.GeoDataFrame, name_col: str | None) -> gpd.GeoDataFrame:
    stops = lrt_stops.copy().reset_index(drop=True)
    order_col = first_existing_col(stops, ORDER_CANDIDATES)
    if order_col is not None:
        numeric_order = pd.to_numeric(stops[order_col], errors="coerce")
        if numeric_order.notna().sum() >= 2:
            stops["_route_order"] = numeric_order.fillna(numeric_order.max() + 1)
            return stops.sort_values("_route_order").reset_index(drop=True)

    coords = np.column_stack([stops.geometry.x.to_numpy(), stops.geometry.y.to_numpy()])
    centered = coords - coords.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    principal_axis = vt[0]
    stops["_route_order"] = centered @ principal_axis
    return stops.sort_values("_route_order").reset_index(drop=True)


def choose_target_stop(lrt_stops: gpd.GeoDataFrame, name_col: str | None, regex: str) -> int:
    if name_col is not None and name_col in lrt_stops.columns:
        names = lrt_stops[name_col].map(clean_name)
        mask = names.str.contains(regex, regex=True, na=False)
        if mask.any():
            return int(mask[mask].index[0])

    warnings.warn(
        f"No LRT stop name matched {regex!r}; using the easternmost/highest-order stop as destination.",
        stacklevel=2,
    )
    return int(lrt_stops.index[-1])


def add_lrt_times(lrt_stops: gpd.GeoDataFrame, name_col: str | None, target_regex: str) -> gpd.GeoDataFrame:
    ordered = order_lrt_stops(lrt_stops, name_col).reset_index(drop=True)
    target_idx = choose_target_stop(ordered, name_col, target_regex)

    coords = list(ordered.geometry)
    segment_lengths = [0.0]
    for prev, cur in zip(coords[:-1], coords[1:]):
        segment_lengths.append(prev.distance(cur))
    ordered["lrt_segment_m"] = segment_lengths
    ordered["lrt_cum_m"] = np.cumsum(segment_lengths)
    target_cum = float(ordered.loc[target_idx, "lrt_cum_m"])
    ordered["z_lrt_min"] = (ordered["lrt_cum_m"] - target_cum).abs() / LRT_SPEED_M_PER_MIN
    ordered["is_destination_stop"] = False
    ordered.loc[target_idx, "is_destination_stop"] = True
    ordered["access_type"] = "lrt_stop"
    ordered["transfer_stop"] = ordered[name_col].map(clean_name) if name_col else [f"LRT_{i:02d}" for i in ordered.index]
    ordered["bus_min"] = 0.0
    ordered["bus_wait_min"] = 0.0
    ordered["lrt_wait_min"] = np.where(ordered["z_lrt_min"].gt(0), LRT_WAIT_TIME_MIN, 0.0)
    ordered["total_transit_min"] = ordered["z_lrt_min"] + ordered["lrt_wait_min"]
    return ordered


def line_iter(geom) -> Iterable[LineString]:
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString):
        yield from geom.geoms


def build_graph_from_lines(lines: gpd.GeoDataFrame, precision: int = 2) -> GraphBundle:
    if nx is None:
        raise ImportError("networkx is required for network-based isochrones.")
    graph = nx.Graph()
    edge_records = []

    for row_idx, geom in enumerate(lines.geometry):
        for line in line_iter(geom):
            coords = list(line.coords)
            for start, end in zip(coords[:-1], coords[1:]):
                a = (round(start[0], precision), round(start[1], precision))
                b = (round(end[0], precision), round(end[1], precision))
                if a == b:
                    continue
                segment = LineString([a, b])
                length = float(segment.length)
                if length <= 0:
                    continue
                if graph.has_edge(a, b):
                    if length >= graph[a][b]["length_m"]:
                        continue
                graph.add_edge(a, b, length_m=length, geometry=segment, source_row=row_idx)
                edge_records.append({"u": a, "v": b, "length_m": length, "geometry": segment})

    node_records = [{"node": node, "geometry": Point(node)} for node in graph.nodes]
    nodes = gpd.GeoDataFrame(node_records, geometry="geometry", crs=CRS_ANALYSIS)
    edges = gpd.GeoDataFrame(edge_records, geometry="geometry", crs=CRS_ANALYSIS)
    return GraphBundle(graph=graph, nodes=nodes, edges=edges)


def snap_points_to_nodes(points: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame) -> pd.DataFrame:
    if points.empty or nodes.empty:
        return pd.DataFrame(columns=["source_index", "node", "snap_dist_m"])
    pts = points[["geometry"]].copy().reset_index(names="source_index")
    snapped = gpd.sjoin_nearest(pts, nodes[["node", "geometry"]], how="left", distance_col="snap_dist_m")
    snapped = snapped.sort_values(["source_index", "snap_dist_m"]).drop_duplicates("source_index")
    return pd.DataFrame(snapped[["source_index", "node", "snap_dist_m"]])


def dijkstra_with_initial_costs(graph, initial_costs: dict[object, float], cutoff: float | None = None) -> dict[object, float]:
    distances: dict[object, float] = {}
    heap = [(cost, node) for node, cost in initial_costs.items() if math.isfinite(cost)]
    heapq.heapify(heap)
    while heap:
        cost, node = heapq.heappop(heap)
        if node in distances:
            continue
        if cutoff is not None and cost > cutoff:
            continue
        distances[node] = cost
        for nbr, attrs in graph[node].items():
            edge_cost = float(attrs.get("time_min", attrs.get("length_m", 0.0)))
            next_cost = cost + edge_cost
            if nbr not in distances and (cutoff is None or next_cost <= cutoff):
                heapq.heappush(heap, (next_cost, nbr))
    return distances


def dijkstra_with_initial_costs_and_labels(graph, initial_records: dict[object, tuple[float, dict]], cutoff: float | None = None) -> tuple[dict[object, float], dict[object, dict]]:
    distances: dict[object, float] = {}
    labels: dict[object, dict] = {}
    heap = [
        (cost, i, node, label)
        for i, (node, (cost, label)) in enumerate(initial_records.items())
        if math.isfinite(cost)
    ]
    heapq.heapify(heap)
    sequence = len(heap)
    while heap:
        cost, _, node, label = heapq.heappop(heap)
        if node in distances:
            continue
        if cutoff is not None and cost > cutoff:
            continue
        distances[node] = cost
        labels[node] = label
        for nbr, attrs in graph[node].items():
            edge_cost = float(attrs.get("time_min", attrs.get("length_m", 0.0)))
            next_cost = cost + edge_cost
            if nbr not in distances and (cutoff is None or next_cost <= cutoff):
                sequence += 1
                heapq.heappush(heap, (next_cost, sequence, nbr, label))
    return distances, labels


def set_edge_time(graph, speed_m_per_min: float) -> None:
    for _, _, attrs in graph.edges(data=True):
        attrs["time_min"] = float(attrs["length_m"]) / speed_m_per_min


def proxy_points_from_bus_routes(bus_routes: gpd.GeoDataFrame, interval_m: float = 300) -> gpd.GeoDataFrame:
    records = []
    route_name_col = first_existing_col(bus_routes, NAME_CANDIDATES["bus_routes"])
    for idx, row in bus_routes.reset_index(drop=True).iterrows():
        route_name = clean_name(row[route_name_col]) if route_name_col else f"route_{idx:04d}"
        for part in line_iter(row.geometry):
            if part.length == 0:
                continue
            distances = np.arange(0, part.length + interval_m, interval_m)
            for seq, dist in enumerate(distances):
                records.append(
                    {
                        "bus_stop_name": f"{route_name}_proxy_{seq:04d}",
                        "access_type": "bus_route_proxy",
                        "geometry": part.interpolate(min(float(dist), part.length)),
                    }
                )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=CRS_ANALYSIS)


def add_bus_transfer_edges(
    graph,
    nodes: gpd.GeoDataFrame,
    snapped_points: pd.DataFrame,
    radius_m: float = BUS_TRANSFER_RADIUS_M,
    penalty_min: float = TRANSFER_PENALTY_MIN,
) -> int:
    if snapped_points.empty or radius_m <= 0:
        return 0
    transfer_nodes = snapped_points[["node"]].drop_duplicates().merge(nodes, on="node", how="inner")
    transfer_nodes = gpd.GeoDataFrame(transfer_nodes, geometry="geometry", crs=CRS_ANALYSIS)
    if transfer_nodes.empty:
        return 0

    left = gpd.GeoDataFrame(
        transfer_nodes[["node"]].copy(),
        geometry=transfer_nodes.geometry.buffer(radius_m),
        crs=CRS_ANALYSIS,
    )
    right = transfer_nodes[["node", "geometry"]].rename(columns={"node": "node_right"})
    right = gpd.GeoDataFrame(right, geometry="geometry", crs=CRS_ANALYSIS)
    pairs = gpd.sjoin(left, right, how="inner", predicate="intersects")

    added = 0
    seen: set[tuple[object, object]] = set()
    node_geoms = dict(zip(transfer_nodes["node"], transfer_nodes.geometry))
    for _, row in pairs.iterrows():
        a = row["node"]
        b = row["node_right"]
        if a == b:
            continue
        pair = tuple(sorted([a, b]))
        if pair in seen:
            continue
        seen.add(pair)
        pa = node_geoms[a]
        pb = node_geoms[b]
        distance_m = float(pa.distance(pb))
        if distance_m > radius_m:
            continue
        # Physical transfer walking is represented by distance; the separate wait
        # penalty represents boarding the next bus after a bus-to-bus transfer.
        time_min = distance_m / WALK_SPEED_M_PER_MIN + penalty_min + BUS_WAIT_TIME_MIN
        if graph.has_edge(a, b) and float(graph[a][b].get("time_min", math.inf)) <= time_min:
            continue
        graph.add_edge(
            a,
            b,
            length_m=distance_m,
            time_min=time_min,
            geometry=LineString([pa, pb]),
            source_row=-1,
            edge_type="bus_transfer",
        )
        added += 1
    return added


def estimate_bus_access(
    bus_points: gpd.GeoDataFrame,
    bus_routes: gpd.GeoDataFrame | None,
    lrt_with_times: gpd.GeoDataFrame,
    destination_point: gpd.GeoDataFrame,
    max_minutes: float,
) -> gpd.GeoDataFrame:
    bus_points = bus_points.copy().reset_index(drop=True)
    if bus_points.empty:
        return bus_points

    if bus_routes is not None and not bus_routes.empty and nx is not None:
        bus_graph = build_graph_from_lines(bus_routes)
        set_edge_time(bus_graph.graph, BUS_SPEED_M_PER_MIN)

        bus_snap = snap_points_to_nodes(bus_points, bus_graph.nodes)
        transfer_edge_count = add_bus_transfer_edges(bus_graph.graph, bus_graph.nodes, bus_snap)

        lrt_snap = snap_points_to_nodes(lrt_with_times, bus_graph.nodes)
        destination_snap = snap_points_to_nodes(destination_point, bus_graph.nodes)

        initial_records: dict[object, tuple[float, dict]] = {}
        for _, row in lrt_snap.iterrows():
            stop_idx = int(row["source_index"])
            node = row["node"]
            snap_cost = float(row["snap_dist_m"]) / WALK_SPEED_M_PER_MIN
            z_min = float(lrt_with_times.loc[stop_idx, "z_lrt_min"])
            lrt_wait_min = float(lrt_with_times.loc[stop_idx, "lrt_wait_min"])
            label = {
                "target_type": "lrt_transfer",
                "transfer_stop": str(lrt_with_times.loc[stop_idx, "transfer_stop"]),
                "z_lrt_min": z_min,
                "lrt_wait_min": lrt_wait_min,
                "target_snap_dist_m": float(row["snap_dist_m"]),
            }
            cost = z_min + lrt_wait_min + snap_cost
            if node not in initial_records or cost < initial_records[node][0]:
                initial_records[node] = (cost, label)

        for _, row in destination_snap.iterrows():
            node = row["node"]
            snap_dist = float(row["snap_dist_m"])
            if snap_dist > BUS_TARGET_SNAP_MAX_M:
                continue
            snap_cost = snap_dist / WALK_SPEED_M_PER_MIN
            label = {
                "target_type": "direct_bus_destination",
                "transfer_stop": "destination_by_bus",
                "z_lrt_min": 0.0,
                "lrt_wait_min": 0.0,
                "target_snap_dist_m": snap_dist,
            }
            if node not in initial_records or snap_cost < initial_records[node][0]:
                initial_records[node] = (snap_cost, label)

        node_costs, node_labels = dijkstra_with_initial_costs_and_labels(bus_graph.graph, initial_records, cutoff=max_minutes)
        transfer_rows = []
        for _, row in bus_snap.iterrows():
            bus_idx = int(row["source_index"])
            node = row["node"]
            total_min = node_costs.get(node, math.inf)
            if not math.isfinite(total_min):
                continue
            label = node_labels.get(node, {})
            z_min = float(label.get("z_lrt_min", 0.0))
            lrt_wait_min = float(label.get("lrt_wait_min", 0.0))
            bus_total_min = total_min + BUS_WAIT_TIME_MIN
            transfer_rows.append(
                {
                    "source_index": bus_idx,
                    "bus_min": max(bus_total_min - z_min - lrt_wait_min, 0.0),
                    "bus_wait_min": BUS_WAIT_TIME_MIN,
                    "z_lrt_min": z_min,
                    "lrt_wait_min": lrt_wait_min,
                    "total_transit_min": bus_total_min,
                    "transfer_stop": str(label.get("transfer_stop", "unknown")),
                    "target_type": str(label.get("target_type", "unknown")),
                    "network_method": "N07_bus_route_network_with_transfers",
                    "bus_snap_dist_m": float(row["snap_dist_m"]),
                    "target_snap_dist_m": float(label.get("target_snap_dist_m", np.nan)),
                    "transfer_edges": transfer_edge_count,
                }
            )
        estimates = pd.DataFrame(transfer_rows)
        out = bus_points.merge(estimates, left_index=True, right_on="source_index", how="inner")
        return gpd.GeoDataFrame(out.drop(columns=["source_index"]), geometry="geometry", crs=CRS_ANALYSIS)

    lrt_coords = lrt_with_times[["transfer_stop", "z_lrt_min", "lrt_wait_min", "geometry"]].copy()
    lrt_coords["target_type"] = "lrt_transfer"
    destination_fallback = destination_point.copy()
    destination_fallback["transfer_stop"] = "destination_by_bus"
    destination_fallback["z_lrt_min"] = 0.0
    destination_fallback["lrt_wait_min"] = 0.0
    destination_fallback["target_type"] = "direct_bus_destination"
    target_points = pd.concat([lrt_coords, destination_fallback[["transfer_stop", "z_lrt_min", "lrt_wait_min", "target_type", "geometry"]]], ignore_index=True)
    target_points = gpd.GeoDataFrame(target_points, geometry="geometry", crs=CRS_ANALYSIS)
    joined = gpd.sjoin_nearest(
        bus_points.reset_index(names="source_index"),
        target_points,
        how="left",
        distance_col="straight_target_dist_m",
    )
    joined["bus_wait_min"] = BUS_WAIT_TIME_MIN
    joined["bus_min"] = joined["straight_target_dist_m"] * ROAD_DISTANCE_FACTOR / BUS_SPEED_M_PER_MIN + joined["bus_wait_min"]
    joined["total_transit_min"] = joined["bus_min"] + joined["z_lrt_min"] + joined["lrt_wait_min"]
    joined["network_method"] = "straight_line_fallback"
    return gpd.GeoDataFrame(joined, geometry="geometry", crs=CRS_ANALYSIS)



def prepare_access_nodes(
    lrt_with_times: gpd.GeoDataFrame,
    bus_stops: gpd.GeoDataFrame | None,
    bus_routes: gpd.GeoDataFrame | None,
    destination_point: gpd.GeoDataFrame,
    max_minutes: float,
) -> gpd.GeoDataFrame:
    lrt_access = lrt_with_times[
        ["access_type", "transfer_stop", "z_lrt_min", "bus_min", "bus_wait_min", "lrt_wait_min", "total_transit_min", "geometry"]
    ].copy()
    lrt_access["network_method"] = "direct_lrt_stop"

    bus_points = None
    if bus_stops is not None and not bus_stops.empty:
        bus_name_col = first_existing_col(bus_stops, NAME_CANDIDATES["bus_stops"])
        bus_points = force_points(bus_stops, None)
        if bus_name_col:
            bus_points["bus_stop_name"] = bus_points[bus_name_col].map(clean_name)
        else:
            bus_points["bus_stop_name"] = [f"bus_stop_{i:05d}" for i in range(len(bus_points))]
        bus_points["access_type"] = "bus_stop"
    elif bus_routes is not None and not bus_routes.empty:
        bus_points = proxy_points_from_bus_routes(bus_routes)
        warnings.warn(
            "Bus stop point layer was not found; using interpolated points along N07 bus route lines as proxy access nodes.",
            stacklevel=2,
        )

    if bus_points is None or bus_points.empty:
        return lrt_access

    lrt_name_col = first_existing_col(lrt_with_times, NAME_CANDIDATES["lrt_stops"])
    bus_estimates = estimate_bus_access(bus_points, bus_routes, lrt_with_times, destination_point, max_minutes)
    keep_cols = [
        "access_type",
        "bus_stop_name",
        "transfer_stop",
        "bus_min",
        "bus_wait_min",
        "z_lrt_min",
        "lrt_wait_min",
        "total_transit_min",
        "network_method",
        "target_type",
        "geometry",
    ]
    for col in keep_cols:
        if col not in bus_estimates.columns:
            bus_estimates[col] = np.nan
    access_nodes = pd.concat([lrt_access, bus_estimates[keep_cols]], ignore_index=True)
    return gpd.GeoDataFrame(access_nodes, geometry="geometry", crs=CRS_ANALYSIS)


def estimate_rail_access(
    rail_stations: gpd.GeoDataFrame | None,
    rail_lines: gpd.GeoDataFrame | None,
    lrt_with_times: gpd.GeoDataFrame,
    destination_point: gpd.GeoDataFrame,
    max_minutes: float,
) -> gpd.GeoDataFrame:
    if rail_stations is None or rail_lines is None or rail_stations.empty or rail_lines.empty or nx is None:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_ANALYSIS)

    station_name_col = first_existing_col(rail_stations, NAME_CANDIDATES["rail_stations"])
    stations = force_points(rail_stations, None).reset_index(drop=True)
    if station_name_col:
        stations["rail_station_name"] = stations[station_name_col].map(clean_name)
    else:
        stations["rail_station_name"] = [f"rail_station_{i:05d}" for i in range(len(stations))]
    stations["access_type"] = "rail_station"

    rail_graph = build_graph_from_lines(rail_lines)
    set_edge_time(rail_graph.graph, RAIL_SPEED_M_PER_MIN)
    station_snap = snap_points_to_nodes(stations, rail_graph.nodes)
    if station_snap.empty:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_ANALYSIS)

    lrt_targets = lrt_with_times[["transfer_stop", "z_lrt_min", "lrt_wait_min", "geometry"]].copy()
    station_to_lrt = gpd.sjoin_nearest(
        stations.reset_index(names="station_idx"),
        lrt_targets,
        how="left",
        distance_col="rail_lrt_transfer_dist_m",
    )
    station_to_lrt["rail_lrt_transfer_walk_min"] = (
        station_to_lrt["rail_lrt_transfer_dist_m"] * ROAD_DISTANCE_FACTOR / WALK_SPEED_M_PER_MIN
    )

    destination_join = gpd.sjoin_nearest(
        stations.reset_index(names="station_idx"),
        destination_point,
        how="left",
        distance_col="rail_destination_walk_dist_m",
    )
    destination_join["rail_destination_walk_min"] = (
        destination_join["rail_destination_walk_dist_m"] * ROAD_DISTANCE_FACTOR / WALK_SPEED_M_PER_MIN
    )

    initial_records: dict[object, tuple[float, dict]] = {}
    station_snap_by_idx = station_snap.set_index("source_index")
    for _, row in station_to_lrt.iterrows():
        station_idx = int(row["station_idx"])
        if station_idx not in station_snap_by_idx.index:
            continue
        snap_row = station_snap_by_idx.loc[station_idx]
        if isinstance(snap_row, pd.DataFrame):
            snap_row = snap_row.iloc[0]
        node = snap_row["node"]
        snap_cost = float(snap_row["snap_dist_m"]) / WALK_SPEED_M_PER_MIN
        z_min = float(row["z_lrt_min"])
        lrt_wait_min = float(row["lrt_wait_min"])
        transfer_walk_min = float(row["rail_lrt_transfer_walk_min"])
        cost = snap_cost + transfer_walk_min + lrt_wait_min + z_min
        label = {
            "target_type": "rail_to_lrt_transfer",
            "transfer_stop": str(row["transfer_stop"]),
            "z_lrt_min": z_min,
            "lrt_wait_min": lrt_wait_min,
            "rail_lrt_transfer_walk_min": transfer_walk_min,
            "rail_destination_walk_min": 0.0,
        }
        if node not in initial_records or cost < initial_records[node][0]:
            initial_records[node] = (cost, label)

    for _, row in destination_join.iterrows():
        walk_dist = float(row["rail_destination_walk_dist_m"])
        if walk_dist > RAIL_TARGET_WALK_MAX_M:
            continue
        station_idx = int(row["station_idx"])
        if station_idx not in station_snap_by_idx.index:
            continue
        snap_row = station_snap_by_idx.loc[station_idx]
        if isinstance(snap_row, pd.DataFrame):
            snap_row = snap_row.iloc[0]
        node = snap_row["node"]
        snap_cost = float(snap_row["snap_dist_m"]) / WALK_SPEED_M_PER_MIN
        walk_min = float(row["rail_destination_walk_min"])
        cost = snap_cost + walk_min
        label = {
            "target_type": "direct_rail_destination",
            "transfer_stop": "destination_by_rail",
            "z_lrt_min": 0.0,
            "lrt_wait_min": 0.0,
            "rail_lrt_transfer_walk_min": 0.0,
            "rail_destination_walk_min": walk_min,
        }
        if node not in initial_records or cost < initial_records[node][0]:
            initial_records[node] = (cost, label)

    node_costs, node_labels = dijkstra_with_initial_costs_and_labels(rail_graph.graph, initial_records, cutoff=max_minutes)
    records = []
    for _, row in station_snap.iterrows():
        station_idx = int(row["source_index"])
        node = row["node"]
        rail_to_target_min = node_costs.get(node, math.inf)
        if not math.isfinite(rail_to_target_min):
            continue
        label = node_labels.get(node, {})
        source_snap_min = float(row["snap_dist_m"]) / WALK_SPEED_M_PER_MIN
        total_min = RAIL_WAIT_TIME_MIN + source_snap_min + rail_to_target_min
        records.append(
            {
                "access_type": "rail_station",
                "rail_station_name": stations.loc[station_idx, "rail_station_name"],
                "transfer_stop": str(label.get("transfer_stop", "unknown")),
                "target_type": str(label.get("target_type", "unknown")),
                "rail_min": total_min - float(label.get("z_lrt_min", 0.0)) - float(label.get("lrt_wait_min", 0.0)),
                "rail_wait_min": RAIL_WAIT_TIME_MIN,
                "rail_lrt_transfer_walk_min": float(label.get("rail_lrt_transfer_walk_min", 0.0)),
                "rail_destination_walk_min": float(label.get("rail_destination_walk_min", 0.0)),
                "bus_min": 0.0,
                "bus_wait_min": 0.0,
                "z_lrt_min": float(label.get("z_lrt_min", 0.0)),
                "lrt_wait_min": float(label.get("lrt_wait_min", 0.0)),
                "total_transit_min": total_min,
                "network_method": "N05_rail_network_with_lrt_transfer",
                "geometry": stations.loc[station_idx, "geometry"],
            }
        )

    if not records:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=CRS_ANALYSIS)
    return gpd.GeoDataFrame(records, geometry="geometry", crs=CRS_ANALYSIS)


def make_isochrones(
    access_nodes: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    thresholds: list[float],
) -> dict[int, gpd.GeoDataFrame]:
    isochrones = {}
    for threshold in thresholds:
        if roads is not None and not roads.empty and nx is not None:
            isochrones[int(threshold)] = make_road_network_isochrone(access_nodes, roads, threshold)
        else:
            warnings.warn(
                "Road network layer or networkx is unavailable; using fallback walking buffers for X minutes.",
                stacklevel=2,
            )
            isochrones[int(threshold)] = make_fallback_isochrone(access_nodes, threshold)
    return isochrones


def make_road_network_isochrone(
    access_nodes: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    threshold_min: float,
) -> gpd.GeoDataFrame:
    eligible = access_nodes[access_nodes["total_transit_min"] <= threshold_min].copy()
    if eligible.empty:
        return gpd.GeoDataFrame({"threshold_min": [threshold_min], "method": ["road_network"], "geometry": [Polygon()]}, crs=CRS_ANALYSIS)

    road_graph = build_graph_from_lines(roads)
    set_edge_time(road_graph.graph, WALK_SPEED_M_PER_MIN)
    snapped = snap_points_to_nodes(eligible, road_graph.nodes)
    initial = {}
    for _, row in snapped.iterrows():
        source_idx = int(row["source_index"])
        node = row["node"]
        transit_min = float(eligible.loc[source_idx, "total_transit_min"])
        if node not in initial or transit_min < initial[node]:
            initial[node] = transit_min

    node_costs = dijkstra_with_initial_costs(road_graph.graph, initial, cutoff=threshold_min)
    reachable_nodes = set(node_costs)

    reachable_edges = []
    for u, v, attrs in road_graph.graph.edges(data=True):
        if u in reachable_nodes or v in reachable_nodes:
            reachable_edges.append(attrs["geometry"])

    if not reachable_edges:
        geom = unary_union(eligible.geometry.buffer(WALK_CORRIDOR_BUFFER_M))
    else:
        geom = unary_union(gpd.GeoSeries(reachable_edges, crs=CRS_ANALYSIS).buffer(WALK_CORRIDOR_BUFFER_M))
    return gpd.GeoDataFrame(
        {
            "threshold_min": [threshold_min],
            "method": ["road_network"],
            "access_nodes": [len(eligible)],
            "geometry": [geom],
        },
        crs=CRS_ANALYSIS,
    )


def make_fallback_isochrone(access_nodes: gpd.GeoDataFrame, threshold_min: float) -> gpd.GeoDataFrame:
    eligible = access_nodes[access_nodes["total_transit_min"] <= threshold_min].copy()
    if eligible.empty:
        geom = Polygon()
    else:
        remaining = threshold_min - eligible["total_transit_min"]
        radii = (remaining * WALK_SPEED_M_PER_MIN / ROAD_DISTANCE_FACTOR).clip(lower=0)
        geom = unary_union([geom.buffer(radius) for geom, radius in zip(eligible.geometry, radii)])
    return gpd.GeoDataFrame(
        {
            "threshold_min": [threshold_min],
            "method": ["walking_buffer_fallback"],
            "access_nodes": [len(eligible)],
            "geometry": [geom],
        },
        crs=CRS_ANALYSIS,
    )


def write_outputs(
    out_dir: Path,
    access_nodes_no_train: gpd.GeoDataFrame,
    access_nodes_with_train: gpd.GeoDataFrame,
    rail_access_nodes: gpd.GeoDataFrame,
    lrt_with_times: gpd.GeoDataFrame,
    isochrones_no_train: dict[int, gpd.GeoDataFrame],
    isochrones_with_train: dict[int, gpd.GeoDataFrame],
    bus_routes: gpd.GeoDataFrame | None,
    rail_lines: gpd.GeoDataFrame | None,
    roads: gpd.GeoDataFrame | None,
) -> None:
    shp_dir = out_dir / "shapefiles"
    table_dir = out_dir / "tables"
    fig_dir = out_dir / "figures"
    for directory in [out_dir, shp_dir, table_dir, fig_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    gpkg = out_dir / "kiyohara_transit_isochrones.gpkg"
    if gpkg.exists():
        gpkg.unlink()

    access_nodes_no_train.to_file(gpkg, layer="access_nodes", driver="GPKG")
    access_nodes_with_train.to_file(gpkg, layer="access_nodes_with_train", driver="GPKG")
    if rail_access_nodes is not None and not rail_access_nodes.empty:
        rail_access_nodes.to_file(gpkg, layer="rail_access_nodes", driver="GPKG")
    lrt_with_times.to_file(gpkg, layer="lrt_travel_times", driver="GPKG")
    access_nodes_no_train.drop(columns="geometry").to_csv(table_dir / "kiyohara_transit_access_nodes.csv", index=False)
    access_nodes_with_train.drop(columns="geometry").to_csv(table_dir / "kiyohara_transit_access_nodes_with_train.csv", index=False)
    if rail_access_nodes is not None and not rail_access_nodes.empty:
        rail_access_nodes.drop(columns="geometry").to_csv(table_dir / "kiyohara_rail_access_nodes.csv", index=False)
    lrt_with_times.drop(columns="geometry").to_csv(table_dir / "kiyohara_lrt_travel_times.csv", index=False)

    for threshold, layer in isochrones_no_train.items():
        layer.to_file(gpkg, layer=f"isochrone_{threshold}min", driver="GPKG")
        layer.to_file(shp_dir / f"kiyohara_isochrone_{threshold}min.shp", encoding="utf-8")
    for threshold, layer in isochrones_with_train.items():
        layer.to_file(gpkg, layer=f"isochrone_with_train_{threshold}min", driver="GPKG")
        layer.to_file(shp_dir / f"kiyohara_isochrone_with_train_{threshold}min.shp", encoding="utf-8")

    plot_isochrones(
        fig_dir / "kiyohara_transit_isochrones.png",
        access_nodes_no_train,
        isochrones_no_train,
        bus_routes,
        roads,
    )
    plot_isochrone_scenarios(
        fig_dir / "kiyohara_transit_isochrones_train_comparison.png",
        isochrones_no_train,
        isochrones_with_train,
        access_nodes_with_train,
        rail_lines,
        roads,
    )
    log(f"\nWrote outputs to {out_dir}")


def plot_isochrones(
    fig_path: Path,
    access_nodes: gpd.GeoDataFrame,
    isochrones: dict[int, gpd.GeoDataFrame],
    bus_routes: gpd.GeoDataFrame | None,
    roads: gpd.GeoDataFrame | None,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 10))
    if roads is not None and not roads.empty:
        roads.plot(ax=ax, color="#d0d0d0", linewidth=0.2)
    if bus_routes is not None and not bus_routes.empty:
        bus_routes.plot(ax=ax, color="#7f7f7f", linewidth=0.5, alpha=0.5)

    colors = {60: "#9ecae1", 30: "#3182bd"}
    for threshold in sorted(isochrones.keys(), reverse=True):
        isochrones[threshold].plot(
            ax=ax,
            color=colors.get(threshold, "#9ecae1"),
            edgecolor="#08519c",
            alpha=0.35 if threshold == 60 else 0.55,
            linewidth=0.8,
            label=f"{threshold} min",
        )

    access_nodes[access_nodes["access_type"].eq("lrt_stop")].plot(ax=ax, color="#de2d26", markersize=18, label="LRT stops")
    access_nodes[~access_nodes["access_type"].eq("lrt_stop")].plot(ax=ax, color="#31a354", markersize=3, alpha=0.5, label="bus access")
    ax.set_axis_off()
    ax.set_title("Kiyohara industrial-area public-transport isochrones")
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(fig_path, dpi=200)
    plt.close(fig)


def plot_isochrone_scenarios(
    fig_path: Path,
    isochrones_no_train: dict[int, gpd.GeoDataFrame],
    isochrones_with_train: dict[int, gpd.GeoDataFrame],
    access_nodes_with_train: gpd.GeoDataFrame,
    rail_lines: gpd.GeoDataFrame | None,
    roads: gpd.GeoDataFrame | None,
) -> None:
    thresholds = sorted(isochrones_with_train.keys())
    fig, axes = plt.subplots(1, len(thresholds), figsize=(7 * len(thresholds), 7))
    if len(thresholds) == 1:
        axes = [axes]
    for ax, threshold in zip(axes, thresholds):
        if roads is not None and not roads.empty:
            roads.plot(ax=ax, color="#eeeeee", linewidth=0.15)
        if rail_lines is not None and not rail_lines.empty:
            rail_lines.plot(ax=ax, color="#636363", linewidth=0.8, alpha=0.7)
        isochrones_with_train[threshold].plot(
            ax=ax,
            color="#9ecae1",
            edgecolor="#08519c",
            linewidth=1.0,
            alpha=0.45,
            label="With train",
        )
        isochrones_no_train[threshold].plot(
            ax=ax,
            color="#fdae6b",
            edgecolor="#e6550d",
            linewidth=1.0,
            alpha=0.45,
            label="No train",
        )
        rail_nodes = access_nodes_with_train[access_nodes_with_train["access_type"].eq("rail_station")]
        if not rail_nodes.empty:
            rail_nodes.plot(ax=ax, color="#54278f", markersize=10, alpha=0.7)
        ax.set_title(f"{threshold} minutes")
        ax.set_axis_off()
        ax.set_aspect("equal")
    axes[0].legend(loc="lower left")
    fig.suptitle("Kiyohara isochrones: no-train vs with-train")
    fig.tight_layout()
    fig.savefig(fig_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def run_analysis(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir)
    max_threshold = max(args.thresholds)

    if args.check_inputs:
        return 0 if check_inputs(data_dir) else 2

    ensure_geospatial_dependencies()
    layers = discover_layers(data_dir)
    input_errors = validate_required_inputs(layers)
    if input_errors:
        formatted = "\n - ".join(input_errors)
        raise FileNotFoundError(f"Required inputs are incomplete:\n - {formatted}")

    lrt_stops = read_layer(layers["lrt_stops"])
    bus_stops = read_layer(layers["bus_stops"]) if layers["bus_stops"] else None
    bus_routes = explode_lines(read_layer(layers["bus_routes"])) if layers["bus_routes"] else None
    rail_lines = explode_lines(read_layer(layers["rail_lines"])) if layers["rail_lines"] else None
    rail_stations = read_layer(layers["rail_stations"]) if layers["rail_stations"] else None

    lrt_name_col = first_existing_col(lrt_stops, NAME_CANDIDATES["lrt_stops"])
    lrt_stops = force_points(lrt_stops, lrt_name_col)
    lrt_name_col = first_existing_col(lrt_stops, NAME_CANDIDATES["lrt_stops"])
    lrt_with_times = add_lrt_times(lrt_stops, lrt_name_col, args.target_stop_regex)
    destination = lrt_with_times[lrt_with_times["is_destination_stop"]].iloc[0]
    log(f"\nDestination LRT stop: {destination['transfer_stop']}")

    analysis_radius_m = max_threshold * BUS_SPEED_M_PER_MIN + max_threshold * WALK_SPEED_M_PER_MIN + 5_000
    analysis_area = destination.geometry.buffer(analysis_radius_m).envelope
    bus_stops = clip_to_polygon(bus_stops, analysis_area)
    bus_routes = clip_to_polygon(bus_routes, analysis_area)
    rail_lines = clip_to_polygon(rail_lines, analysis_area)
    rail_stations = clip_to_polygon(rail_stations, analysis_area)

    road_paths = layers["roads"] if isinstance(layers["roads"], list) else []
    roads = read_layers(road_paths)
    roads = explode_lines(roads)
    roads = clip_to_polygon(roads, analysis_area) if roads is not None else None

    destination_point = gpd.GeoDataFrame(
        {"target_type": ["destination"], "geometry": [destination.geometry]},
        geometry="geometry",
        crs=CRS_ANALYSIS,
    )
    access_nodes_no_train = prepare_access_nodes(lrt_with_times, bus_stops, bus_routes, destination_point, max_threshold)
    rail_access_nodes = estimate_rail_access(rail_stations, rail_lines, lrt_with_times, destination_point, max_threshold)
    access_nodes_with_train = pd.concat([access_nodes_no_train, rail_access_nodes], ignore_index=True)
    access_nodes_with_train = gpd.GeoDataFrame(access_nodes_with_train, geometry="geometry", crs=CRS_ANALYSIS)

    numeric_cols = [
        "total_transit_min",
        "bus_min",
        "bus_wait_min",
        "rail_min",
        "rail_wait_min",
        "rail_lrt_transfer_walk_min",
        "rail_destination_walk_min",
        "z_lrt_min",
        "lrt_wait_min",
    ]
    access_nodes_no_train = access_nodes_no_train[access_nodes_no_train["total_transit_min"].le(max_threshold)].copy()
    access_nodes_with_train = access_nodes_with_train[access_nodes_with_train["total_transit_min"].le(max_threshold)].copy()
    rail_access_nodes = rail_access_nodes[rail_access_nodes["total_transit_min"].le(max_threshold)].copy() if not rail_access_nodes.empty else rail_access_nodes
    for frame in [access_nodes_no_train, access_nodes_with_train, rail_access_nodes]:
        if frame is None or frame.empty:
            continue
        for col in numeric_cols:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce").round(3)

    if access_nodes_no_train.empty:
        raise RuntimeError("No no-train transit access nodes are reachable within the requested thresholds.")
    if access_nodes_with_train.empty:
        raise RuntimeError("No with-train transit access nodes are reachable within the requested thresholds.")

    isochrones_no_train = make_isochrones(access_nodes_no_train, roads, args.thresholds)
    isochrones_with_train = make_isochrones(access_nodes_with_train, roads, args.thresholds)

    write_outputs(
        out_dir,
        access_nodes_no_train,
        access_nodes_with_train,
        rail_access_nodes,
        lrt_with_times,
        isochrones_no_train,
        isochrones_with_train,
        bus_routes,
        rail_lines,
        roads,
    )
    for scenario, layers_by_threshold in [("no-train", isochrones_no_train), ("with-train", isochrones_with_train)]:
        for threshold, gdf in layers_by_threshold.items():
            area_km2 = float(gdf.to_crs(CRS_ANALYSIS).area.sum()) / 1_000_000
            log(f"{threshold:>2} min {scenario} isochrone area: {area_km2:,.2f} km2 ({gdf.iloc[0]['method']})")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Directory containing shapefiles.")
    parser.add_argument("--output-dir", default="outputs/kiyohara_isochrone", help="Output directory.")
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=list(DEFAULT_THRESHOLDS),
        help="Isochrone thresholds in minutes.",
    )
    parser.add_argument(
        "--target-stop-regex",
        default=DEFAULT_TARGET_STOP_REGEX,
        help="Regex used to select the destination LRT stop.",
    )
    parser.add_argument("--check-inputs", action="store_true", help="Only report discovered inputs and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_analysis(args)
    except Exception as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
