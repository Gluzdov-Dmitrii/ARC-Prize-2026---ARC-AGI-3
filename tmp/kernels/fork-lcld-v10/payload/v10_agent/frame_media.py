"""Visual Channel Media generation: Pure Pillow rendering with pure-Python PNG fallback."""

from __future__ import annotations

import io
import struct
import zlib
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False
    Image = None
    ImageDraw = None
    ImageFont = None

from v10_agent.planning_set import PlanningSet
from v10_agent.types import Grid2D

# Standard ARC 10-Color Palette
ARC_COLOR_MAP: dict[int, tuple[int, int, int]] = {
    0: (0, 0, 0),        # 0: Black
    1: (30, 136, 229),   # 1: Blue
    2: (211, 47, 47),    # 2: Red
    3: (56, 142, 60),    # 3: Green
    4: (251, 192, 45),   # 4: Yellow
    5: (117, 117, 117),  # 5: Grey
    6: (194, 24, 91),    # 6: Magenta
    7: (245, 124, 0),    # 7: Orange
    8: (0, 172, 193),    # 8: Light Blue
    9: (136, 14, 79),    # 9: Maroon
}

GRID_LINE_COLOR = (45, 45, 45)


def _encode_png(width: int, height: int, rgb_bytes: bytes) -> bytes:
    """Encode raw 24-bit RGB scanlines to standard PNG format without third-party dependencies."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        content = tag + data
        crc = zlib.crc32(content) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + content + struct.pack(">I", crc)

    stride = width * 3
    raw_scanlines = b"".join(
        b"\x00" + rgb_bytes[i * stride : (i + 1) * stride]
        for i in range(height)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw_scanlines, level=6))
        + _chunk(b"IEND", b"")
    )


def _render_grid_pure(grid: Grid2D, scale: int = 20) -> bytes:
    """Pure-Python standard-library grid-to-PNG renderer."""
    if not grid or not grid[0]:
        return _encode_png(32, 32, bytes(32 * 32 * 3))
    height = len(grid)
    width = len(grid[0])
    img_w = width * scale
    img_h = height * scale
    buf = bytearray(img_w * img_h * 3)

    for r in range(height):
        for c in range(width):
            color = ARC_COLOR_MAP.get(grid[r][c], (0, 0, 0))
            for py in range(r * scale, (r + 1) * scale):
                for px in range(c * scale, (c + 1) * scale):
                    idx = (py * img_w + px) * 3
                    if py == r * scale or py == (r + 1) * scale - 1 or px == c * scale or px == (c + 1) * scale - 1:
                        buf[idx : idx + 3] = GRID_LINE_COLOR
                    else:
                        buf[idx : idx + 3] = color

    return _encode_png(img_w, img_h, bytes(buf))


def _render_annotated_pure(grid: Grid2D, planning_set: PlanningSet, scale: int = 24) -> bytes:
    """Pure-Python standard-library annotated frame-to-PNG renderer."""
    if not grid or not grid[0]:
        return _encode_png(64, 64, bytes(64 * 64 * 3))
    height = len(grid)
    width = len(grid[0])
    img_w = width * scale
    img_h = height * scale
    buf = bytearray(img_w * img_h * 3)

    def set_px(x: int, y: int, color: tuple[int, int, int]):
        if 0 <= x < img_w and 0 <= y < img_h:
            idx = (y * img_w + x) * 3
            buf[idx : idx + 3] = color

    def draw_box(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], width: int = 2):
        for w in range(width):
            for x in range(x0 + w, x1 - w + 1):
                set_px(x, y0 + w, color)
                set_px(x, y1 - w, color)
            for y in range(y0 + w, y1 - w + 1):
                set_px(x0 + w, y, color)
                set_px(x1 - w, y, color)

    # 1. Base grid drawing
    for r in range(height):
        for c in range(width):
            color = ARC_COLOR_MAP.get(grid[r][c], (0, 0, 0))
            for py in range(r * scale, (r + 1) * scale):
                for px in range(c * scale, (c + 1) * scale):
                    idx = (py * img_w + px) * 3
                    if py == r * scale or py == (r + 1) * scale - 1 or px == c * scale or px == (c + 1) * scale - 1:
                        buf[idx : idx + 3] = GRID_LINE_COLOR
                    else:
                        buf[idx : idx + 3] = color

    # 2. Annotate Planning Objects (bounding boxes and crosshairs)
    bbox_colors = [
        (255, 255, 255),  # White
        (0, 255, 255),    # Cyan
        (255, 255, 0),    # Yellow
        (255, 0, 255),    # Magenta
        (0, 255, 0),      # Lime
    ]

    for idx, obj in enumerate(planning_set.objects):
        outline_color = bbox_colors[idx % len(bbox_colors)]
        bx0 = obj.bbox.min_col * scale
        by0 = obj.bbox.min_row * scale
        bx1 = (obj.bbox.max_col + 1) * scale - 1
        by1 = (obj.bbox.max_row + 1) * scale - 1

        draw_box(bx0, by0, bx1, by1, outline_color, width=2)

        # Centroid crosshair
        cx = int(round(obj.centroid.col * scale + scale / 2))
        cy = int(round(obj.centroid.row * scale + scale / 2))
        arm = max(2, scale // 4)
        for d in range(-arm, arm + 1):
            set_px(cx + d, cy, outline_color)
            set_px(cx, cy + d, outline_color)

    return _encode_png(img_w, img_h, bytes(buf))


def render_grid_png(grid: Grid2D, scale: int = 20) -> bytes:
    """Render a clean 2D ARC grid to PNG bytes."""
    if _HAS_PIL and Image is not None and ImageDraw is not None:
        try:
            if not grid or not grid[0]:
                img = Image.new("RGB", (32, 32), color=(0, 0, 0))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()

            height = len(grid)
            width = len(grid[0])
            img_w = width * scale
            img_h = height * scale

            img = Image.new("RGB", (img_w, img_h), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)

            for r in range(height):
                for c in range(width):
                    color_idx = grid[r][c]
                    rgb = ARC_COLOR_MAP.get(color_idx, (0, 0, 0))
                    x0 = c * scale
                    y0 = r * scale
                    x1 = x0 + scale - 1
                    y1 = y0 + scale - 1
                    draw.rectangle([x0, y0, x1, y1], fill=rgb, outline=GRID_LINE_COLOR)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            pass
    return _render_grid_pure(grid, scale)


def render_annotated_frame_png(
    grid: Grid2D,
    planning_set: PlanningSet,
    scale: int = 24,
) -> bytes:
    """Render an annotated ARC frame highlighting planning objects with aliases and bounding boxes."""
    if _HAS_PIL and Image is not None and ImageDraw is not None and ImageFont is not None:
        try:
            if not grid or not grid[0]:
                img = Image.new("RGB", (64, 64), color=(0, 0, 0))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()

            height = len(grid)
            width = len(grid[0])
            img_w = width * scale
            img_h = height * scale

            img = Image.new("RGB", (img_w, img_h), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)

            # 1. Base grid drawing
            for r in range(height):
                for c in range(width):
                    color_idx = grid[r][c]
                    rgb = ARC_COLOR_MAP.get(color_idx, (0, 0, 0))
                    x0 = c * scale
                    y0 = r * scale
                    x1 = x0 + scale - 1
                    y1 = y0 + scale - 1
                    draw.rectangle([x0, y0, x1, y1], fill=rgb, outline=GRID_LINE_COLOR)

            # Use default bitmap font
            font = ImageFont.load_default()

            # 2. Annotate Planning Objects (bounding boxes and alias badges)
            bbox_colors = [
                (255, 255, 255),  # White
                (0, 255, 255),    # Cyan
                (255, 255, 0),    # Yellow
                (255, 0, 255),    # Magenta
                (0, 255, 0),      # Lime
            ]

            for idx, obj in enumerate(planning_set.objects):
                alias = planning_set.object_real_to_alias.get(obj.id, obj.id)
                outline_color = bbox_colors[idx % len(bbox_colors)]

                # Bounding box
                bx0 = obj.bbox.min_col * scale
                by0 = obj.bbox.min_row * scale
                bx1 = (obj.bbox.max_col + 1) * scale - 1
                by1 = (obj.bbox.max_row + 1) * scale - 1

                draw.rectangle([bx0, by0, bx1, by1], outline=outline_color, width=2)

                # Centroid crosshair
                cx = int(round(obj.centroid.col * scale + scale / 2))
                cy = int(round(obj.centroid.row * scale + scale / 2))
                arm = max(2, scale // 4)
                draw.line([cx - arm, cy, cx + arm, cy], fill=outline_color, width=2)
                draw.line([cx, cy - arm, cx, cy + arm], fill=outline_color, width=2)

                # Alias label badge
                badge_w = max(14, len(alias) * 8 + 4)
                badge_h = 12
                badge_x0 = bx0
                badge_y0 = max(0, by0 - badge_h)
                badge_x1 = badge_x0 + badge_w
                badge_y1 = badge_y0 + badge_h

                draw.rectangle([badge_x0, badge_y0, badge_x1, badge_y1], fill=(0, 0, 0), outline=outline_color)
                draw.text((badge_x0 + 2, badge_y0 + 1), alias, fill=outline_color, font=font)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            pass
    return _render_annotated_pure(grid, planning_set, scale)
