#!/usr/bin/env python
"""Root proxy for Django's command-line utility for administrative tasks."""
import os
import sys

def main():
    """Run administrative tasks."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    django_dir = os.path.join(root_dir, 'deepvision_django')
    # Ensure the project's dedicated venv is always used
    venv_py_win = os.path.join(root_dir, "venv", "Scripts", "python.exe")
    venv_py_posix = os.path.join(root_dir, "venv", "bin", "python")
    target_py = venv_py_win if os.path.exists(venv_py_win) else (venv_py_posix if os.path.exists(venv_py_posix) else None)
    if target_py and sys.prefix == sys.base_prefix and os.path.abspath(sys.executable) != os.path.abspath(target_py):
        import subprocess
        result = subprocess.run([target_py] + sys.argv)
        sys.exit(result.returncode)

    if django_dir not in sys.path:
        sys.path.insert(0, django_dir)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(root_dir, '.env'))
    except ImportError:
        pass

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
