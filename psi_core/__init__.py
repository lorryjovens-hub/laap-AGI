"""
LAAP PSI Core — Python fallback implementation.

This package provides a pure-Python PSI (Psychological Synthetic Intelligence)
cycle that writes real-time cognitive state to `state/latest.json`. It is
designed to be API-compatible with the optional Rust PSI Core binary.

When the Rust binary is not available, `laap_brain.psi_core_integration` will
automatically fall back to launching this Python implementation.

Public API:
    from psi_core.engine import PsiCoreEngine
    engine = PsiCoreEngine(state_dir="./state")
    engine.start()
    ...
    engine.stop()
"""

from psi_core.engine import PsiCoreEngine

__all__ = ["PsiCoreEngine"]
