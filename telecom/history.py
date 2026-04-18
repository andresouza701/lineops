"""Backward-compatible history model export.

This module intentionally re-exports the canonical model declared in
``telecom.models`` to avoid duplicate model registrations.
"""

from telecom.models import PhoneLineHistory

__all__ = ["PhoneLineHistory"]
