from typing import Any, Dict, List, Optional, Tuple


def resolve_zone_pixel_bounds(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    frame_width: int = None,
    frame_height: int = None,
    ref_width: int = None,
    ref_height: int = None,
):
    """
    Maps a stored zone rectangle (normalized 0..1 or reference coords such as 1280x720)
    cleanly onto the target `(frame_width, frame_height)` video resolution.
    """
    lx1, rx2 = min(float(x1), float(x2)), max(float(x1), float(x2))
    ty1, by2 = min(float(y1), float(y2)), max(float(y1), float(y2))

    if frame_width and frame_height and frame_width > 0 and frame_height > 0:
        if max(lx1, rx2) <= 1.0 and max(ty1, by2) <= 1.0 and (rx2 > 0.0 or by2 > 0.0):
            return (
                int(round(lx1 * frame_width)),
                int(round(ty1 * frame_height)),
                int(round(rx2 * frame_width)),
                int(round(by2 * frame_height)),
            )
        if ref_width and ref_height and ref_width > 0 and ref_height > 0:
            rw = float(ref_width) if rx2 <= float(ref_width) and by2 <= float(ref_height) else 1920.0
            rh = float(ref_height) if rx2 <= float(ref_width) and by2 <= float(ref_height) else 1080.0
            return (
                max(0, min(int(frame_width), int(round(lx1 * frame_width / rw)))),
                max(0, min(int(frame_height), int(round(ty1 * frame_height / rh)))),
                max(0, min(int(frame_width), int(round(rx2 * frame_width / rw)))),
                max(0, min(int(frame_height), int(round(by2 * frame_height / rh)))),
            )
        if rx2 > frame_width or by2 > frame_height:
            rw, rh = (1280.0, 720.0) if (rx2 <= 1280.0 and by2 <= 720.0) else (1920.0, 1080.0)
            return (
                max(0, min(int(frame_width), int(round(lx1 * frame_width / rw)))),
                max(0, min(int(frame_height), int(round(ty1 * frame_height / rh)))),
                max(0, min(int(frame_width), int(round(rx2 * frame_width / rw)))),
                max(0, min(int(frame_height), int(round(by2 * frame_height / rh)))),
            )
        return (
            max(0, min(int(frame_width), int(round(lx1)))),
            max(0, min(int(frame_height), int(round(ty1)))),
            max(0, min(int(frame_width), int(round(rx2)))),
            max(0, min(int(frame_height), int(round(by2)))),
        )

    return int(round(lx1)), int(round(ty1)), int(round(rx2)), int(round(by2))


def resolve_polygon_pixel_points(
    points: Optional[List[Any]],
    x1: float = 0.0,
    y1: float = 0.0,
    x2: float = 0.0,
    y2: float = 0.0,
    frame_width: int = None,
    frame_height: int = None,
    ref_width: int = None,
    ref_height: int = None,
) -> List[Tuple[int, int]]:
    """
    Converts polygon vertices (normalized 0..1 or reference pixel coordinates)
    into integer pixel `(x, y)` tuples on the given frame size.
    Falls back to the 4 corners of the bounding rectangle if `points` is empty.
    """
    if isinstance(points, (list, tuple)) and len(points) >= 3:
        raw_pts: List[Tuple[float, float]] = []
        max_x = 0.0
        max_y = 0.0
        for p in points:
            if isinstance(p, dict):
                fx, fy = float(p.get("x", 0.0)), float(p.get("y", 0.0))
            else:
                fx, fy = float(p[0]), float(p[1])
            raw_pts.append((fx, fy))
            max_x = max(max_x, fx)
            max_y = max(max_y, fy)

        if frame_width and frame_height and frame_width > 0 and frame_height > 0:
            if max_x <= 1.0 and max_y <= 1.0:
                return [
                    (
                        max(0, min(int(frame_width), int(round(fx * frame_width)))),
                        max(0, min(int(frame_height), int(round(fy * frame_height)))),
                    )
                    for fx, fy in raw_pts
                ]
            if ref_width and ref_height and ref_width > 0 and ref_height > 0:
                return [
                    (
                        max(0, min(int(frame_width), int(round(fx * frame_width / float(ref_width))))),
                        max(0, min(int(frame_height), int(round(fy * frame_height / float(ref_height))))),
                    )
                    for fx, fy in raw_pts
                ]
            if max_x > frame_width or max_y > frame_height:
                rw, rh = (1280.0, 720.0) if (max_x <= 1280.0 and max_y <= 720.0) else (1920.0, 1080.0)
                return [
                    (
                        max(0, min(int(frame_width), int(round(fx * frame_width / rw)))),
                        max(0, min(int(frame_height), int(round(fy * frame_height / rh)))),
                    )
                    for fx, fy in raw_pts
                ]
        return [(int(round(fx)), int(round(fy))) for fx, fy in raw_pts]

    zx1, zy1, zx2, zy2 = resolve_zone_pixel_bounds(
        x1,
        y1,
        x2,
        y2,
        frame_width=frame_width,
        frame_height=frame_height,
        ref_width=ref_width,
        ref_height=ref_height,
    )
    return [(zx1, zy1), (zx2, zy1), (zx2, zy2), (zx1, zy2)]


def _point_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float, eps: float = 1e-6) -> bool:
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > max(eps, eps * max(abs(bx - ax), abs(by - ay), 1.0)):
        return False
    return min(ax, bx) - eps <= px <= max(ax, bx) + eps and min(ay, by) - eps <= py <= max(ay, by) + eps


def point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """
    Ray-casting point-in-polygon check (supports convex and concave polygons, inclusive on edges).
    """
    if not polygon or len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    for i in range(n):
        ax, ay = float(polygon[i][0]), float(polygon[i][1])
        bx, by = float(polygon[(i + 1) % n][0]), float(polygon[(i + 1) % n][1])
        if _point_on_segment(x, y, ax, ay, bx, by):
            return True
        if ((ay > y) != (by > y)) and (x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax):
            inside = not inside
    return inside


def get_object_reference_point(obj: Dict[str, Any]) -> Tuple[float, float]:
    """
    Computes the authoritative ground/foot reference point for spatial zone tests.
    Uses bottom-center `( (x1 + x2) / 2, y2 )` when bounding box bounds are present,
    falling back to explicit foot coordinates or `(center_x, center_y)`.
    """
    if "foot_x" in obj and "foot_y" in obj and obj["foot_x"] is not None and obj["foot_y"] is not None:
        return float(obj["foot_x"]), float(obj["foot_y"])
    if "bbox" in obj and isinstance(obj["bbox"], (list, tuple)) and len(obj["bbox"]) >= 4:
        bx1, _, bx2, by2 = obj["bbox"][:4]
        return 0.5 * (float(bx1) + float(bx2)), float(by2)
    if all(k in obj and obj[k] is not None for k in ("x1", "x2", "y2")):
        return 0.5 * (float(obj["x1"]) + float(obj["x2"])), float(obj["y2"])
    return float(obj.get("center_x", 0.0)), float(obj.get("center_y", 0.0))


class RestrictedZone:
    """
    Utility class for representing and validating rectangular and polygon
    restricted spatial zones and checking whether an object's foot point lies inside.
    """

    def __init__(
        self,
        zone_id,
        name,
        x1,
        y1,
        x2,
        y2,
        enabled=True,
        ref_width=None,
        ref_height=None,
        points=None,
        entry_direction="any",
        shape="rectangle",
        cooldown_seconds=None,
        camera_id=None,
        user_id=None,
    ):
        self.id = zone_id
        self.name = name
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.enabled = enabled
        self.ref_width = ref_width
        self.ref_height = ref_height
        self.points = list(points) if isinstance(points, (list, tuple)) and len(points) >= 3 else None
        self.entry_direction = str(entry_direction or "any").strip().lower()
        self.shape = "polygon" if (self.points and shape == "polygon") else (str(shape or "rectangle").strip().lower())
        self.cooldown_seconds = cooldown_seconds
        self.camera_id = camera_id
        self.user_id = user_id

    def get_pixel_polygon(self, frame_width: int = None, frame_height: int = None) -> List[Tuple[int, int]]:
        return resolve_polygon_pixel_points(
            self.points,
            self.x1,
            self.y1,
            self.x2,
            self.y2,
            frame_width=frame_width,
            frame_height=frame_height,
            ref_width=self.ref_width,
            ref_height=self.ref_height,
        )

    def is_point_inside(self, x, y, frame_width: int = None, frame_height: int = None):
        """
        Returns True if `(x, y)` is inside the polygon or rectangular boundary.
        Automatically scales normalized `0..1` or reference coords to `frame_width x frame_height`.
        """
        if not self.enabled:
            return False
        if self.points and len(self.points) >= 3:
            poly = self.get_pixel_polygon(frame_width=frame_width, frame_height=frame_height)
            return point_in_polygon(float(x), float(y), poly)
        zx1, zy1, zx2, zy2 = resolve_zone_pixel_bounds(
            self.x1,
            self.y1,
            self.x2,
            self.y2,
            frame_width=frame_width,
            frame_height=frame_height,
            ref_width=self.ref_width,
            ref_height=self.ref_height,
        )
        return zx1 <= x <= zx2 and zy1 <= y <= zy2
