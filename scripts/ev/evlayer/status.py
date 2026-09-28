"""OCPI status normalisation. One place, so the uptime definition is auditable.

The published uptime number depends entirely on this mapping, so it is stated
once here and never re-derived inline. An audit report has to be able to show
exactly what was counted as working.
"""

UP = "UP"           # plugged-in-able right now
BUSY = "BUSY"       # working, but taken
DOWN = "DOWN"       # not working
UNKNOWN = "UNKNOWN"  # operator is not telling us

_MAP = {
    "AVAILABLE": UP,
    "CHARGING": UP,
    "OCCUPIED": BUSY,
    "RESERVED": BUSY,
    "BLOCKED": BUSY,
    "OUTOFORDER": DOWN,
    "INOPERATIVE": DOWN,
    "REMOVED": DOWN,
    "PLANNED": UNKNOWN,
    "UNKNOWN": UNKNOWN,
}

# A working charger is one a driver could use, or that someone else is using.
# DOWN counts against uptime. Prolonged UNKNOWN also counts against it: an
# operator that stops reporting is not demonstrating uptime.
WORKING = {UP, BUSY}

# How long UNKNOWN is tolerated before it is treated as downtime.
UNKNOWN_GRACE_MINUTES = 60


def normalise(ocpi_status: str | None) -> str:
    if not ocpi_status:
        return UNKNOWN
    return _MAP.get(ocpi_status.strip().upper(), UNKNOWN)


def is_working(ocpi_status: str | None) -> bool:
    return normalise(ocpi_status) in WORKING
