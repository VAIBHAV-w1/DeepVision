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

    def is_point_inside(self, x, y):
        """
        Returns True if the point (x, y) is inside the rectangular boundary, False otherwise.
        """
        if not self.enabled:
            return False
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2
