import math

class TrackHistoryManager:
    """
    Manages temporal track histories separately for each track_id.
    Maintains memory-bounded position history, timestamps, and calculates center
    positions, frame-to-frame distances, stationary durations, and loitering states.
    """
    def __init__(self):
        # Stream-scoped transient storage mapping track_id -> track_data dict
        self.tracks = {}

    def update(self, track_id, x1, y1, x2, y2, timestamp, config):
        """
        Updates the track history for a specific track ID with its bounding box coordinates
        and the current timestamp. Updates stationary and loitering timers using config parameters.
        """
        # Calculate center point coordinates
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0

        # Retrieve configuration values
        max_history = config.get("MAX_HISTORY_LENGTH", 30)
        stat_dist_thresh = config.get("STATIONARY_DISTANCE_THRESHOLD", 15.0)
        loiter_radius = config.get("LOITERING_RADIUS", 80.0)

        # 1. Initialize track history if track_id is new
        if track_id not in self.tracks:
            self.tracks[track_id] = {
                "positions": [(center_x, center_y)],
                "timestamps": [timestamp],
                "last_seen": timestamp,
                "stationary_start_time": timestamp,
                "stationary_duration": 0.0,
                "initial_loitering_position": (center_x, center_y),
                "loitering_start_time": timestamp,
                "loitering_duration": 0.0
            }
            return self.tracks[track_id]

        track = self.tracks[track_id]
        
        # 2. Append new position and timestamp
        track["positions"].append((center_x, center_y))
        track["timestamps"].append(timestamp)
        track["last_seen"] = timestamp

        # Enforce memory-bounded history length
        if len(track["positions"]) > max_history:
            track["positions"].pop(0)
            track["timestamps"].pop(0)

        # 3. Calculate stationary duration based on frame-to-frame center drift distance
        prev_pos = track["positions"][-2] if len(track["positions"]) > 1 else (center_x, center_y)
        dist = math.sqrt((center_x - prev_pos[0]) ** 2 + (center_y - prev_pos[1]) ** 2)

        if dist <= stat_dist_thresh:
            if track["stationary_start_time"] is None:
                track["stationary_start_time"] = timestamp
            track["stationary_duration"] = timestamp - track["stationary_start_time"]
        else:
            track["stationary_start_time"] = timestamp
            track["stationary_duration"] = 0.0

        # 4. Calculate loitering duration based on spatial radius displacement
        loiter_init = track["initial_loitering_position"]
        dist_from_init = math.sqrt((center_x - loiter_init[0]) ** 2 + (center_y - loiter_init[1]) ** 2)

        if dist_from_init <= loiter_radius:
            if track["loitering_start_time"] is None:
                track["loitering_start_time"] = timestamp
            track["loitering_duration"] = timestamp - track["loitering_start_time"]
        else:
            track["initial_loitering_position"] = (center_x, center_y)
            track["loitering_start_time"] = timestamp
            track["loitering_duration"] = 0.0

        return track

    def clean_stale_tracks(self, current_timestamp, config):
        """
        Removes any track histories that have not been updated for longer than
        TRACK_TIMEOUT_SECONDS to bound memory consumption.
        """
        track_timeout = config.get("TRACK_TIMEOUT_SECONDS", 5)
        for track_id in list(self.tracks.keys()):
            last_seen = self.tracks[track_id]["last_seen"]
            if current_timestamp - last_seen > track_timeout:
                del self.tracks[track_id]
