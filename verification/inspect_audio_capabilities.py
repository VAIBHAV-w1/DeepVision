import os
import sys

print("Python version:", sys.version)

# Check installed modules related to audio
audio_modules = ['pyaudio', 'sounddevice', 'soundfile', 'wave', 'moviepy', 'av', 'ffmpeg', 'pydub', 'pygame']
print("\nChecking audio modules:")
for mod in audio_modules:
    try:
        __import__(mod)
        print(f"  {mod}: INSTALLED")
    except ImportError:
        print(f"  {mod}: NOT installed")

# Check if ffmpeg binary exists in PATH or system
import shutil
ffmpeg_path = shutil.which('ffmpeg')
ffprobe_path = shutil.which('ffprobe')
print(f"\nFFmpeg in PATH: {ffmpeg_path}")
print(f"FFprobe in PATH: {ffprobe_path}")

# Check DirectShow / Windows Audio devices using powershell or ctypes/pywin32
import subprocess
try:
    cmd = 'powershell "Get-PnpDevice -Class Media | Select-Object FriendlyName, Status, InstanceId"'
    res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    print("\nWindows Media Devices:\n", res.stdout)
except Exception as e:
    print("Error querying devices:", e)

# Check an existing recording MP4 to see if it has audio
sample_files = [
    r"instance\evidence\camera_3\2026-09-26\alert_1291_clip.mp4",
    r"instance\recordings\camera_3\cam_3_rec_20260926_182709.mp4"
]
print("\nChecking sample files for audio:")
for s in sample_files:
    if os.path.exists(s):
        print(f"\nFile: {s} (size={os.path.getsize(s)} bytes)")
        # Check box structure of MP4 (look for trak, mdia, hdlr 'soun')
        with open(s, "rb") as f:
            data = f.read(50000)
            has_soun = b"soun" in data
            has_vide = b"vide" in data
            print(f"  Contains 'vide' atom: {has_vide}")
            print(f"  Contains 'soun' (audio) atom: {has_soun}")
    else:
        print(f"File not found: {s}")
