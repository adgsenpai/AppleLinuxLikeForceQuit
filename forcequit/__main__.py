import argparse
import sys

from .ui import ForceQuitApplication


def main():
    parser = argparse.ArgumentParser(prog="force-quit", description="macOS-style Force Quit Applications panel")
    parser.add_argument("--shortcut-label", default="Super + Alt + Escape",
                        help="shortcut text shown at the bottom of the window")
    args, rest = parser.parse_known_args()
    return ForceQuitApplication(args.shortcut_label).run([sys.argv[0], *rest])


if __name__ == "__main__":
    sys.exit(main())
