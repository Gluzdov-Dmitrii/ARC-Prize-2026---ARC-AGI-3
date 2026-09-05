"""ARGALite: Deterministic object-centric perception for ARC-AGI-3."""

from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any

from v10_agent.types import BoundingBox, Centroid, Grid2D


@dataclass
class PlanningObject:
    """Deterministic representation of a detected grid object."""
    id: str
    color: int
    color_histogram: dict[int, int]
    area: int
    bbox: BoundingBox
    centroid: Centroid
    pixels: list[tuple[int, int]]
    is_single_color: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "color": self.color,
            "color_histogram": dict(self.color_histogram),
            "area": self.area,
            "bbox": self.bbox.to_dict(),
            "centroid": self.centroid.to_dict(),
            "pixel_count": len(self.pixels),
            "is_single_color": self.is_single_color,
        }


@dataclass(frozen=True)
class SpatialRelation:
    """Spatial or topological relation between two planning objects."""
    subject_id: str
    relation_type: str  # "touches", "aligned_h", "aligned_v", "contains", "distance"
    target_id: str
    metric_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "subject": self.subject_id,
            "relation": self.relation_type,
            "target": self.target_id,
        }
        if self.metric_value is not None:
            out["value"] = round(self.metric_value, 2)
        return out


@dataclass
class ARGALiteSnapshot:
    """Immutable perception snapshot for a single grid observation."""
    objects: list[PlanningObject] = field(default_factory=list)
    relations: list[SpatialRelation] = field(default_factory=list)
    grid_dims: tuple[int, int] = (0, 0)
    background_color: int = 0

    @property
    def object_ids(self) -> list[str]:
        return [obj.id for obj in self.objects]

    def get_object(self, object_id: str) -> PlanningObject | None:
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid_dims": {"height": self.grid_dims[0], "width": self.grid_dims[1]},
            "background_color": self.background_color,
            "objects": [obj.to_dict() for obj in self.objects],
            "relations": [rel.to_dict() for rel in self.relations],
        }


def detect_background_color(grid: Grid2D) -> int:
    """Determine the background color. Color 0 by default, or most frequent border color."""
    if not grid or not grid[0]:
        return 0

    height = len(grid)
    width = len(grid[0])

    # If color 0 appears anywhere, convention treats 0 (black) as background
    has_zero = any(0 in row for row in grid)
    if has_zero:
        return 0

    # Otherwise inspect border pixels
    border_pixels: list[int] = []
    border_pixels.extend(grid[0])
    if height > 1:
        border_pixels.extend(grid[-1])
    for r in range(1, height - 1):
        border_pixels.append(grid[r][0])
        border_pixels.append(grid[r][-1])

    if border_pixels:
        counter = Counter(border_pixels)
        return counter.most_common(1)[0][0]

    return 0


def segment_connected_components(grid: Grid2D, background_color: int) -> list[list[tuple[int, int]]]:
    """Segment non-background cells of identical color using 4-connectivity."""
    if not grid or not grid[0]:
        return []

    height = len(grid)
    width = len(grid[0])
    visited: set[tuple[int, int]] = set()
    components: list[list[tuple[int, int]]] = []

    for r in range(height):
        for c in range(width):
            color = grid[r][c]
            if color == background_color or (r, c) in visited:
                continue

            # BFS flood fill for monochromatic 4-connected component
            component: list[tuple[int, int]] = []
            queue = deque([(r, c)])
            visited.add((r, c))

            while queue:
                curr_r, curr_c = queue.popleft()
                component.append((curr_r, curr_c))

                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = curr_r + dr, curr_c + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        if (nr, nc) not in visited and grid[nr][nc] == color:
                            visited.add((nr, nc))
                            queue.append((nr, nc))

            components.append(component)

    return components


def extract_spatial_relations(objects: list[PlanningObject]) -> list[SpatialRelation]:
    """Extract pairwise spatial and topological relations between planning objects."""
    relations: list[SpatialRelation] = []
    num_objs = len(objects)

    for i in range(num_objs):
        obj_a = objects[i]
        pix_set_a = set(obj_a.pixels)

        for j in range(i + 1, num_objs):
            obj_b = objects[j]
            pix_set_b = set(obj_b.pixels)

            # 1. Touches (Chebyshev adjacency <= 1)
            touches = False
            for r, c in obj_a.pixels:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if (r + dr, c + dc) in pix_set_b:
                            touches = True
                            break
                    if touches:
                        break
                if touches:
                    break

            if touches:
                relations.append(SpatialRelation(obj_a.id, "touches", obj_b.id))
                relations.append(SpatialRelation(obj_b.id, "touches", obj_a.id))

            # 2. Horizontal alignment (row interval overlap)
            if max(obj_a.bbox.min_row, obj_b.bbox.min_row) <= min(obj_a.bbox.max_row, obj_b.bbox.max_row):
                relations.append(SpatialRelation(obj_a.id, "aligned_h", obj_b.id))
                relations.append(SpatialRelation(obj_b.id, "aligned_h", obj_a.id))

            # 3. Vertical alignment (col interval overlap)
            if max(obj_a.bbox.min_col, obj_b.bbox.min_col) <= min(obj_a.bbox.max_col, obj_b.bbox.max_col):
                relations.append(SpatialRelation(obj_a.id, "aligned_v", obj_b.id))
                relations.append(SpatialRelation(obj_b.id, "aligned_v", obj_a.id))

            # 4. Containment
            if (
                obj_a.bbox.min_row <= obj_b.bbox.min_row
                and obj_a.bbox.max_row >= obj_b.bbox.max_row
                and obj_a.bbox.min_col <= obj_b.bbox.min_col
                and obj_a.bbox.max_col >= obj_b.bbox.max_col
                and obj_a.area > obj_b.area
            ):
                relations.append(SpatialRelation(obj_a.id, "contains", obj_b.id))

            elif (
                obj_b.bbox.min_row <= obj_a.bbox.min_row
                and obj_b.bbox.max_row >= obj_a.bbox.max_row
                and obj_b.bbox.min_col <= obj_a.bbox.min_col
                and obj_b.bbox.max_col >= obj_a.bbox.max_col
                and obj_b.area > obj_a.area
            ):
                relations.append(SpatialRelation(obj_b.id, "contains", obj_a.id))

            # 5. Centroid Distance
            dist = math.hypot(obj_a.centroid.row - obj_b.centroid.row, obj_a.centroid.col - obj_b.centroid.col)
            relations.append(SpatialRelation(obj_a.id, "distance", obj_b.id, metric_value=dist))

    return relations


def extract_arga_snapshot(grid: Grid2D) -> ARGALiteSnapshot:
    """Extract a complete ARGALite perception snapshot from a 2D grid."""
    if not grid or not grid[0]:
        return ARGALiteSnapshot(grid_dims=(0, 0))

    height = len(grid)
    width = len(grid[0])
    bg_color = detect_background_color(grid)
    raw_components = segment_connected_components(grid, bg_color)

    # Sort components deterministically: top-to-bottom, left-to-right, then largest area
    def sort_key(comp: list[tuple[int, int]]) -> tuple[int, int, int, int]:
        min_r = min(r for r, _ in comp)
        min_c = min(c for _, c in comp)
        color = grid[comp[0][0]][comp[0][1]]
        return (min_r, min_c, -len(comp), color)

    raw_components.sort(key=sort_key)

    objects: list[PlanningObject] = []
    for idx, comp in enumerate(raw_components):
        obj_id = f"obj_{idx}"
        rows = [r for r, _ in comp]
        cols = [c for _, c in comp]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)
        area = len(comp)

        color_hist = Counter(grid[r][c] for r, c in comp)
        primary_color = color_hist.most_common(1)[0][0]

        centroid_r = sum(rows) / area
        centroid_c = sum(cols) / area

        objects.append(
            PlanningObject(
                id=obj_id,
                color=primary_color,
                color_histogram=dict(color_hist),
                area=area,
                bbox=BoundingBox(min_row=min_r, min_col=min_c, max_row=max_r, max_col=max_c),
                centroid=Centroid(row=centroid_r, col=centroid_c),
                pixels=sorted(comp),
                is_single_color=(len(color_hist) == 1),
            )
        )

    relations = extract_spatial_relations(objects)

    return ARGALiteSnapshot(
        objects=objects,
        relations=relations,
        grid_dims=(height, width),
        background_color=bg_color,
    )
