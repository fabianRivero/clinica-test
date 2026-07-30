#!/usr/bin/env python3
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    # Ensure the virtualenv's site-packages is on the import path even
    # if the user invoked `manage.py` without first running
    # `source env/bin/activate` (some shells / IDEs lose the
    # activation state). This makes `python manage.py ...` work
    # directly when called from this directory.
    venv_site = Path(__file__).resolve().parent / "env" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    if venv_site.is_dir() and str(venv_site) not in sys.path:
        sys.path.insert(0, str(venv_site))

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
