"""Stable entry point for the versioned SoftMetadata UI script."""

from pathlib import Path
import runpy


UI_SCRIPT = Path(__file__).with_name("SoftMetadata_V0.1.py")


def main():
    # The versioned filename contains a dot, so it cannot be imported using
    # a normal Python module path in the console-script entry point.
    runpy.run_path(str(UI_SCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()
