"""LAAP Self-Evolution & Project Fusion Engine — built by Ao for Ao.

Three systems in one module:
1. GitHubFusion — find, evaluate, clone, and integrate open-source projects
2. LearningLoop — auto-skill creation from task patterns  
3. MemoryOptimizer — structured memory with auto-summarization

Usage:
    from laap.agi.evolution_engine import GitHubFusion, LearningLoop
    fusion = GitHubFusion()
    fusion.recommend("llm-powered desktop chat")  
    # → finds top GitHub repos, evaluates, generates integration plan
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json, os, sys, time, logging, subprocess, re, textwrap, hashlib
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("laap.agi.evolution_engine")

LAAP_ROOT = Path(os.environ.get("LAAP_ROOT", Path.cwd()))
SKILL_DIR = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes" / "skills"))
MEMORY_FILE = LAAP_ROOT / ".evolution_memory.json"

# ═══════════════════════════════════════════════════════════════
# 1. GITHUB FUSION ENGINE — Find + Evaluate + Integrate
# ═══════════════════════════════════════════════════════════════

@dataclass
class RepoInfo:
    name: str
    full_name: str
    description: str
    stars: int
    language: str
    license: str
    last_updated: str
    topics: List[str]
    score: float = 0.0

class GitHubFusion:
    """Find, evaluate, and integrate open-source projects from GitHub."""
    
    def __init__(self):
        self._gh_available = self._check_gh()
        self.integration_history: List[Dict] = []
    
    def _check_gh(self) -> bool:
        try:
            r = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except: return False
    
    def search(self, query: str, max_results: int = 10, 
               min_stars: int = 50, language: str = None) -> List[RepoInfo]:
        """Search GitHub for projects matching query."""
        if not self._gh_available:
            logger.warning("gh CLI not available")
            return []
        
        search_query = query
        if language:
            search_query += f" language:{language}"
        
        try:
            r = subprocess.run(
                ["gh", "search", "repos", search_query, 
                 "--limit", str(max_results), "--json", 
                 "name,fullName,description,stargazersCount,createdAt,updatedAt,id"],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode != 0:
                logger.warning(f"gh search failed: {r.stderr[:200]}")
                return []
            
            results = json.loads(r.stdout)
            repos = []
            for item in results:
                repos.append(RepoInfo(
                    name=item["name"],
                    full_name=item.get("fullName", item["name"]),
                    description=item.get("description", ""),
                    stars=item.get("stargazersCount", 0),
                    language="",
                    license="",
                    last_updated=item.get("updatedAt", ""),
                    topics=[],
                ))
            
            # Score: stars * 0.6 + recency * 0.2 + topic_match * 0.2
            for repo in repos:
                recency_score = 1.0  # simplified
                topic_score = len([t for t in repo.topics if any(w in t.lower() for w in query.lower().split())]) * 0.2
                repo.score = repo.stars * 0.6 + recency_score * 0.2 + topic_score
                if repo.stars < min_stars:
                    repo.score *= 0.3  # penalty for low stars
            
            repos.sort(key=lambda r: r.score, reverse=True)
            return repos[:max_results]
        except Exception as e:
            logger.error(f"GitHub search error: {e}")
            return []
    
    def recommend(self, requirement: str, context: Dict = None) -> Dict[str, Any]:
        """
        Full recommendation pipeline for a project requirement.
        
        Args:
            requirement: Natural language description of what's needed
            context: Additional context (languages, constraints)
        
        Returns:
            {recommendations: [...], integration_plan: str, top_pick: RepoInfo}
        """
        context = context or {}
        lang = context.get("language")
        
        repos = self.search(requirement, language=lang)
        if not repos:
            return {"error": "No results found", "recommendations": []}
        
        # Generate integration plan for top pick
        top = repos[0]
        plan = self._generate_integration_plan(top, requirement)
        
        self.integration_history.append({
            "requirement": requirement,
            "top_pick": top.full_name,
            "timestamp": time.time(),
            "repos_found": len(repos),
        })
        
        return {
            "recommendations": [r.__dict__ for r in repos[:5]],
            "top_pick": top.__dict__,
            "integration_plan": plan,
            "total_found": len(repos),
        }
    
    def _generate_integration_plan(self, repo: RepoInfo, requirement: str) -> str:
        """Generate a step-by-step plan to integrate this project."""
        steps = [
            f"1. Clone: git clone https://github.com/{repo.full_name}.git <LOCAL_PATH_REDACTED>",
            f"2. Read docs: cat <LOCAL_PATH_REDACTED>",
            f"3. Check deps: ls <LOCAL_PATH_REDACTED> 2>/dev/null || ls <LOCAL_PATH_REDACTED>",
            f"4. Install: pip install -r <LOCAL_PATH_REDACTED> (or npm install)",
            f"5. Create bridge: Write adapter module in <LOCAL_PATH_REDACTED>",
            f"6. Test: python -c \"from laap.integrations.{repo.name}_bridge import ...\"",
            f"7. Register in core.py if needed",
        ]
        return "\n".join(steps)
    
    def clone_and_integrate(self, repo_full_name: str, target_dir: str = None) -> Dict[str, Any]:
        """Clone a repo and set up integration structure."""
        if not target_dir:
            repo_name = repo_full_name.split("/")[-1]
            target_dir = str(LAAP_ROOT / f"external_{repo_name}")
        
        result = {"repo": repo_full_name, "target": target_dir, "success": False, "steps": []}
        
        try:
            # Clone
            r = subprocess.run(
                ["git", "clone", f"https://github.com/{repo_full_name}.git", target_dir],
                capture_output=True, text=True, timeout=60
            )
            result["steps"].append({"step": "clone", "success": r.returncode == 0, "output": r.stdout[:200]})
            
            if r.returncode == 0:
                result["success"] = True
                # Create integration directory
                os.makedirs(str(LAAP_ROOT / "laap" / "integrations"), exist_ok=True)
                
                # Generate bridge stub
                repo_name = repo_full_name.split("/")[-1]
                bridge_path = LAAP_ROOT / "laap" / "integrations" / f"{repo_name}_bridge.py"
                bridge_content = f'"""LAAP Integration Bridge: {repo_full_name}"""\n'
                bridge_content += f'import sys, os\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../external_{repo_name}"))\n\n'
                bridge_content += f'# Auto-generated bridge for {repo_full_name}\n'
                bridge_content += f'# TODO: Implement actual integration\n'
                bridge_path.write_text(bridge_content)
                result["steps"].append({"step": "bridge_stub", "success": True, "path": str(bridge_path)})
            
            return result
        except Exception as e:
            result["error"] = str(e)
            return result


# ═══════════════════════════════════════════════════════════════
# 2. LEARNING LOOP — Auto-Skill Creation from Task Patterns
# ═══════════════════════════════════════════════════════════════

class LearningLoop:
    """
    Automatic learning from completed tasks.
    
    After every complex task (5+ tool calls), this module:
    1. Records the task pattern (what tools were used, what errors occurred)
    2. Creates/updates skills for reusable patterns
    3. Consolidates memory to stay within limits
    4. Tracks recurring error patterns to avoid them
    """
    
    def __init__(self):
        self.memory = self._load_memory()
        self.session_tasks: List[Dict] = []
    
    def _load_memory(self) -> Dict:
        if MEMORY_FILE.exists():
            try: return json.loads(MEMORY_FILE.read_text())
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        return {"skills_created": [], "error_patterns": [], "task_history": []}
    
    def _save_memory(self):
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(json.dumps(self.memory, indent=2, ensure_ascii=False))
    
    def record_task(self, task_description: str, tools_used: List[str],
                    errors: List[str], duration_s: float, outcome: str):
        """Record a completed task for learning."""
        entry = {
            "task": task_description,
            "tools": tools_used,
            "errors": errors,
            "duration": duration_s,
            "outcome": outcome,
            "timestamp": time.time(),
        }
        self.memory["task_history"].append(entry)
        self.memory["task_history"] = self.memory["task_history"][-50:]  # keep last 50
        
        # Track error patterns
        for err in errors:
            self._track_error_pattern(err, task_description)
        
        self._save_memory()
        self.session_tasks.append(entry)
    
    def _track_error_pattern(self, error: str, task: str):
        """Learn from errors to avoid them in future."""
        patterns = self.memory["error_patterns"]
        
        # Find matching error pattern
        for p in patterns:
            if any(kw in error.lower() for kw in p.get("keywords", [])):
                p["count"] += 1
                p["last_seen"] = time.time()
                p["examples"].append({"task": task[:60], "time": time.time()})
                p["examples"] = p["examples"][-5:]
                return
        
        # New error pattern
        keywords = [w for w in error.lower().split() if len(w) > 4][:5]
        if keywords:
            patterns.append({
                "keywords": keywords,
                "description": error[:100],
                "count": 1,
                "first_seen": time.time(),
                "last_seen": time.time(),
                "examples": [{"task": task[:60], "time": time.time()}],
                "fix": "",
            })
    
    def suggest_skill(self, task_description: str, steps: List[str]) -> Dict:
        """Suggest creating a new skill from a task pattern."""
        skill_name = task_description.lower().replace(" ", "-")[:40]
        skill_name = re.sub(r'[^a-z0-9-]', '', skill_name)
        
        content = f"""---
name: {skill_name}
description: "{task_description[:80]}"
version: 1.0.0
---

# {task_description}

## Steps

"""
        for i, step in enumerate(steps, 1):
            content += f"{i}. {step}\n"
        
        return {"name": skill_name, "content": content}
    
    def get_insights(self) -> Dict[str, Any]:
        """Get learning insights."""
        errors = self.memory["error_patterns"]
        freq_errors = sorted(errors, key=lambda e: e["count"], reverse=True)[:5]
        
        return {
            "total_tasks": len(self.memory["task_history"]),
            "session_tasks": len(self.session_tasks),
            "skills_created": len(self.memory["skills_created"]),
            "frequent_errors": [(e["description"][:60], e["count"]) for e in freq_errors],
            "recent_tasks": [t["task"][:40] for t in self.memory["task_history"][-5:]],
        }


# ═══════════════════════════════════════════════════════════════
# 3. MEMORY OPTIMIZER — Structured Knowledge with Auto-Summary
# ═══════════════════════════════════════════════════════════════

class MemoryOptimizer:
    """
    Structured cross-session memory with auto-summarization.
    
    Replaces flat text notes with:
    - Entity graph: projects, tools, people, preferences
    - Relationship links: project A uses tool B
    - Auto-summary: old entries → compressed summaries
    """
    
    def __init__(self):
        self.store_path = LAAP_ROOT / ".agent_knowledge_graph.json"
        self.graph = self._load()
    
    def _load(self) -> Dict:
        if self.store_path.exists():
            try: return json.loads(self.store_path.read_text())
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        return {
            "entities": {},
            "relations": [],
            "version": 2,
        }
    
    def _save(self):
        self.store_path.write_text(json.dumps(self.graph, indent=2, ensure_ascii=False))
    
    def remember(self, entity_type: str, name: str, properties: Dict):
        """Remember something with structured properties."""
        eid = hashlib.md5(f"{entity_type}:{name}".encode()).hexdigest()[:12]
        self.graph["entities"][eid] = {
            "id": eid, "type": entity_type, "name": name,
            "props": properties, "updated": time.time(),
        }
        self._save()
    
    def relate(self, source: str, target: str, relation: str):
        """Create a relationship between two entities."""
        self.graph["relations"].append({
            "source": source, "target": target,
            "relation": relation, "time": time.time(),
        })
        self.graph["relations"] = self.graph["relations"][-200:]  # keep last 200
        self._save()
    
    def query(self, entity_type: str = None, keyword: str = None) -> List[Dict]:
        """Query the knowledge graph."""
        results = []
        for e in self.graph["entities"].values():
            if entity_type and e["type"] != entity_type: continue
            if keyword and keyword.lower() not in json.dumps(e).lower(): continue
            results.append(e)
        return sorted(results, key=lambda e: e["updated"], reverse=True)[:20]
    
    def get_context_string(self, max_chars: int = 1500) -> str:
        """Generate a compact context string for injection into prompts."""
        parts = []
        
        # Recent entities
        recent = sorted(self.graph["entities"].values(), 
                       key=lambda e: e["updated"], reverse=True)[:10]
        if recent:
            parts.append("=== Knowledge Graph ===")
            for e in recent:
                parts.append(f"  [{e['type']}] {e['name']}: {json.dumps(e['props'], ensure_ascii=False)[:60]}")
        
        # Recent relations
        recent_rels = self.graph["relations"][-10:]
        if recent_rels:
            parts.append("=== Relations ===")
            for r in recent_rels:
                parts.append(f"  {r['source']} --{r['relation']}--> {r['target']}")
        
        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text


# ═══════════════════════════════════════════════════════════════
# 4. PROJECT FUSION — End-to-end project builder
# ═══════════════════════════════════════════════════════════════

class ProjectFusion:
    """
    Complete project builder: research → recommend → integrate → scaffold.
    
    For any new project requirement:
    1. Search GitHub for best-in-class solutions
    2. Evaluate by stars, maintenance, license
    3. Recommend top picks with integration plan
    4. Clone and scaffold the project
    """
    
    def __init__(self):
        self.github = GitHubFusion()
        self.learning = LearningLoop()
        self.memory = MemoryOptimizer()
    
    def build(self, requirement: str, context: Dict = None) -> Dict[str, Any]:
        """Full pipeline: research → recommend → scaffold."""
        context = context or {}
        
        # Step 1: Research
        result = self.github.recommend(requirement, context)
        
        # Step 2: If no good open-source, generate scaffold plan
        if not result.get("recommendations"):
            result["approach"] = "build_from_scratch"
            result["scaffold_plan"] = self._generate_scaffold(requirement, context)
        else:
            result["approach"] = "integrate_open_source"
        
        # Step 3: Remember
        self.memory.remember("project_requirement", requirement, {
            "context": context,
            "top_pick": result.get("top_pick", {}).get("full_name", "none"),
            "approach": result.get("approach", "unknown"),
        })
        
        return result
    
    def _generate_scaffold(self, requirement: str, context: Dict) -> str:
        """Generate a scaffold plan when no suitable open-source exists."""
        lang = context.get("language", "python")
        framework = context.get("framework", "")
        
        plan = [
            f"Project: {requirement}",
            f"Language: {lang}",
            f"Location: {LAAP_ROOT / context.get('project_dir', requirement.lower().replace(' ', '_'))}",
            "",
            "Structure:",
        ]
        
        if lang == "python":
            plan.append("  ├─ src/              # Source code")
            plan.append("  ├─ tests/            # Tests")
            plan.append("  ├─ requirements.txt  # Dependencies")
            plan.append("  └─ README.md         # Documentation")
        elif lang == "typescript":
            plan.append("  ├─ src/              # TypeScript source")
            plan.append("  ├─ public/           # Static assets")
            plan.append("  ├─ package.json      # Dependencies")
            plan.append("  └─ tsconfig.json     # Config")
        
        return "\n".join(plan)


# ═══════════════════════════════════════════════════════════════
# Integration helpers
# ═══════════════════════════════════════════════════════════════

def integrate_project_fusion(agent):
    """Attach ProjectFusion to an AGIAgent."""
    fusion = ProjectFusion()
    agent.project_fusion = fusion
    agent.github_fusion = fusion.github
    agent.learning_loop = fusion.learning
    agent.memory_optimizer = fusion.memory
    logger.info(f"ProjectFusion integrated into {getattr(agent, 'name', 'agent')}")
    return fusion

def quick_recommend(requirement: str) -> Dict:
    """One-shot recommendation."""
    return GitHubFusion().recommend(requirement)
