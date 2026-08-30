"""Top-level launcher used by run.bat and the PyInstaller build."""
import sys

from app.main import main

if __name__ == '__main__':
    sys.exit(main())
