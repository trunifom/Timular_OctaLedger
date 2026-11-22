"""Public holidays from the optional ``holidays`` package (offline, MIT).

Install with ``pip install octaledger[holidays]``. Without the package no holidays are known
and the target working time simply has no public-holiday reduction; the user can still enter
holidays as absences. Regional and half holidays differ between companies, so an absence
always overrides this list.
"""

from __future__ import annotations

import importlib.util
import logging
from datetime import date

logger = logging.getLogger(__name__)


def holidays_available() -> bool:
    """Whether the optional package is installed."""
    return importlib.util.find_spec("holidays") is not None


def holiday_dates(region: str, first: date, last: date) -> frozenset[date]:
    """Public holidays of ``region`` (``CC`` or ``CC-SUB``) between two dates, inclusive.

    Returns an empty set when no region is set, the package is missing or the region is
    unknown (logged, never raised).
    """
    if not region or not holidays_available():
        return frozenset()
    country, _, subdiv = region.partition("-")
    try:
        import holidays  # type: ignore[import-not-found,unused-ignore]

        calendar = holidays.country_holidays(
            country,
            subdiv=subdiv or None,
            years=range(first.year, last.year + 1),
        )
    except Exception:
        logger.warning("Holidays for %s are not available", region, exc_info=True)
        return frozenset()
    return frozenset(d for d in calendar if first <= d <= last)
