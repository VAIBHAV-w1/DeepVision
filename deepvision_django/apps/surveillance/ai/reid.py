try:
    import cv2
    import numpy as np
except (ImportError, Exception):
    cv2 = None
    np = None
import time
import math
from threading import Lock

class GlobalIdentityRegistry:
    """
    Thread-safe registry for mapping camera-local tracking IDs to persistent
    global identities (PERSON-xxx and ITEM-xxx) across multiple cameras.
    """
    def __init__(self):
        self.lock = Lock()
        
        # Local mapping state: (camera_id, local_track_id) -> global_id (str)
        self.local_to_global = {}
        
        # Active global persons: global_person_id -> {
        #    "global_id": str,
        #    "last_seen_time": float,
        #    "last_camera_id": int,
        #    "last_local_track_id": int,
        #    "histogram": np.ndarray|None,
        #    "reid_status": str,       # "CONFIRMED" | "PROBABLE" | "UNCERTAIN"
        #    "reid_confidence": float,
        #    "carried_items": set       # set of global_item_ids
        # }
        self.global_persons = {}
        
        # Active global items: global_item_id -> {
        #    "global_id": str,
        #    "class_name": str,
        #    "confidence": float,
        #    "first_seen": float,
        #    "last_seen": float,
        #    "current_camera_id": int,
        #    "current_local_track_id": int,
        #    "associated_person_id": str|None,
        #    "status": str,
        #    "lifecycle_history": list,  # list of event logs
        #    "checkout_details": dict|None  # POS check out details
        # }
        self.global_items = {}
        
        # Counters
        self.person_counter = 0
        self.item_counter = 0
        
        # Lost tracks buffer for cross-camera Re-ID: list of dicts
        self.lost_persons = []

    def clear(self):
        """Clears all states (used primarily between unit tests)."""
        with self.lock:
            self.local_to_global.clear()
            self.global_persons.clear()
            self.global_items.clear()
            self.lost_persons.clear()
            self.person_counter = 0
            self.item_counter = 0

    def calculate_hsv_histogram(self, crop):
        """Calculates a normalized 2D HSV color histogram of a crop image."""
        if crop is None or crop.size == 0:
            return None
        try:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
            return hist
        except Exception:
            return None

    def compare_histograms(self, hist1, hist2):
        """Computes correlation similarity between two histograms [0, 1]."""
        if hist1 is None or hist2 is None:
            return 0.0
        try:
            val = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            return max(0.0, min(1.0, val))
        except Exception:
            return 0.0

    def get_global_person_id(self, camera_id, local_track_id, crop=None, timestamp=None):
        """
        Retrieves or generates a persistent global PERSON ID, performing Re-ID.
        """
        if timestamp is None:
            timestamp = time.time()
            
        key = (camera_id, local_track_id)
        
        with self.lock:
            # 1. Existing local association check
            if key in self.local_to_global:
                g_id = self.local_to_global[key]
                if g_id in self.global_persons:
                    self.global_persons[g_id]["last_seen_time"] = timestamp
                    self.global_persons[g_id]["last_camera_id"] = camera_id
                    self.global_persons[g_id]["last_local_track_id"] = local_track_id
                    if crop is not None:
                        self.global_persons[g_id]["histogram"] = self.calculate_hsv_histogram(crop)
                return g_id, self.global_persons.get(g_id, {}).get("reid_status", "CONFIRMED")

            # Calculate histogram of new crop
            new_hist = self.calculate_hsv_histogram(crop) if crop is not None else None

            # 2. Attempt Re-ID against lost tracks list
            best_match = None
            best_score = 0.0
            
            # Clean up lost tracks older than 30 seconds
            self.lost_persons = [p for p in self.lost_persons if timestamp - p["lost_time"] <= 30.0]

            for candidate in self.lost_persons:
                # Basic continuity gating: can only match if different camera or same camera after a gap
                # (Same camera match is allowed if they went out of frame and returned)
                time_gap = timestamp - candidate["lost_time"]
                if time_gap >= 0.0 and time_gap <= 30.0:
                    similarity = self.compare_histograms(new_hist, candidate["histogram"])
                    if similarity > best_score:
                        best_score = similarity
                        best_match = candidate

            # Re-ID Match thresholds
            # CONFIRMED: >= 0.82
            # PROBABLE: >= 0.70
            # UNCERTAIN: >= 0.55
            reid_status = "CONFIRMED"
            reid_confidence = 1.0
            matched_g_id = None

            if best_match is not None and best_score >= 0.55:
                matched_g_id = best_match["global_id"]
                reid_confidence = best_score
                if best_score >= 0.82:
                    reid_status = "CONFIRMED"
                elif best_score >= 0.70:
                    reid_status = "PROBABLE"
                else:
                    reid_status = "UNCERTAIN"
                
                # Remove from lost list
                self.lost_persons = [p for p in self.lost_persons if p["global_id"] != matched_g_id]

            if matched_g_id:
                # Re-associated successfully!
                self.local_to_global[key] = matched_g_id
                p_state = self.global_persons.get(matched_g_id)
                if p_state:
                    p_state.update({
                        "last_seen_time": timestamp,
                        "last_camera_id": camera_id,
                        "last_local_track_id": local_track_id,
                        "reid_status": reid_status,
                        "reid_confidence": reid_confidence
                    })
                    if new_hist is not None:
                        p_state["histogram"] = new_hist
                else:
                    self.global_persons[matched_g_id] = {
                        "global_id": matched_g_id,
                        "last_seen_time": timestamp,
                        "last_camera_id": camera_id,
                        "last_local_track_id": local_track_id,
                        "histogram": new_hist,
                        "reid_status": reid_status,
                        "reid_confidence": reid_confidence,
                        "carried_items": set()
                    }
                return matched_g_id, reid_status

            # 3. Create a new global PERSON ID
            self.person_counter += 1
            new_g_id = f"PERSON-{self.person_counter:03d}"
            
            self.local_to_global[key] = new_g_id
            self.global_persons[new_g_id] = {
                "global_id": new_g_id,
                "last_seen_time": timestamp,
                "last_camera_id": camera_id,
                "last_local_track_id": local_track_id,
                "histogram": new_hist,
                "reid_status": "CONFIRMED", # Fresh track is confirmed by default
                "reid_confidence": 1.0,
                "carried_items": set()
            }
            return new_g_id, "CONFIRMED"

    def resolve_person(self, camera_id, local_track_id, crop=None, timestamp=None):
        """Authoritative resolver mapping to get_global_person_id with structured Re-ID certainty."""
        gid, status = self.get_global_person_id(camera_id, local_track_id, crop, timestamp)
        certainty = "HIGH" if status == "CONFIRMED" else ("MEDIUM" if status == "PROBABLE" else "LOW")
        return gid, status, certainty

    def resolve_item(self, camera_id, local_track_id, class_name="Unknown Object", timestamp=None, confidence=0.0):
        """Authoritative resolver mapping to get_global_item_id."""
        gid = self.get_global_item_id(camera_id, local_track_id, timestamp=timestamp, class_name=class_name, confidence=confidence)
        return gid, "DETECTED"

    def get_global_item_id(self, camera_id, local_track_id, crop=None, timestamp=None, class_name="Unknown Object", confidence=0.0):
        """
        Retrieves or generates a persistent global ITEM ID.
        Since items are small, we map them directly per camera session or transfer them.
        """
        if timestamp is None:
            timestamp = time.time()
            
        key = (camera_id, local_track_id)
        
        with self.lock:
            # 1. Existing local association check
            if key in self.local_to_global:
                g_id = self.local_to_global[key]
                if g_id in self.global_items:
                    item = self.global_items[g_id]
                    item["last_seen"] = timestamp
                    item["current_camera_id"] = camera_id
                    item["current_local_track_id"] = local_track_id
                    item["confidence"] = confidence
                return g_id

            # 2. Check if this local track has already been matched via Re-ID transfer
            # (If a person was carrying ITEM-001, and Re-Identified on Camera 2,
            # we can resolve which new local track is closest to the person as ITEM-001)
            # This is handled dynamically by the association manager, so here we fallback to fresh ID.
            
            # 3. Create a new global ITEM ID
            self.item_counter += 1
            new_g_id = f"ITEM-{self.item_counter:03d}"
            
            self.local_to_global[key] = new_g_id
            self.global_items[new_g_id] = {
                "global_id": new_g_id,
                "class_name": class_name,
                "confidence": confidence,
                "first_seen": timestamp,
                "last_seen": timestamp,
                "current_camera_id": camera_id,
                "current_local_track_id": local_track_id,
                "associated_person_id": None,
                "status": "DETECTED",
                "lifecycle_history": [
                    {"timestamp": timestamp, "event_type": "DETECTED", "message": f"Object ({class_name}) detected.", "camera_id": camera_id}
                ],
                "checkout_details": None
            }
            return new_g_id

    def handle_lost_track(self, camera_id, local_track_id, timestamp=None):
        """Called when a local track disappears. Moves it to the lost buffer."""
        if timestamp is None:
            timestamp = time.time()
            
        key = (camera_id, local_track_id)
        with self.lock:
            if key in self.local_to_global:
                g_id = self.local_to_global[key]

                # Grace window for items: if the item was seen within 2 seconds, don't evict yet.
                # This prevents a momentary confidence dip (dropping the box from one inference
                # cycle) from wiping the (camera, track_id) → ITEM-XXX mapping and minting a new
                # global ID when the phone reappears in the very next frame.
                if g_id in self.global_items:
                    last_seen = self.global_items[g_id].get("last_seen", 0.0)
                    if timestamp - last_seen < 2.0:
                        return  # Still fresh — don't evict

                # Remove mapping and buffer persons for Re-ID
                self.local_to_global.pop(key)
                g_id_removed = g_id
                
                # If it's a person, buffer their crop history for Re-ID
                if g_id_removed in self.global_persons:
                    p_state = self.global_persons[g_id_removed]
                    self.lost_persons.append({
                        "global_id": g_id_removed,
                        "histogram": p_state["histogram"],
                        "lost_time": timestamp
                    })
                    
                    # Clean up carried items local mapping references if person leaves

    # Alias for API compatibility
    mark_person_lost = handle_lost_track

    def log_item_event(self, global_item_id, event_type, message, camera_id, timestamp=None):
        """Logs an event in the item's lifecycle history."""
        if timestamp is None:
            timestamp = time.time()
        with self.lock:
            if global_item_id in self.global_items:
                self.global_items[global_item_id]["lifecycle_history"].append({
                    "timestamp": timestamp,
                    "event_type": event_type,
                    "message": message,
                    "camera_id": camera_id
                })

    def checkout_event(self, person_id, item_id, transaction_id, user_id, timestamp=None):
        """
        Processes an external POS checkout event for an item.
        Updates item status to CHECKED_OUT and records transaction details.
        """
        if timestamp is None:
            timestamp = time.time()
        with self.lock:
            if item_id in self.global_items:
                item = self.global_items[item_id]
                
                from apps.cameras.models import Camera
                camera = Camera.objects.filter(id=item["current_camera_id"]).first()
                if not camera or camera.user_id != user_id:
                    return False
                    
                item["status"] = "CHECKED_OUT"
                item["checkout_details"] = {
                    "transaction_id": transaction_id,
                    "timestamp": timestamp,
                    "person_id": person_id
                }
                item["lifecycle_history"].append({
                    "timestamp": timestamp,
                    "event_type": "CHECKED_OUT",
                    "message": f"Checked out under transaction {transaction_id} by {person_id}.",
                    "camera_id": item["current_camera_id"]
                })
                # Persist checkout status to DB as a low-severity alert
                try:
                    from apps.alerts.models import Alert
                    from datetime import datetime, timezone
                    
                    numeric_track = int(item_id.split("-")[1]) if "-" in item_id else 0
                    camera_id = item["current_camera_id"]
                    
                    Alert.objects.create(
                        user_id=user_id,
                        camera_id=camera_id,
                        track_id=numeric_track,
                        event_type="item_checked_out",
                        title="Item Checked Out",
                        message=f"ITEM-{item_id.split('-')[1]} ({item['class_name']}) checked out under transaction {transaction_id} by PERSON-{person_id.split('-')[1] if '-' in person_id else person_id}.",
                        severity="low",
                        status="new",
                        confidence=item["confidence"],
                        detected_at=datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    )
                except Exception as e:
                    print(f"[ERROR] Failed to save checkout alert: {e}")
                return True
        return False

# Global Identity Registry Instance
registry = GlobalIdentityRegistry()
