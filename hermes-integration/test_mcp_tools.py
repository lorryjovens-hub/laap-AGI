"""Test LAAP MCP server tools without Hermes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp_server"))
sys.path.insert(0, str(ROOT / "aris_brain"))

from laap_mcp_server import (
    laap_cognitive_state,
    laap_recall_memory,
    laap_express,
)

print("=== laap_cognitive_state ===")
print(laap_cognitive_state("我想你了")[:400])

print("\n=== laap_recall_memory ===")
print(laap_recall_memory("我最喜欢喝什么", 3)[:400])

print("\n=== laap_express ===")
print(laap_express("我想你了")[:400])
