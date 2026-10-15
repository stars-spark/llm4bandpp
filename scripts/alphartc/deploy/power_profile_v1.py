# -*- coding: utf-8 -*-
"""Set the platform power profile with powerprofilesctl and read back the active one; called between batches, before the scheduler starts.
A failed switch raises nothing: ensure() returns the requested and the actual profile.
"""
import subprocess
from pathlib import Path


def current():
    try: return Path("/sys/firmware/acpi/platform_profile").read_text().strip()
    except OSError: return None


def ensure(profile="performance"):
    if current() != profile:
        subprocess.run(["powerprofilesctl", "set", profile], capture_output=True, text=True, timeout=30)
    return {"requested": profile, "actual": current()}
