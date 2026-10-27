"""
LAAP PSI Core runner.

Convenience entry point used by `laap_brain.psi_core_integration` to launch
the Python fallback as a subprocess.

Usage:
    python -m psi_core.runner <state_dir> [tick_ms]
"""
from psi_core.engine import main

if __name__ == "__main__":
    main()
