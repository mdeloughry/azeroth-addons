"""Event names shared between the backend and the React frontend.

Kept in one place so a channel rename cannot silently break the UI.
"""

from __future__ import annotations

RUNTIME_STATUS = "az:runtime_status"
INSTALLATIONS_CHANGED = "az:installations_changed"
ADDONS_CHANGED = "az:addons_changed"
OPERATION = "az:operation"
ERROR = "az:error"

ALL_EVENTS = (RUNTIME_STATUS, INSTALLATIONS_CHANGED, ADDONS_CHANGED, OPERATION, ERROR)
