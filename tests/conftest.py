"""Add the repo root to sys.path so tests can `import carbonlight`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
