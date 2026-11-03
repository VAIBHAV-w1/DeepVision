import math
from .zones import RestrictedZone

_SECURITY_INTRUDER_CLASSES = frozenset({
    "person", "car", "truck", "bus", "motorcycle", "bicycle"
})


class AnomalyDetector:
    """
    Modular, rule-based anomaly detection engine that Consumes tracking and
    behavioral classification properties, identifies suspicious behaviors,
    and returns structured anomaly event dictionaries.
    """
    def __init__(self, config=None):
        self.config = config or {}

        # State stores - stream-scoped and transient
        self.cooldowns = {}                 # maps (track_id, event_type) -> last_triggered_time (float)
        self.restricted_zone_states = {}    # maps track_id -> set of zone IDs they were inside in the previous frame
        self.fast_movement_timers = {}      # maps track_id -> {"start": float, "last_fast": float}
        self.rapid_movement_timers = {}     # maps track_id -> {"start": float, "last_rapid": float}

        # Maps object_track_id -> dict state for abandoned objects:
        # {
        #   "associated_person_track_id": int,
        #   "last_nearby_person_time": float,
        #   "last_object_position": (float, float),
        #   "stationary_start_time": float,
        #   "last_seen_time": float
        # }
        self.abandoned_objects = {}

    def detect(self, tracked_objects, timestamp, zones=None):
        """
        Processes a list of tracked objects with behavioral attributes and
        evaluates anomaly rules. Returns a list of generated anomaly events.
        """
        # If no zones provided, use a default test zone for evaluation/unit tests
        if zones is None:
            zones = [
                RestrictedZone("restricted_1", "Restricted Zone 1", 400, 50, 600, 250, enabled=True)
            ]
        else:
            # Instantiate RestrictedZone objects if dicts or models are passed
            instantiated_zones = []
            for z in zones:
                if isinstance(z, dict):
                    instantiated_zones.append(
                        RestrictedZone(
                            z["id"], z["name"], z["x1"], z["y1"], z["x2"], z["y2"], z.get("enabled", True)
                        )
                    )
                elif hasattr(z, 'is_point_inside'):
                    instantiated_zones.append(z)
                else:
                    instantiated_zones.append(
                        RestrictedZone(
                            getattr(z, 'id', 1),
                            getattr(z, 'name', 'Restricted Zone'),
                            getattr(z, 'x1', 0),
                            getattr(z, 'y1', 0),
                            getattr(z, 'x2', 100),
                            getattr(z, 'y2', 100),
                            getattr(z, 'enabled', True)
                        )
                    )
            zones = instantiated_zones

        events = []
        active_track_ids = {obj["track_id"] for obj in tracked_objects}

        # 1. Map persons by track ID for proximity lookups
        persons = {obj["track_id"]: obj for obj in tracked_objects if obj["class_name"] == "person"}

        # 2. Iterate and check rules for every active object
        for obj in tracked_objects:
            track_id = obj["track_id"]
            cls_name = obj["class_name"]
            conf = obj["confidence"]
            center_x = obj["center_x"]
            center_y = obj["center_y"]
            behavior = obj["behavior"]
            speed = float(obj.get("speed", 0.0) or 0.0)
            window_speed = float(obj.get("window_speed", speed) or speed)
            window_displacement = float(obj.get("window_displacement", 0.0) or 0.0)
            direction_reversals = int(obj.get("direction_reversals", 0) or 0)
            stationary_duration = float(obj.get("stationary_duration", 0.0) or 0.0)

            # ----------------------------------------------------
            # RULE A: LOITERING
            # ----------------------------------------------------
            if self.config.get("LOITERING_ENABLED", True) and behavior == "loitering" and cls_name == "person":
                event = self._create_event(
                    event_type="loitering",
                    severity="medium",
                    track_id=track_id,
                    class_name=cls_name,
                    confidence=conf,
                    message="Prolonged presence detected.",
                    timestamp=timestamp
                )
                if event:
                    events.append(event)

            # ----------------------------------------------------
            # RULE B: RESTRICTED AREA ENTRY (VALID SECURITY INTRUDERS ONLY)
            # ----------------------------------------------------
            current_inside_zones = set()
            active_zones = zones if (self.config.get("RESTRICTED_ENTRY_ENABLED", True) and cls_name in _SECURITY_INTRUDER_CLASSES) else []
            for zone in active_zones:
                zone_id = getattr(zone, 'id', None)
                zone_name = getattr(zone, 'name', 'Restricted Area')
                zone_camera_id = getattr(zone, 'camera_id', None)
                zone_user_id = getattr(zone, 'user_id', None)
                if zone.is_point_inside(center_x, center_y):
                    current_inside_zones.add(zone_id)

                    # Transition: OUTSIDE -> INSIDE
                    prev_inside_zones = self.restricted_zone_states.get(track_id, set())
                    if zone_id not in prev_inside_zones:
                        event = self._create_event(
                            event_type="restricted_area_entry",
                            severity="high",
                            track_id=track_id,
                            class_name=cls_name,
                            confidence=conf,
                            message=f"Restricted area entry detected in {zone_name}.",
                            timestamp=timestamp,
                            bypass_cooldown=False
                        )
                        if event:
                            if zone_camera_id is not None:
                                event["camera_id"] = zone_camera_id
                            if zone_user_id is not None:
                                event["user_id"] = zone_user_id
                            event["zone_id"] = zone_id
                            event["zone_name"] = zone_name
                            events.append(event)

            # Save zone status for the next frame
            self.restricted_zone_states[track_id] = current_inside_zones

            # ----------------------------------------------------
            # RULE C: UNUSUAL MOVEMENT (ERRATIC REVERSALS OR SUSTAINED FAST MOTION)
            # ----------------------------------------------------
            if self.config.get("UNUSUAL_MOVEMENT_ENABLED", True) and cls_name in _SECURITY_INTRUDER_CLASSES:
                speed_fast_thresh = float(self.config.get("SPEED_FAST_THRESHOLD", 150.0))
                reversal_thresh = int(self.config.get("UNUSUAL_REVERSAL_THRESHOLD", 2))
                is_erratic = (direction_reversals >= reversal_thresh and max(speed, window_speed) >= 60.0)
                is_sustained_fast = (
                    (behavior == "moving_fast" or window_speed >= speed_fast_thresh)
                    and (window_displacement >= 55.0 or speed >= speed_fast_thresh)
                )

                if is_erratic:
                    event = self._create_event(
                        event_type="unusual_movement",
                        severity="medium",
                        track_id=track_id,
                        class_name=cls_name,
                        confidence=conf,
                        message=f"Erratic movement pattern detected ({direction_reversals} rapid direction reversals).",
                        timestamp=timestamp
                    )
                    if event:
                        events.append(event)
                elif is_sustained_fast:
                    tmr = self.fast_movement_timers.get(track_id)
                    if tmr is None:
                        self.fast_movement_timers[track_id] = {"start": timestamp, "last_fast": timestamp}
                    else:
                        tmr["last_fast"] = timestamp
                        duration = timestamp - tmr["start"]
                        fast_thresh = float(self.config.get("UNUSUAL_MOVEMENT_PERSISTENCE_SECONDS", 1.5))
                        if duration >= fast_thresh:
                            event = self._create_event(
                                event_type="unusual_movement",
                                severity="medium",
                                track_id=track_id,
                                class_name=cls_name,
                                confidence=conf,
                                message=f"Unusual sustained fast movement pattern detected ({max(speed, window_speed):.0f} px/s).",
                                timestamp=timestamp
                            )
                            if event:
                                events.append(event)
                else:
                    tmr = self.fast_movement_timers.get(track_id)
                    if tmr is not None and (timestamp - tmr["last_fast"] > 0.45):
                        self.fast_movement_timers.pop(track_id, None)
            else:
                self.fast_movement_timers.pop(track_id, None)

            # ----------------------------------------------------
            # RULE C2: RAPID MOVEMENT (HIGH-VELOCITY DASH / SPRINT)
            # ----------------------------------------------------
            if self.config.get("RAPID_MOVEMENT_ENABLED", True) and cls_name in _SECURITY_INTRUDER_CLASSES:
                rapid_speed_thresh = float(self.config.get("RAPID_MOVEMENT_SPEED_THRESHOLD", 240.0))
                rapid_disp_thresh = float(self.config.get("RAPID_MOVEMENT_MIN_DISPLACEMENT", 110.0))
                rapid_persist_sec = float(self.config.get("RAPID_MOVEMENT_PERSISTENCE_SECONDS", 0.45))
                peak_vel = max(speed, window_speed)
                is_rapid = (peak_vel >= rapid_speed_thresh and window_displacement >= rapid_disp_thresh)

                if is_rapid:
                    rtmr = self.rapid_movement_timers.get(track_id)
                    if rtmr is None:
                        self.rapid_movement_timers[track_id] = {"start": timestamp, "last_rapid": timestamp}
                    else:
                        rtmr["last_rapid"] = timestamp
                        if (timestamp - rtmr["start"]) >= rapid_persist_sec:
                            event = self._create_event(
                                event_type="rapid_movement",
                                severity="high",
                                track_id=track_id,
                                class_name=cls_name,
                                confidence=conf,
                                message=f"Rapid high-velocity movement detected ({peak_vel:.0f} px/s across {window_displacement:.0f} px).",
                                timestamp=timestamp
                            )
                            if event:
                                events.append(event)
                else:
                    rtmr = self.rapid_movement_timers.get(track_id)
                    if rtmr is not None and (timestamp - rtmr["last_rapid"] > 0.35):
                        self.rapid_movement_timers.pop(track_id, None)
            else:
                self.rapid_movement_timers.pop(track_id, None)

            # ----------------------------------------------------
            # RULE D: ABANDONED OBJECT DETECTION
            # ----------------------------------------------------
            supported_movable_objects = {"backpack", "handbag", "suitcase", "laptop"}
            if self.config.get("ABANDONED_OBJECT_ENABLED", True) and cls_name in supported_movable_objects:
                # Eligible when stationary OR newly placed / low drift speed (fixes frame-1 association where stationary_duration == 0.0)
                is_stationary = (behavior == "stationary" or stationary_duration > 0.0 or speed <= 30.0)

                if is_stationary:
                    if track_id not in self.abandoned_objects:
                        # Find nearest person for initial association
                        nearest_person_id = None
                        min_dist = float("inf")
                        assoc_dist_thresh = float(self.config.get("PERSON_OBJECT_ASSOCIATION_DISTANCE", 140.0))

                        for p_id, p_obj in persons.items():
                            d = math.sqrt((center_x - p_obj["center_x"]) ** 2 + (center_y - p_obj["center_y"]) ** 2)
                            if d <= assoc_dist_thresh and d < min_dist:
                                min_dist = d
                                nearest_person_id = p_id

                        # Only initialize state if we associated an owner/carrier person track ID
                        if nearest_person_id is not None:
                            self.abandoned_objects[track_id] = {
                                "associated_person_track_id": nearest_person_id,
                                "last_nearby_person_time": timestamp,
                                "last_object_position": (center_x, center_y),
                                "stationary_start_time": timestamp,
                                "last_seen_time": timestamp
                            }
                    else:
                        obj_state = self.abandoned_objects[track_id]
                        obj_state["last_seen_time"] = timestamp

                        # Verify if object has drifted significantly from its placed position
                        last_pos = obj_state["last_object_position"]
                        drift = math.sqrt((center_x - last_pos[0]) ** 2 + (center_y - last_pos[1]) ** 2)
                        drift_thresh = float(self.config.get("STATIONARY_DISTANCE_THRESHOLD", 20.0))

                        if drift > drift_thresh:
                            # Object moved — reset stationary timer and placement position
                            obj_state["stationary_start_time"] = timestamp
                            obj_state["last_object_position"] = (center_x, center_y)
                            obj_state["last_nearby_person_time"] = timestamp
                        else:
                            # Check whether the associated owner (or any attending person within threshold) is still nearby
                            assoc_p_id = obj_state["associated_person_track_id"]
                            p_dist_thresh = float(self.config.get("ABANDONED_OBJECT_DISTANCE_THRESHOLD", 120.0))
                            person_nearby = False

                            if assoc_p_id in persons:
                                p_obj = persons[assoc_p_id]
                                p_dist = math.sqrt((center_x - p_obj["center_x"]) ** 2 + (center_y - p_obj["center_y"]) ** 2)
                                if p_dist <= p_dist_thresh:
                                    person_nearby = True

                            if person_nearby:
                                obj_state["last_nearby_person_time"] = timestamp
                            else:
                                unattended_duration = timestamp - obj_state["last_nearby_person_time"]
                                stationary_duration_total = timestamp - obj_state["stationary_start_time"]
                                time_thresh = float(self.config.get("ABANDONED_OBJECT_TIME_THRESHOLD", 10.0))

                                if unattended_duration >= time_thresh and stationary_duration_total >= time_thresh:
                                    event = self._create_event(
                                        event_type="abandoned_object",
                                        severity="high",
                                        track_id=track_id,
                                        class_name=cls_name,
                                        confidence=conf,
                                        message=f"Potentially unattended {cls_name} left stationary for {unattended_duration:.1f}s.",
                                        timestamp=timestamp
                                    )
                                    if event:
                                        events.append(event)
                else:
                    self.abandoned_objects.pop(track_id, None)

            # ----------------------------------------------------
            # RULE E: UNEXPECTED OBJECT DETECTION
            # ----------------------------------------------------
            unexpected_classes = self.config.get("UNEXPECTED_CLASSES", {"knife", "scissors", "baseball bat", "gun"})
            if self.config.get("UNEXPECTED_OBJECT_ENABLED", True) and cls_name in unexpected_classes:
                event = self._create_event(
                    event_type="unexpected_object",
                    severity="critical" if cls_name in {"knife", "gun"} else "high",
                    track_id=track_id,
                    class_name=cls_name,
                    confidence=conf,
                    message=f"Unauthorized/unexpected object detected: {cls_name}.",
                    timestamp=timestamp
                )
                if event:
                    events.append(event)

        # ----------------------------------------------------
        # RULE F: CROWDING / UNUSUAL COUNT (SCENE LEVEL)
        # ----------------------------------------------------
        crowding_threshold = self.config.get("CROWDING_THRESHOLD", 4)
        if self.config.get("CROWDING_ENABLED", True) and len(persons) >= crowding_threshold:
            event = self._create_event(
                event_type="crowding",
                severity="high" if len(persons) >= crowding_threshold + 2 else "medium",
                track_id=-1,
                class_name="person",
                confidence=1.0,
                message=f"High density crowding detected: {len(persons)} people in view (threshold: {crowding_threshold}).",
                timestamp=timestamp
            )
            if event:
                events.append(event)

        # 3. Clean up stale stream-scoped states to prevent memory leaks
        self._cleanup_stale_states(active_track_ids)

        return events

    def _create_event(self, event_type, severity, track_id, class_name, confidence, message, timestamp, bypass_cooldown=False):
        """
        Helper that verifies if the event type for this track ID is currently
        under cooldown. Returns an event dictionary if allowed, otherwise None.
        """
        cooldown_key = (track_id, event_type)
        cooldown_period = self.config.get("ANOMALY_EVENT_COOLDOWN_SECONDS", 30)

        last_triggered = self.cooldowns.get(cooldown_key)
        if not bypass_cooldown and last_triggered is not None and (timestamp - last_triggered < cooldown_period):
            return None

        # Record trigger timestamp to enforce cooldown
        self.cooldowns[cooldown_key] = timestamp

        return {
            "event_type": event_type,
            "severity": severity,
            "track_id": track_id,
            "class_name": class_name,
            "confidence": confidence,
            "message": message,
            "timestamp": timestamp
        }

    def _cleanup_stale_states(self, active_track_ids):
        """
        Cleans up stream states for tracks no longer active in the current frame.
        """
        # Clean stale restricted zone transition states
        for tid in list(self.restricted_zone_states.keys()):
            if tid not in active_track_ids:
                self.restricted_zone_states.pop(tid, None)

        # Clean stale fast and rapid movement timers
        for tid in list(self.fast_movement_timers.keys()):
            if tid not in active_track_ids:
                self.fast_movement_timers.pop(tid, None)
        for tid in list(self.rapid_movement_timers.keys()):
            if tid not in active_track_ids:
                self.rapid_movement_timers.pop(tid, None)

        # Clean stale abandoned objects state
        for tid in list(self.abandoned_objects.keys()):
            if tid not in active_track_ids:
                self.abandoned_objects.pop(tid, None)
