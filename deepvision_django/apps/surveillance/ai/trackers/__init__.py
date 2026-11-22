"""
Pure-NumPy / OpenCV Multi-Object Tracker Algorithms for DeepVision 4.0.

Implements verified upstream algorithmic formulations of:
  - ByteTrack (Zhang et al., ECCV 2022)
  - BoT-SORT with GMC & Appearance Re-ID (Aharon et al., 2022)
  - OC-SORT with ORU / OCM / OCR (Cao et al., CVPR 2023)

All assignment steps use Crouse (2016) modified Jonker-Volgenant linear sum
assignment in pure NumPy so Smart App Control (WinError 4551) never blocks
unsigned PyTorch/SciPy/LAP extensions on Windows 11.
"""

from apps.surveillance.ai.trackers.bytetrack_core import GenuineByteTracker
from apps.surveillance.ai.trackers.botsort_core import GenuineBotSortTracker
from apps.surveillance.ai.trackers.ocsort_core import GenuineOCSortTracker

__all__ = [
    "GenuineByteTracker",
    "GenuineBotSortTracker",
    "GenuineOCSortTracker",
]

