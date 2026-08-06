"""
LAAP AGI — Hermes Integration Module (Hermes能力复用层)

Connects LAAP AGI modules to Hermes infrastructure services:
  - LLM calls through Hermes's 20+ providers
  - Session persistence in Hermes's SQLite+FTS5 store
  - Skill generation → Hermes skill system
  - Tool access → Hermes's 51+ tool suite
  - Memory sync → Hermes persistent memory
  - Config access → Shared configuration

This module ensures LAAP AGI doesn't duplicate Hermes functionality
but instead REUSES it through clean adapters.

Architecture:
  ┌────────────────────────────────────────────┐
  │           AGI Core (brain)                  │
  │  ┌──────────────────────────────────────┐  │
  │  │  HermesIntegration (this file)        │  │
  │  │  ├── llm_call()    → Hermes Provider  │  │
  │  │  ├── sync_session()→ Hermes SessionDB │  │
  │  │  ├── save_skill()  → Hermes Skills    │  │
  │  │  ├── exec_tool()   → Hermes Tools     │  │
  │  │  ├── sync_memory() → Hermes Memory    │  │
  │  │  └── get_config()  → Hermes Config    │  │
  │  └──────────────────────────────────────┘  │
  └────────────────────────────────────────────┘
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Callable
import threading, logging, os, sys, time, json
from pathlib import Path

from laap.config.paths import get_hermes_root

logger = logging.getLogger("laap.agi.hermes")


class HermesIntegration:
    """
    AGI module that provides Hermes services to other AGI modules.

    Not a cognitive module itself — it's an INFRASTRUCTURE ADAPTER
    that gives the brain (LAAP) access to the body (Hermes).
    """

    def __init__(self, hermes_home: str = ""):
        self.hermes_home = hermes_home or self._detect_hermes()
        self.hermes_available = bool(self.hermes_home)
        self.created_at = time.time()

        # Service lazy refs
        self._bridge = None
        self._llm_fn = None

        # Stats
        self.total_llm_calls = 0
        self.total_syncs = 0

        if self.hermes_available:
            logger.info(f"HermesIntegration: connected to {self.hermes_home}")
        else:
            logger.warning("HermesIntegration: Hermes NOT available — LLM calls disabled")

    def _detect_hermes(self) -> str:
        """Detect Hermes installation."""
        root = get_hermes_root()
        if root is not None:
            run_agent = root / "run_agent.py"
            if run_agent.exists():
                return str(root)
            logger.warning(
                "HermesIntegration: HERMES_ROOT points to %s but run_agent.py is missing; "
                "Hermes integration disabled.",
                root,
            )
        else:
            logger.warning(
                "HermesIntegration: HERMES_ROOT not set and no Hermes installation found. "
                "Set HERMES_ROOT environment variable to enable Hermes integration."
            )
        return ""

    def _get_bridge(self):
        """Lazy init the unified bridge."""
        if self._bridge is None:
            try:
                from laap.hermes_bridge import UnifiedBridge
                self._bridge = UnifiedBridge.get_instance()
            except ImportError:
                self._bridge = None
        return self._bridge

    # ════════════════════════════════════════════════════════
    # LLM Access (最重要的能力)
    # ════════════════════════════════════════════════════════

    def llm_call(self, prompt: str, system: str = "",
                 model: str = None, max_tokens: int = 500) -> Dict[str, Any]:
        """
        Call LLM through Hermes.

        This is how CodeEvolution generates patches, how Autonomy makes
        decisions, and how Analogical engine reasons about patterns.
        """
        self.total_llm_calls += 1
        bridge = self._get_bridge()
        if bridge:
            return bridge.llm_call(prompt, system, model=model, max_tokens=max_tokens)

        # Fallback: try in-process Hermes
        try:
            if not self.hermes_available:
                return {"error": "no_llm", "text": ""}
            result = self._call_hermes_inprocess(prompt, system, max_tokens)
            return {"text": result, "success": True}
        except Exception as e:
            return {"error": str(e), "text": ""}

    def llm_generate_patch(self, target_description: str,
                           current_code: str) -> Optional[Dict[str, Any]]:
        """
        Generate a code patch using LLM.

        This is the function passed to CodeEvolution.PatchGenerator.
        """
        prompt = f"""You are a code optimization expert. Given this code:

```python
{current_code[:2000]}
```

Target: {target_description}

Generate an improved version. Return ONLY the improved code, no explanation.
If no improvement is needed, return the original code unchanged."""
        
        result = self.llm_call(prompt, system="You are a Python code optimizer. Return only code.", max_tokens=2000)
        if result.get("text"):
            return {"code": result["text"], "description": target_description, "type": "optimize"}
        return None

    def llm_generate_patch_for_target(self, target: Any) -> Optional[Dict[str, Any]]:
        """
        Wrapper for CodeTarget → llm_generate_patch.
        
        This is the bridge function passed to CodeEvolutionEngine's PatchGenerator.
        """
        from laap.agi.code_evolution import CodeTarget
        if not isinstance(target, CodeTarget):
            return None
        desc = f"{target.file_path}:{target.function_name} — {target.optimization_hint} (complexity={target.complexity})"
        return self.llm_generate_patch(desc, target.current_code)

    def _call_hermes_inprocess(self, prompt: str, system: str = "",
                                max_tokens: int = 500) -> str:
        """Try in-process Hermes call (when running inside Hermes)."""
        try:
            sys.path.insert(0, self.hermes_home)
            from run_agent import AIAgent
            agent = AIAgent(model="", skip_context_files=True)
            if system:
                # Inject system message
                agent._extra_system_prompt = system
            result = agent.chat(prompt)
            return str(result)[:max_tokens]
        except Exception as e:
            return f"[LLM unavailable: {e}]"

    # ════════════════════════════════════════════════════════
    # Session Sync
    # ════════════════════════════════════════════════════════

    def sync_agi_state(self, agent_name: str,
                       state: Dict[str, Any]) -> bool:
        """Sync AGI state to Hermes session DB."""
        self.total_syncs += 1
        bridge = self._get_bridge()
        if bridge:
            return bridge.sync_session(agent_name, {
                "module_count": state.get("modules", 0),
                "uptime": time.time() - self.created_at,
                **state,
            })
        return False

    def load_agi_state(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Load AGI state from Hermes session DB."""
        bridge = self._get_bridge()
        if bridge:
            return bridge.load_session_state(agent_name)
        return None

    # ════════════════════════════════════════════════════════
    # Skill Pipeline
    # ════════════════════════════════════════════════════════

    def save_skill(self, name: str, domain: str,
                   steps: List[str], success_rate: float = 0.5,
                   description: str = "") -> bool:
        """Save an evolution-discovered pattern as a Hermes skill."""
        bridge = self._get_bridge()
        if bridge:
            result = bridge.propose_skill(name, domain, steps, success_rate, description)
            return result.get("success", False)
        return False

    # ════════════════════════════════════════════════════════
    # Tool Access
    # ════════════════════════════════════════════════════════

    def execute_tool(self, tool_name: str,
                     args: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a Hermes tool from AGI modules."""
        bridge = self._get_bridge()
        if bridge:
            return bridge.execute_tool(tool_name, args)
        return {"success": False, "error": "Bridge unavailable"}

    def list_tools(self) -> List[str]:
        """List available Hermes tools."""
        bridge = self._get_bridge()
        if bridge:
            return bridge.list_available_tools()
        return []

    # ════════════════════════════════════════════════════════
    # Config
    # ════════════════════════════════════════════════════════

    def get_config(self, key: str, default: Any = None) -> Any:
        """Read Hermes config."""
        bridge = self._get_bridge()
        if bridge:
            return bridge.get_hermes_config(key, default)
        return default

    # ════════════════════════════════════════════════════════
    # Stats
    # ════════════════════════════════════════════════════════

    def stats(self) -> Dict[str, Any]:
        return {
            "hermes_available": self.hermes_available,
            "hermes_home": self.hermes_home,
            "llm_calls": self.total_llm_calls,
            "state_syncs": self.total_syncs,
            "uptime_seconds": time.time() - self.created_at,
        }


def integrate_hermes(agent) -> HermesIntegration:
    """Attach Hermes integration to AGI agent."""
    hi = HermesIntegration()
    agent.hermes = hi
    logger.info(f"HermesIntegration attached to {getattr(agent, 'name', 'agent')}")
    return hi
