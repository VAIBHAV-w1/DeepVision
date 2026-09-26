import math

class BehaviorAnalyzer:
    """
    Analyzes historical movement properties of tracked objects to classify
    direction (9 states) and basic behavior classifications using configurable thresholds.
    """
    def __init__(self):
        pass

    def analyze(self, track_history, config):
        """
        Receives track history data dictionary for a tracked object and returns
        a structured dictionary containing speed, distance, direction, and behavior.
        """
        positions = track_history["positions"]
        timestamps = track_history["timestamps"]

        # Default values
        speed = 0.0
        distance = 0.0
        direction = "stationary"
        behavior = "normal"

        # Check if there is enough history to calculate movement
        if len(positions) > 1:
            curr_pos = positions[-1]
            prev_pos = positions[-2]
            curr_time = timestamps[-1]
            prev_time = timestamps[-2]

            # Calculate relative pixel movement (Euclidean distance)
            distance = math.sqrt((curr_pos[0] - prev_pos[0]) ** 2 + (curr_pos[1] - prev_pos[1]) ** 2)
            time_diff = curr_time - prev_time

            # Speed = position change over elapsed time (pixels per second)
            if time_diff > 0:
                speed = distance / time_diff

            # Determine direction using change in center coordinates with a small noise threshold
            dx = curr_pos[0] - prev_pos[0]
            dy = curr_pos[1] - prev_pos[1]
            
            if math.sqrt(dx ** 2 + dy ** 2) < 2.0:
                direction = "stationary"
            else:
                # Math angle calculation (note: negative dy because Y axis goes downward in image pixels)
                angle = math.atan2(-dy, dx)
                degrees = math.degrees(angle) % 360.0

                # Map 360 degrees to 8 directions (45 degrees per sector)
                if (degrees >= 337.5) or (degrees < 22.5):
                    direction = "right"
                elif 22.5 <= degrees < 67.5:
                    direction = "upper-right"
                elif 67.5 <= degrees < 112.5:
                    direction = "up"
                elif 112.5 <= degrees < 157.5:
                    direction = "upper-left"
                elif 157.5 <= degrees < 202.5:
                    direction = "left"
                elif 202.5 <= degrees < 247.5:
                    direction = "lower-left"
                elif 247.5 <= degrees < 292.5:
                    direction = "down"
                else:
                    direction = "lower-right"

        # Retrieve thresholds from Config
        stat_time_thresh = config.get("STATIONARY_TIME_THRESHOLD", 3.0)
        loiter_time_thresh = config.get("LOITERING_TIME_THRESHOLD", 10.0)
        speed_fast_thresh = config.get("SPEED_FAST_THRESHOLD", 150.0)
        speed_slow_thresh = config.get("SPEED_SLOW_THRESHOLD", 15.0)

        # Classification hierarchy
        if track_history.get("loitering_duration", 0.0) >= loiter_time_thresh:
            behavior = "loitering"
        elif track_history.get("stationary_duration", 0.0) >= stat_time_thresh:
            behavior = "stationary"
        elif speed >= speed_fast_thresh:
            behavior = "moving_fast"
        elif speed <= speed_slow_thresh:
            # Only classify moving_slow if not completely stationary
            if direction != "stationary":
                behavior = "moving_slow"
            else:
                behavior = "normal"
        else:
            behavior = "normal"

        return {
            "behavior": behavior,
            "direction": direction,
            "speed": float(speed),
            "distance": float(distance),
            "stationary_duration": float(track_history.get("stationary_duration", 0.0))
        }
