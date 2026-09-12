"""Convert OSM GeoJSON layers to a local, styled GLB mesh."""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any


DATA_PATH = Path(r"C:\Projects\A3M\data")
OUTPUT_PATH = Path(r"C:\Projects\A3M\model.glb")

# Width and appearance are intentionally driven by the OSM highway tag.
HIGHWAY_STYLE = {
	"motorway": (12.0, (0.12, 0.14, 0.16, 1.0)),
	"trunk": (10.0, (0.16, 0.18, 0.20, 1.0)),
	"primary": (8.0, (0.78, 0.42, 0.12, 1.0)),
	"secondary": (7.0, (0.82, 0.58, 0.18, 1.0)),
	"tertiary": (6.0, (0.68, 0.68, 0.62, 1.0)),
	"residential": (5.5, (0.48, 0.50, 0.48, 1.0)),
	"service": (4.0, (0.36, 0.38, 0.36, 1.0)),
	"pedestrian": (4.0, (0.72, 0.55, 0.34, 1.0)),
	"footway": (2.0, (0.55, 0.40, 0.24, 1.0)),
	"cycleway": (2.5, (0.16, 0.48, 0.38, 1.0)),
}
DEFAULT_STYLE = (5.0, (0.45, 0.45, 0.42, 1.0))
LAYER_STYLE = {
	"building": (0.92, (0.68, 0.43, 0.28, 1.0)),
	"green": (0.12, (0.25, 0.55, 0.32, 1.0)),
	"water": (0.05, (0.19, 0.52, 0.68, 1.0)),
}


def signed_area(points: list[tuple[float, float]]) -> float:
	return 0.5 * sum(
		points[index][0] * points[(index + 1) % len(points)][1]
		- points[(index + 1) % len(points)][0] * points[index][1]
		for index in range(len(points))
	)


def cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
	return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def point_in_triangle(
	point: tuple[float, float], triangle: tuple[tuple[float, float], ...]
) -> bool:
	signs = [cross(triangle[index], triangle[(index + 1) % 3], point) for index in range(3)]
	return not (any(value < -1e-8 for value in signs) and any(value > 1e-8 for value in signs))


def triangulate(polygon: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
	"""Ear-clip a simple ring, returning indices into the original ring."""
	if len(polygon) < 3:
		return []
	indices = list(range(len(polygon)))
	if signed_area(polygon) < 0:
		indices.reverse()
	triangles: list[tuple[int, int, int]] = []
	guard = 0
	while len(indices) > 3 and guard < len(polygon) * len(polygon):
		guard += 1
		ear_found = False
		for position in range(len(indices)):
			previous = indices[position - 1]
			current = indices[position]
			following = indices[(position + 1) % len(indices)]
			if cross(polygon[previous], polygon[current], polygon[following]) <= 1e-8:
				continue
			triangle = (polygon[previous], polygon[current], polygon[following])
			if any(
				point_in_triangle(polygon[index], triangle)
				for index in indices
				if index not in (previous, current, following)
			):
				continue
			triangles.append((previous, current, following))
			indices.pop(position)
			ear_found = True
			break
		if not ear_found:
			return []
	if len(indices) == 3:
		triangles.append(tuple(indices))  # type: ignore[arg-type]
	return triangles


def rings_for_geometry(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
	geometry_type = geometry.get("type")
	coordinates = geometry.get("coordinates", [])
	if geometry_type == "Polygon":
		return [coordinates]
	if geometry_type == "MultiPolygon":
		return coordinates
	return []


def lines_for_geometry(geometry: dict[str, Any]) -> list[list[list[float]]]:
	geometry_type = geometry.get("type")
	coordinates = geometry.get("coordinates", [])
	if geometry_type == "LineString":
		return [coordinates]
	if geometry_type == "MultiLineString":
		return coordinates
	return []


def coordinates_for_geometry(geometry: dict[str, Any]) -> list[list[float]]:
	return [point for polygon in rings_for_geometry(geometry) for ring in polygon for point in ring] + [
		point for line in lines_for_geometry(geometry) for point in line
	]


def make_glb(vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]], materials: list[tuple[float, float, float, float]], groups: list[tuple[int, int, int]]) -> bytes:
	positions = b"".join(struct.pack("<3f", *vertex) for vertex in vertices)
	position_min = [min(vertex[index] for vertex in vertices) for index in range(3)]
	position_max = [max(vertex[index] for vertex in vertices) for index in range(3)]
	flat_indices = [index for triangle in triangles for index in triangle]
	indices_by_material: dict[int, list[int]] = {index: [] for index in range(len(materials))}
	for material_index, first_index, index_count in groups:
		indices_by_material[material_index].extend(flat_indices[first_index:first_index + index_count])

	buffer_views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962}]
	accessors = [{"bufferView": 0, "componentType": 5126, "count": len(vertices), "type": "VEC3", "min": position_min, "max": position_max}]
	primitive_json = []
	binary_parts = [positions]
	for material_index, material_indices in indices_by_material.items():
		if not material_indices:
			continue
		index_bytes = b"".join(struct.pack("<I", index) for index in material_indices)
		byte_offset = sum(len(part) for part in binary_parts)
		binary_parts.append(index_bytes)
		if byte_offset % 4:
			padding = b"\0" * (4 - byte_offset % 4)
			binary_parts.append(padding)
			byte_offset += len(padding)
		view_index = len(buffer_views)
		buffer_views.append({"buffer": 0, "byteOffset": byte_offset, "byteLength": len(index_bytes), "target": 34963})
		accessor_index = len(accessors)
		accessors.append({"bufferView": view_index, "componentType": 5125, "count": len(material_indices), "type": "SCALAR"})
		primitive_json.append({"attributes": {"POSITION": 0}, "indices": accessor_index, "material": material_index, "mode": 4})
	binary = b"".join(binary_parts)
	binary += b"\0" * ((4 - len(binary) % 4) % 4)
	gltf = {
		"asset": {"version": "2.0", "generator": "A3M GeoJSON layer exporter"},
		"scene": 0,
		"scenes": [{"nodes": [0]}],
		"nodes": [{"mesh": 0, "name": "OSM layers", "rotation": [-0.7071068, 0.0, 0.0, 0.7071068]}],
		"meshes": [{"name": "Buildings, green space, highways and water", "primitives": primitive_json}],
		"buffers": [{"byteLength": len(binary)}],
		"bufferViews": buffer_views,
		"accessors": accessors,
		"materials": [
			{"name": f"highway-{index}", "pbrMetallicRoughness": {"baseColorFactor": color, "roughnessFactor": 0.9, "metallicFactor": 0.0}}
			for index, color in enumerate(materials)
		],
	}
	json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
	json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
	return b"glTF" + struct.pack("<II", 2, 12 + 8 + len(json_chunk) + 8 + len(binary)) + struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk + struct.pack("<I4s", len(binary), b"BIN\0") + binary


def convert() -> None:
	layers = {
		name: json.loads((DATA_PATH / f"{name}.geojson").read_text(encoding="utf-8"))
		for name in ("building", "green", "highway", "water")
	}
	features = [feature for data in layers.values() for feature in data.get("features", [])]
	all_coordinates = [
		coordinate
		for feature in features
		for coordinate in coordinates_for_geometry(feature.get("geometry", {}))
	]
	if not all_coordinates:
		raise ValueError("No supported GeoJSON geometry found")
	origin_lon = sum(point[0] for point in all_coordinates) / len(all_coordinates)
	origin_lat = sum(point[1] for point in all_coordinates) / len(all_coordinates)
	meters_per_degree_lon = 111320.0 * math.cos(math.radians(origin_lat))
	meters_per_degree_lat = 110540.0

	vertices: list[tuple[float, float, float]] = []
	triangles: list[tuple[int, int, int]] = []
	materials: list[tuple[float, float, float, float]] = []
	material_ids: dict[str, int] = {}
	groups: list[tuple[int, int, int]] = []

	for layer_name, data in layers.items():
		for feature in data.get("features", []):
			properties = feature.get("properties", {})
			highway = str(properties.get("highway", "other"))
			if layer_name == "highway":
				width, color = HIGHWAY_STYLE.get(highway, DEFAULT_STYLE)
				style_key = f"highway:{highway}"
				base_z = float(properties.get("layer", 0) or 0) * 0.35
				height = 0.12
			else:
				height, color = LAYER_STYLE[layer_name]
				style_key = layer_name
				base_z = 0.02 if layer_name != "building" else 0.04
				width = 3.0
			material_id = material_ids.setdefault(style_key, len(materials))
			if material_id == len(materials):
				materials.append(color)
			for polygon in rings_for_geometry(feature.get("geometry", {})):
				if not polygon:
					continue
				ring = polygon[0]
				points = [
					((point[0] - origin_lon) * meters_per_degree_lon, (point[1] - origin_lat) * meters_per_degree_lat)
					for point in ring
				]
				if len(points) > 1 and points[0] == points[-1]:
					points.pop()
				if len(points) < 3:
					continue
				start_vertex = len(vertices)
				vertices.extend((x, y, base_z) for x, y in points)
				vertices.extend((x, y, base_z + (float(properties.get("building:levels", 1) or 1) * 2.8 if layer_name == "building" else height)) for x, y in points)
				local_triangles = triangulate(points)
				start_index = len(triangles) * 3
				for first, second, third in local_triangles:
					triangles.append((start_vertex + len(points) + first, start_vertex + len(points) + second, start_vertex + len(points) + third))
					triangles.append((start_vertex + third, start_vertex + second, start_vertex + first))
				for index in range(len(points)):
					next_index = (index + 1) % len(points)
					triangles.append((start_vertex + index, start_vertex + next_index, start_vertex + len(points) + next_index))
					triangles.append((start_vertex + index, start_vertex + len(points) + next_index, start_vertex + len(points) + index))
				groups.append((material_id, start_index, (len(triangles) * 3) - start_index))
			for line in lines_for_geometry(feature.get("geometry", {})):
				points = [
					((point[0] - origin_lon) * meters_per_degree_lon, (point[1] - origin_lat) * meters_per_degree_lat)
					for point in line
				]
				for first, second in zip(points, points[1:]):
					dx = second[0] - first[0]
					dy = second[1] - first[1]
					length = math.hypot(dx, dy)
					if length == 0:
						continue
					offset = (dy / length * width / 2, -dx / length * width / 2)
					start_vertex = len(vertices)
					vertices.extend(((first[0] + offset[0], first[1] + offset[1], base_z), (second[0] + offset[0], second[1] + offset[1], base_z), (second[0] - offset[0], second[1] - offset[1], base_z), (first[0] - offset[0], first[1] - offset[1], base_z)))
					start_index = len(triangles) * 3
					triangles.extend(((start_vertex, start_vertex + 1, start_vertex + 2), (start_vertex, start_vertex + 2, start_vertex + 3)))
					groups.append((material_id, start_index, 6))

	OUTPUT_PATH.write_bytes(make_glb(vertices, triangles, materials, groups))
	print(f"Exported {len(features)} features from {len(layers)} layers, {len(vertices)} vertices, and {len(triangles)} triangles to {OUTPUT_PATH}")


if __name__ == "__main__":
	convert()
