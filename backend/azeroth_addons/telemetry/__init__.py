"""Diagnostics and telemetry.

Two layers, deliberately separated:

* :mod:`journal` - an always-on, bounded, **redacted** error journal on disk.
  Nothing leaves the device.
* :mod:`reporter` - strictly opt-in forwarding of journal entries to an
  endpoint the user configures. Disabled by default, and the exact payload is
  previewable before it is ever switched on.
"""
