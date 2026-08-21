"""Thin health-reporting process entry point.

The legacy all-in-one outcome/reporting engine remains available as
``reporting.engine`` for audit and replay work.  Live health output uses the
small failure-isolated reporter so outcome calculations cannot freeze worker,
auth, CPU, memory, storage, or tape heartbeats.
"""
from reporting.health_engine import main

if __name__ == "__main__":
    main()
