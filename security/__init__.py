"""Security & Privacy subsystem for JARVIS (additive package).

Nothing in this package replaces existing JARVIS behaviour.  The manager is
created once at startup; every feature is OFF / unconfigured by default so an
upgrade changes nothing until the user opts in through the Security overlay
or the remote dashboard.
"""

_manager = None


def get_manager():
    """Return the process-wide SecurityManager (created on first use)."""
    global _manager
    if _manager is None:
        from .manager import SecurityManager
        _manager = SecurityManager()
    return _manager