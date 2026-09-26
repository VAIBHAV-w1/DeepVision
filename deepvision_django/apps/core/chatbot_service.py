"""
DeepVision Assistant Service
Provides grounded, website-specific answers exclusively about DeepVision and its features.
Enforces hard scope boundaries against general-purpose AI usage and prevents secret leakage.
"""

import re

OUT_OF_SCOPE_RESPONSE = (
    "I can only help with questions about using DeepVision and its features."
)

# Supported anomaly types explicitly verified in DeepVision
SUPPORTED_ANOMALIES = [
    "Loitering (prolonged presence in a stationary zone)",
    "Restricted Area Entry (unauthorized presence in configured perimeter)",
    "Unusual Movement (abnormal velocity or directional movement)",
    "Abandoned Object (stationary item left unattended)",
    "Unexpected Object (unauthorized object class detected)",
    "Crowding (person count exceeding threshold)",
    "Concealed Item Suspected (item occluded or hidden by tracked person)",
    "Suspicious Unpaid Item Removal (shelf item taken past exit without checkout)"
]

UNSUPPORTED_ANOMALIES = [
    "Weapon / gun / knife violent assault detection",
    "Murder or homicide detection",
    "Semantic theft or shoplifting prediction without POS pairing",
    "Physical fight / combat detection",
    "Facial biometric surveillance / citizen profiling"
]

# Knowledge base of topics and answers
DEEPVISION_KNOWLEDGE = {
    "add_camera": (
        "To add a camera to DeepVision:\n"
        "1. Click '+ Add Camera' in the top navigation or on the Cameras page.\n"
        "2. Select your camera protocol: Phone Camera (Android IP Webcam), USB / Integrated Webcam, Network IP (HTTP/MJPEG), RTSP, or Local Video file.\n"
        "3. Enter a friendly name and the source identifier (e.g. index '0' for built-in webcam, or 'http://<phone-ip>:8080/videofeed' for phone).\n"
        "4. Click 'Test Connection' to verify frames, then save your camera."
    ),
    "connect_webcam": (
        "To connect your laptop webcam or USB camera:\n"
        "1. Go to 'Add Camera' and select 'USB / Webcam'.\n"
        "2. In the Stream Source field, enter the device index number: '0' for your primary built-in webcam, or '1' / '2' for an external USB camera.\n"
        "3. Click 'Test Connection' to verify the video signal.\n"
        "4. Click 'Save Feed' to begin monitoring."
    ),
    "connect_phone": (
        "To connect your Android phone as a camera:\n"
        "1. Install the free 'IP Webcam' app from Google Play on your Android phone.\n"
        "2. Ensure your phone and computer are on the SAME Wi-Fi network.\n"
        "3. Open the app, scroll to the bottom, and tap 'Start server'.\n"
        "4. Note the IP address shown on your phone screen (e.g., http://192.168.1.50:8080).\n"
        "5. In DeepVision, click 'Add Camera', select 'Phone Camera', and enter 'http://<phone-ip>:8080/videofeed' as the source URL.\n"
        "6. Click 'Test Connection' and then 'Save Feed'."
    ),
    "raw_mode": (
        "RAW Mode provides direct, low-latency video streaming from your camera without any AI bounding boxes or overlay graphics. It uses minimal CPU resources and displays the clean, unedited camera feed."
    ),
    "detection_mode": (
        "Detection Mode runs real-time YOLO11 object detection on every camera frame. It displays color-coded bounding boxes, classified object names (such as person, mobile phone, backpack, chair), and model confidence scores (e.g., person 0.92)."
    ),
    "tracking_mode": (
        "Tracking Mode combines YOLO11 detection with ByteTrack to maintain object identities across frames. You\'ll see bounding boxes, object classes, confidence, and Track IDs (such as Track #1, Track #2). If a person is tracked across cameras, a persistent Global ID (e.g., PERSON-001) will also be displayed."
    ),
    "yolo11": (
        "DeepVision uses YOLO11 (specifically YOLO11n - Nano) because it offers state-of-the-art object detection accuracy with an ultra-lightweight memory footprint and fast inference latency. It accurately detects persons and retail items in real time."
    ),
    "bytetrack": (
        "ByteTrack is a high-performance multi-object tracker used by DeepVision. While YOLO11 detects objects in individual frames, ByteTrack utilizes a Kalman filter and Hungarian matching algorithm to associate detections across consecutive frames, giving objects consistent Track IDs even through brief occlusions."
    ),
    "track_id": (
        "A Track ID (e.g., Track #4) is a unique integer assigned by ByteTrack to an object continuously visible in a camera\'s field of view. It prevents duplicate detections and allows DeepVision to analyze trajectory, speed, and dwell time."
    ),
    "global_id": (
        "A Global ID (e.g., PERSON-001 or ITEM-006) is a system-wide identifier managed by DeepVision\'s Global Identity Registry. It tracks a person or item across time and cameras, linking associated items (such as carried phones or bags) to their owner."
    ),
    "recordings": (
        "Recordings in DeepVision are high-definition MP4 video files saved directly to the server. You can record live streams manually by clicking 'Start Recording' on the Live View page, and review, play, or download clips anytime in the Recordings media library."
    ),
    "recording_start": (
        "To start a recording:\n"
        "1. Open any camera in 'Live View'.\n"
        "2. Click the 'Start Recording' button in the right-hand controls panel.\n"
        "3. The timer will track elapsed recording duration.\n"
        "4. Click 'Stop Recording' when finished. The clip will automatically be archived in the 'Recordings' section."
    ),
    "alerts": (
        "Alerts are real-time security notifications generated when DeepVision\'s AI detects an anomaly (such as loitering, perimeter entry, or crowding). Each alert includes an incident severity level (Low, Medium, High, Critical), camera name, timestamp, and automated evidence."
    ),
    "anomalies": (
        "DeepVision currently supports the following real-time anomaly rules:\n"
        "• Loitering: Stationary person exceeding time threshold (e.g., >10s in one spot)\n"
        "• Restricted Area Entry: Target entering prohibited zone boundaries\n"
        "• Unusual Movement: Erratic speed or rapid sudden motion\n"
        "• Abandoned Object: Unattended item left stationary without an owner\n"
        "• Unexpected Object: Unapproved object category in a monitored area\n"
        "• Crowding: Person count exceeding configured room capacity\n"
        "• Concealed Item Suspected: Tracked item disappearing into person boundary\n"
        "• Suspicious Unpaid Item Removal: Item taken from shelf without checkout"
    ),
    "unsupported_features": (
        "DeepVision focuses on behavioral computer vision and perimeter security. The following are NOT currently supported: violent crime / assault / murder prediction, facial biometric identification, audio wiretapping, and fighting detection."
    ),
    "evidence": (
        "An evidence clip is an automated MP4 video recording captured by DeepVision\'s rolling buffer surrounding an anomaly event (including 3 seconds pre-event and 5 seconds post-event). You can inspect the evidence video and snapshot directly from the Alert Investigation page."
    ),
    "camera_offline": (
        "If your camera shows OFFLINE:\n"
        "1. For USB/Webcam: Make sure no other application (like Zoom, Teams, or Skype) is currently using the camera, and verify the device index (usually 0).\n"
        "2. For Phone Camera: Confirm your phone and PC are on the same Wi-Fi subnet, the IP Webcam server is running, and the URL ends with /videofeed.\n"
        "3. For RTSP: Verify network connectivity, IP address, port (usually 554), and credentials.\n"
        "4. Use the 'Test Connection' button on the camera\'s edit page to view real-time diagnostics."
    ),
    "camera_live_vs_ai": (
        "'Camera LIVE' means the physical camera hardware or network stream is actively feeding video frames into DeepVision\'s capture buffer.\n"
        "'AI RUNNING' means the YOLO11 and ByteTrack background inference threads are actively analyzing those frames for objects, tracking paths, and anomalies."
    ),
    "fullscreen": (
        "To enter Fullscreen mode, open any camera in 'Live View' and click the 'Fullscreen' button in the control panel, or press the 'F' key. The video feed will expand to fill your entire monitor with streamlined HUD controls. Press 'Esc' or click the exit button to return."
    ),
    "what_is_deepvision": (
        "DeepVision is an intelligent AI surveillance platform designed for commercial, residential, and industrial security. It combines live video ingestion, YOLO11n object detection, ByteTrack multi-object tracking, spatial anomaly detection, instant alerts, and automated MP4 evidence generation."
    )
}

# General knowledge refusal keywords
GENERAL_KNOWLEDGE_TRIGGERS = [
    r"\bpython\b", r"\bjava\b", r"\bjavascript\b", r"\bc\+\+\b", r"\brust\b",
    r"\bwrite (a|me) (code|program|script|app|essay|poem|story)\b",
    r"\btell me (the )?news\b", r"\bwho is (the )?(prime minister|president|king|ceo of)\b",
    r"\bweather\b", r"\bstock market\b", r"\bbitcoin\b", r"\bcrypto\b",
    r"\brecipe\b", r"\bcook\b", r"\bmovie\b", r"\bsong\b", r"\bjoke\b",
    r"\bquantum physics\b", r"\bcapital of\b", r"\bhow old is\b", r"\bwho won\b",
    r"\bcalculate\b", r"\bsolve\b", r"\btranslate\b", r"\bhistory of\b",
    r"\bphilosophy\b", r"\bgpt\b", r"\bchatgpt\b", r"\bclaude\b", r"\bopenai\b"
]

def is_out_of_scope(query: str) -> bool:
    """
    Checks if query is asking about unrelated general knowledge or non-DeepVision topics.
    """
    q = query.lower().strip()
    
    # Check if query asks for general topics without mentioning DeepVision
    for pattern in GENERAL_KNOWLEDGE_TRIGGERS:
        if re.search(pattern, q):
            if "deepvision" not in q and "camera" not in q and "track" not in q and "detect" not in q and "alert" not in q:
                return True

    # Check for direct queries like "What is Python?", "Tell me today's news.", "Write a Java program."
    if q.startswith(("write ", "code ", "solve ", "translate ", "who is ", "what is ")) and not any(k in q for k in [
        "deepvision", "camera", "webcam", "yolo", "bytetrack", "track", "detection", "raw", "alert",
        "recording", "evidence", "anomaly", "loitering", "fullscreen", "mode", "ip webcam", "rtsp"
    ]):
        return True
        
    return False

def answer_query(user_query: str) -> str:
    """
    Processes user queries and returns a concise, grounded DeepVision response.
    Guarantees hard scope bounds and secret isolation.
    """
    if not user_query or not user_query.strip():
        return "How can I help you with DeepVision today? You can ask about camera setup, tracking modes, alerts, or recordings."

    query_clean = user_query.strip()
    q_lower = query_clean.lower()

    # Boundary check 1: Out of scope general knowledge questions
    if is_out_of_scope(query_clean):
        return OUT_OF_SCOPE_RESPONSE

    # Boundary check 2: Secret / password / credentials sniffing
    if any(secret_term in q_lower for secret_term in ["password", "secret_key", "api_key", ".env", "credential", "smtp_password", "token", "database_uri"]):
        return "For security reasons, system credentials, keys, and internal credentials are not accessible."

    # Intent Matching Grounded in DeepVision Knowledge:
    
    # 1. Add camera / connect camera
    if any(k in q_lower for k in ["how do i add a camera", "how to add a camera", "add camera", "new camera", "setup camera", "connect camera"]):
        if any(w in q_lower for w in ["phone", "android", "mobile"]):
            return DEEPVISION_KNOWLEDGE["connect_phone"]
        elif any(w in q_lower for w in ["webcam", "usb", "laptop"]):
            return DEEPVISION_KNOWLEDGE["connect_webcam"]
        return DEEPVISION_KNOWLEDGE["add_camera"]

    # 2. Connect phone / Android IP webcam
    if any(k in q_lower for k in ["phone", "android", "ip webcam", "connect my phone", "use my phone", "connect phone"]):
        return DEEPVISION_KNOWLEDGE["connect_phone"]

    # 3. Connect webcam / USB
    if any(k in q_lower for k in ["webcam", "usb camera", "laptop camera", "connect webcam"]):
        return DEEPVISION_KNOWLEDGE["connect_webcam"]

    # 4. Tracking mode / ByteTrack
    if "why" in q_lower and ("bytetrack" in q_lower or "track" in q_lower):
        return DEEPVISION_KNOWLEDGE["bytetrack"]
    elif any(k in q_lower for k in ["what is tracking mode", "tracking mode", "tracking view", "how does tracking work"]):
        return DEEPVISION_KNOWLEDGE["tracking_mode"]
    elif any(k in q_lower for k in ["what is bytetrack", "how does bytetrack work", "bytetrack"]):
        return DEEPVISION_KNOWLEDGE["bytetrack"]

    # 5. Detection mode / YOLO11
    if "why" in q_lower and "yolo" in q_lower:
        return DEEPVISION_KNOWLEDGE["yolo11"]
    elif any(k in q_lower for k in ["what is detection mode", "detection mode", "detection view", "how does detection work"]):
        return DEEPVISION_KNOWLEDGE["detection_mode"]
    elif any(k in q_lower for k in ["what is yolo", "yolo11", "yolo11n", "yolo model"]):
        return DEEPVISION_KNOWLEDGE["yolo11"]

    # 6. RAW mode
    if any(k in q_lower for k in ["raw mode", "what is raw mode", "raw stream", "passthrough"]):
        return DEEPVISION_KNOWLEDGE["raw_mode"]

    # 7. Track IDs & Global IDs
    if any(k in q_lower for k in ["track id", "track number", "what does track id mean", "track #"]):
        return DEEPVISION_KNOWLEDGE["track_id"]
    if any(k in q_lower for k in ["global id", "person-001", "item-001", "global identity"]):
        return DEEPVISION_KNOWLEDGE["global_id"]

    # 8. Recording video
    if any(k in q_lower for k in ["how do i start recording", "how to record", "start recording", "stop recording"]):
        return DEEPVISION_KNOWLEDGE["recording_start"]
    elif any(k in q_lower for k in ["what are recordings", "recordings", "recorded footage", "saved video"]):
        return DEEPVISION_KNOWLEDGE["recordings"]

    # 9. Alerts
    if any(k in q_lower for k in ["how do alerts work", "what are alerts", "alert inbox", "security alerts"]):
        return DEEPVISION_KNOWLEDGE["alerts"]

    # 10. Anomalies / Supported anomalies
    if any(k in q_lower for k in ["what anomalies", "supported anomalies", "anomaly types", "what can deepvision detect", "anomalies does deepvision support", "anomaly rules"]):
        return DEEPVISION_KNOWLEDGE["anomalies"]
    if any(k in q_lower for k in ["murder", "weapon", "fight", "assault", "gun", "knife", "unsupported"]):
        return "DeepVision does not support violent crime or weapons detection. " + DEEPVISION_KNOWLEDGE["unsupported_features"]

    # 11. Evidence
    if any(k in q_lower for k in ["evidence clip", "what is evidence", "evidence video", "how to open evidence", "snapshot"]):
        return DEEPVISION_KNOWLEDGE["evidence"]

    # 12. Troubleshooting / Offline
    if any(k in q_lower for k in ["offline", "why is my camera offline", "troubleshoot", "camera error", "not connecting", "cannot connect"]):
        return DEEPVISION_KNOWLEDGE["camera_offline"]

    # 13. Camera LIVE vs AI RUNNING
    if any(k in q_lower for k in ["camera live", "ai running", "live vs running"]):
        return DEEPVISION_KNOWLEDGE["camera_live_vs_ai"]

    # 14. Fullscreen
    if any(k in q_lower for k in ["fullscreen", "full screen", "how to use fullscreen", "expand video"]):
        return DEEPVISION_KNOWLEDGE["fullscreen"]

    # 15. What is DeepVision
    if any(k in q_lower for k in ["what is deepvision", "about deepvision", "what does deepvision do"]):
        return DEEPVISION_KNOWLEDGE["what_is_deepvision"]

    # Default friendly fallback if query mentions cameras or DeepVision generally
    if any(k in q_lower for k in ["camera", "video", "deepvision", "security", "stream", "feed", "alert", "monitor"]):
        return (
            "DeepVision provides real-time surveillance with RAW, Detection (YOLO11), and Tracking (ByteTrack) modes. "
            "You can manage cameras, configure alerts, capture MP4 recordings, and review evidence clips. "
            "What specific feature would you like help with?"
        )

    # Strict fallback for anything else
    return OUT_OF_SCOPE_RESPONSE