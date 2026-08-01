"""Thin reporting process entry point.

Strategy definitions live in ``strategies/``. Generic paper-outcome and
rendering infrastructure lives in ``reporting/``. This core entry point contains
no strategy thresholds, entry rules, exit rules, or strategy identifiers.
"""
from reporting.engine import main

if __name__ == "__main__":
    main()
