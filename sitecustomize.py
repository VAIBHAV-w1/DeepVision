import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
_dj_root = _root / "deepvision_django"
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if _dj_root.is_dir() and str(_dj_root) not in sys.path:
    sys.path.insert(0, str(_dj_root))

# Safe Python 3.14 Windows compatibility shim
try:
    import markupsafe
    from markupsafe._native import _escape_inner
    markupsafe._escape_inner = _escape_inner
except Exception:
    pass

