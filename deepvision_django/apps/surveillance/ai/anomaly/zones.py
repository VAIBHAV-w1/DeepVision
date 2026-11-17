def resolve_zone_pixel_bounds(x1: float, y1: float, x2: float, y2: float, frame_width: int = None, frame_height: int = None):
    """
    Maps a stored zone rectangle (normalized 0..1 or pixel coords from e.g. 1280x720 / 640x480)
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
        if rx2 > frame_width or by2 > frame_height:
            ref_w, ref_h = (1280.0, 720.0) if (rx2 <= 1280.0 and by2 <= 720.0) else (1920.0, 1080.0)
            return (
                max(0, min(int(frame_width), int(round(lx1 * frame_width / ref_w)))),
                max(0, min(int(frame_height), int(round(ty1 * frame_height / ref_h)))),
                max(0, min(int(frame_width), int(round(rx2 * frame_width / ref_w)))),
                max(0, min(int(frame_height), int(round(by2 * frame_height / ref_h)))),
            )
        return (
            max(0, min(int(frame_width), int(round(lx1)))),
            max(0, min(int(frame_height), int(round(ty1)))),
            max(0, min(int(frame_width), int(round(rx2)))),
            max(0, min(int(frame_height), int(round(by2)))),
        )

    return int(round(lx1)), int(round(ty1)), int(round(rx2)), int(round(by2))


class RestrictedZone:
    """
    Utility class for representing and validating rectangular restricted spatial zones
    and checking if coordinates lie inside them.
    """
    def __init__(self, zone_id, name, x1, y1, x2, y2, enabled=True):
        self.id = zone_id
        self.name = name
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.enabled = enabled

    def is_point_inside(self, x, y, frame_width: int = None, frame_height: int = None):
        """
        Returns True if the point (x, y) is inside the rectangular boundary, False otherwise.
        Automatically scales zone coordinates when video resolution differs from definition space.
        """
        if not self.enabled:
            return False
        zx1, zy1, zx2, zy2 = resolve_zone_pixel_bounds(
            self.x1, self.y1, self.x2, self.y2, frame_width=frame_width, frame_height=frame_height
        )
        return zx1 <= x <= zx2 and zy1 <= y <= zy2
