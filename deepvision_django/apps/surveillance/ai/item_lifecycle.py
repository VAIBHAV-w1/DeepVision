import time
import math
from apps.surveillance.ai.reid import registry

class ItemLifecycleManager:
    """
    Manages state transitions and person-item associations for tracked items.
    State machine: DETECTED -> PICKED_UP -> CARRIED -> CHECKOUT_PENDING -> CHECKED_OUT / PLACED / EXITED
    Concealment: CONCEALED_ITEM_SUSPECTED (e.g. item placed in bag)
    Unattended: ABANDONED
    """
    def __init__(self, association_distance_threshold=120.0):
        self.association_distance_threshold = association_distance_threshold
        # Stores last active local bbox mapping for items
        self.item_last_boxes = {}
        # Stores disappeared items to check for concealment: item_id -> disappearance_time
        self.disappeared_items = {}

    def update_associations_and_lifecycles(self, active_persons, active_items, zones, camera_id, timestamp=None):
        """
        Main update loop executed at the AI inference cadence.
        """
        if timestamp is None:
            timestamp = time.time()

        if zones is None:
            zones = []

        # Update bboxes cache
        current_active_item_ids = {item["global_id"] for item in active_items}
        for item in active_items:
            self.item_last_boxes[item["global_id"]] = item["bbox"]

        # Track maps for quick lookups
        persons_map = {p["global_id"]: p for p in active_persons}
        items_map = {item["global_id"]: item for item in active_items}

        # Step 1: Identify Exit Zones and Checkout Zones
        exit_zones = []
        checkout_zones = []
        for zone in zones:
            if not zone.enabled:
                continue
            zname = zone.name.lower()
            if any(term in zname for term in ("exit", "door", "gate")):
                exit_zones.append(zone)
            elif any(term in zname for term in ("checkout", "register", "billing", "cashier")):
                checkout_zones.append(zone)

        # Step 2: Handle Active Items Lifecycle & Association
        for item in active_items:
            item_id = item["global_id"]
            ix1, iy1, ix2, iy2 = item["bbox"]
            icx, icy = item["center"]
            
            g_item = registry.global_items.get(item_id)
            if not g_item:
                continue

            current_assoc_person = g_item["associated_person_id"]

            # Evaluate distance to all active persons to find the closest overlapping one
            best_person_id = None
            min_dist = float("inf")

            for person in active_persons:
                px1, py1, px2, py2 = person["bbox"]
                pcx, pcy = person["center"]
                
                # Check distance between centers
                dist = math.sqrt((icx - pcx) ** 2 + (icy - pcy) ** 2)
                is_overlapping = (px1 <= icx <= px2) and (py1 <= icy <= py2)

                if (is_overlapping or dist <= self.association_distance_threshold) and dist < min_dist:
                    min_dist = dist
                    best_person_id = person["global_id"]

            current_status = g_item["status"]
            
            # Transition: DETECTED -> PICKED_UP
            if best_person_id and current_status in ("DETECTED", "PLACED", "ABANDONED"):
                g_item["status"] = "PICKED_UP"
                g_item["associated_person_id"] = best_person_id
                registry.log_item_event(
                    item_id,
                    "PICKED_UP",
                    f"Item picked up by {best_person_id}.",
                    camera_id,
                    timestamp
                )
                p_state = registry.global_persons.get(best_person_id)
                if p_state:
                    p_state["carried_items"].add(item_id)

            # Transition: PICKED_UP -> CARRIED
            elif best_person_id and current_status == "PICKED_UP":
                g_item["status"] = "CARRIED"
                registry.log_item_event(
                    item_id,
                    "CARRIED",
                    f"Item carried by {best_person_id}.",
                    camera_id,
                    timestamp
                )

            # Transition: Transfer ownership if a different person takes the item
            elif best_person_id and current_assoc_person and best_person_id != current_assoc_person:
                curr_person = persons_map.get(current_assoc_person)
                curr_dist = float("inf")
                if curr_person:
                    curr_dist = math.sqrt((icx - curr_person["center"][0]) ** 2 + (icy - curr_person["center"][1]) ** 2)

                if curr_dist > self.association_distance_threshold or min_dist < curr_dist / 2.0:
                    old_p = registry.global_persons.get(current_assoc_person)
                    if old_p:
                        old_p["carried_items"].discard(item_id)
                        
                    g_item["associated_person_id"] = best_person_id
                    g_item["status"] = "PICKED_UP"
                    registry.log_item_event(
                        item_id,
                        "PICKED_UP",
                        f"Item transferred and picked up by {best_person_id}.",
                        camera_id,
                        timestamp
                    )
                    new_p = registry.global_persons.get(best_person_id)
                    if new_p:
                        new_p["carried_items"].add(item_id)

            # Transition: CARRIED/PICKED_UP -> PLACED
            elif not best_person_id and current_assoc_person:
                assoc_p = persons_map.get(current_assoc_person)
                assoc_dist = float("inf")
                if assoc_p:
                    apcx, apcy = assoc_p["center"]
                    assoc_dist = math.sqrt((icx - apcx) ** 2 + (icy - apcy) ** 2)

                if assoc_dist > self.association_distance_threshold:
                    g_item["status"] = "PLACED"
                    g_item["associated_person_id"] = None
                    registry.log_item_event(
                        item_id,
                        "PLACED",
                        f"Item placed back on shelf by {current_assoc_person}.",
                        camera_id,
                        timestamp
                    )
                    self._create_db_alert(
                        event_type="item_placed_back",
                        title="Item Placed Back",
                        message=f"ITEM-{item_id.split('-')[1]} ({g_item['class_name']}) placed back on shelf by PERSON-{current_assoc_person.split('-')[1]}.",
                        camera_id=camera_id,
                        timestamp=timestamp,
                        item_id=item_id,
                        person_id=current_assoc_person,
                        confidence=g_item["confidence"],
                        severity="low"
                    )
                    p_state = registry.global_persons.get(current_assoc_person)
                    if p_state:
                        p_state["carried_items"].discard(item_id)

            # Transition: PLACED -> ABANDONED
            elif not best_person_id and current_status == "PLACED":
                any_nearby = False
                for person in active_persons:
                    pcx, pcy = person["center"]
                    if math.sqrt((icx - pcx) ** 2 + (icy - pcy) ** 2) <= self.association_distance_threshold:
                        any_nearby = True
                        break

                if not any_nearby:
                    g_item["status"] = "ABANDONED"
                    registry.log_item_event(
                        item_id,
                        "ABANDONED",
                        "Item left unattended.",
                        camera_id,
                        timestamp
                    )

            self.disappeared_items.pop(item_id, None)

        # Step 3: Handle Disappeared Items & Concealment (e.g. Person -> Bag -> Item)
        for item_id, g_item in list(registry.global_items.items()):
            if g_item["current_camera_id"] == camera_id and item_id not in current_active_item_ids:
                status = g_item["status"]
                
                if status in ("PICKED_UP", "CARRIED", "CONCEALED_ITEM_SUSPECTED"):
                    assoc_person_id = g_item["associated_person_id"]
                    
                    if assoc_person_id and assoc_person_id in persons_map:
                        if item_id not in self.disappeared_items:
                            self.disappeared_items[item_id] = timestamp
                        else:
                            gone_duration = timestamp - self.disappeared_items[item_id]
                            if gone_duration >= 1.0 and status != "CONCEALED_ITEM_SUSPECTED":
                                # Smart Basket/Bag check: does the person carry a "Bag" item?
                                p_state = registry.global_persons.get(assoc_person_id)
                                carries_bag = False
                                if p_state:
                                    for c_id in p_state["carried_items"]:
                                        c_item = registry.global_items.get(c_id)
                                        if c_item and c_item["class_name"] == "Bag" and c_id in current_active_item_ids:
                                            carries_bag = True
                                            break
                                
                                g_item["status"] = "CONCEALED_ITEM_SUSPECTED"
                                msg = f"Concealed item suspected on {assoc_person_id}"
                                if carries_bag:
                                    msg += " (possibly inside bag)"
                                msg += "."
                                
                                registry.log_item_event(
                                    item_id,
                                    "CONCEALED_ITEM_SUSPECTED",
                                    msg,
                                    camera_id,
                                    timestamp
                                )
                                self._create_db_alert(
                                    event_type="concealed_item_suspected",
                                    title="Concealed Item Suspected",
                                    message=f"ITEM-{item_id.split('-')[1]} ({g_item['class_name']}) went out of sight while carried by PERSON-{assoc_person_id.split('-')[1]}. {msg}",
                                    camera_id=camera_id,
                                    timestamp=timestamp,
                                    item_id=item_id,
                                    person_id=assoc_person_id,
                                    confidence=g_item["confidence"],
                                    severity="low"
                                )
                    else:
                        self.disappeared_items.pop(item_id, None)

        # Step 4: Handle Checkout and Exit Zone Entry Evaluations
        for person in active_persons:
            person_id = person["global_id"]
            pcx, pcy = person["center"]
            
            p_state = registry.global_persons.get(person_id)
            if not p_state:
                continue

            # A. Check if person is in any Checkout Zone
            in_checkout = False
            for zone in checkout_zones:
                if zone.is_point_inside(pcx, pcy):
                    in_checkout = True
                    break

            if in_checkout:
                for item_id in list(p_state["carried_items"]):
                    g_item = registry.global_items.get(item_id)
                    if g_item and g_item["status"] in ("PICKED_UP", "CARRIED", "CONCEALED_ITEM_SUSPECTED"):
                        g_item["status"] = "CHECKOUT_PENDING"
                        registry.log_item_event(
                            item_id,
                            "CHECKOUT_PENDING",
                            f"Item at checkout counter with {person_id}.",
                            camera_id,
                            timestamp
                        )

            # B. Check if person is in any Exit Zone
            in_exit = False
            exit_zone_name = "Exit Zone"
            for zone in exit_zones:
                if zone.is_point_inside(pcx, pcy):
                    in_exit = True
                    exit_zone_name = zone.name
                    break

            if in_exit:
                for item_id in list(p_state["carried_items"]):
                    g_item = registry.global_items.get(item_id)
                    if not g_item:
                        continue

                    if g_item["status"] != "EXITED":
                        # Checked Out exit -> clean close
                        if g_item["status"] == "CHECKED_OUT":
                            g_item["status"] = "EXITED"
                            registry.log_item_event(
                                item_id,
                                "EXITED",
                                f"Item exited legitimately with {person_id}.",
                                camera_id,
                                timestamp
                            )
                        # Unpaid exit -> evaluate evidence level for severity
                        else:
                            has_evidence = False
                            for history_entry in g_item["lifecycle_history"]:
                                if history_entry["event_type"] in ("PICKED_UP", "CARRIED", "CONCEALED_ITEM_SUSPECTED"):
                                    has_evidence = True
                                    break
                            
                            if has_evidence:
                                g_item["status"] = "EXITED"
                                registry.log_item_event(
                                    item_id,
                                    "EXITED",
                                    f"Unpaid removal by {person_id}.",
                                    camera_id,
                                    timestamp
                                )
                                
                                history_str = " -> ".join([
                                    f"{evt['event_type']} ({time.strftime('%H:%M:%S', time.localtime(evt['timestamp']))})"
                                    for evt in g_item["lifecycle_history"]
                                ])
                                
                                # Evidence-Based Smart Severity Alert levels
                                # High Severity conditions:
                                # 1. Person Re-ID is CONFIRMED or PROBABLE (not UNCERTAIN)
                                # 2. Item confidence >= 0.50
                                reid_status = p_state.get("reid_status", "CONFIRMED")
                                is_high_confidence = (reid_status in ("CONFIRMED", "PROBABLE")) and (g_item["confidence"] >= 0.50)
                                
                                severity = "high" if is_high_confidence else "medium"
                                alert_type = "suspicious_unpaid_item_removal" if is_high_confidence else "suspicious_exit_review_required"
                                title = "Suspicious Unpaid Item Removal" if is_high_confidence else "Suspicious Exit - Review Required"
                                
                                message_txt = (
                                    f"PERSON-{person_id.split('-')[1]} exited monitored area carrying "
                                    f"ITEM-{item_id.split('-')[1]} ({g_item['class_name']}) without a confirmed checkout event.\n"
                                    f"Checkout Status: CHECKOUT_UNKNOWN. Zone: {exit_zone_name}.\n"
                                    f"Re-ID Status: {reid_status}. Tracking Confidence: {g_item['confidence'] * 100:.0f}%.\n"
                                    f"Lifecycle Timeline: {history_str}"
                                )
                                
                                self._create_db_alert(
                                    event_type=alert_type,
                                    title=title,
                                    message=message_txt,
                                    camera_id=camera_id,
                                    timestamp=timestamp,
                                    item_id=item_id,
                                    person_id=person_id,
                                    confidence=g_item["confidence"],
                                    severity=severity
                                )

    def _create_db_alert(self, event_type, title, message, camera_id, timestamp, item_id, person_id, confidence, severity="low"):
        """Helper to create persistent alerts in DB for tracking and theft anomalies."""
        try:
            from apps.alerts.models import Alert
            from apps.cameras.models import Camera
            from datetime import datetime, timezone
            
            numeric_track = int(item_id.split("-")[1]) if "-" in item_id else 0
            
            camera = Camera.objects.filter(id=camera_id).first()
            if not camera:
                return
                
            Alert.objects.create(
                user_id=camera.user_id,
                camera_id=camera_id,
                track_id=numeric_track,
                event_type=event_type,
                title=title,
                message=message,
                severity=severity,
                status="new",
                confidence=confidence,
                location=camera.location,
                detected_at=datetime.fromtimestamp(timestamp, tz=timezone.utc)
            )
        except Exception as e:
            print(f"[ERROR] Failed to save DB alert: {e}")

# Global Item Lifecycle Manager Instance
lifecycle_manager = ItemLifecycleManager()
