#!/usr/bin/env python3
"""Compatibility entry point for the BCRP monitor."""

import sys

from bcrp_monitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
