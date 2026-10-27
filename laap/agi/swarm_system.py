"""
LAAP AGI — Advanced Swarm Collaboration System (蜂群协作系统)

Beyond centralized task distribution. Five collaboration patterns:

  1. Auction Market    — Agents BID on tasks; market finds optimal allocation
  2. Swarm Formation   — Multiple agents attack ONE task simultaneously
  3. Hive Mind         — Shared consciousness/context across all agents
  4. Collective Graph  — Knowledge learned by one agent → all benefit
  5. Consensus Engine  — N-of-M agreement for high-stakes code changes

Key advantage over CentralBrain:
  CentralBrain: Commander decides → soldiers execute (top-down)
  Swarm:        Market decides → agents self-organize (bottom-up)
  
  Result: No single point of failure, naturally load-balanced,
          agents that "want" tasks do them better.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from enum import Enum
import time, logging, threading, uuid, heapq, math, json, os, random
from collections import defaultdict, deque

logger = logging.getLogger("laap.agi.swarm")


# ════════════════════════════════════════════════════════════
# 1. Auction Market Engine
# ════════════════════════════════════════════════════════════

class BidStrategy(str, Enum):
    AGGRESSIVE = "aggressive"     # Always bid high to win
    CONSERVATIVE = "conservative"  # Bid only when confident
    BALANCED = "balanced"         # Weighted by capability+load
    OPPORTUNISTIC = "opportunistic" # Bid on high-value, skip low-value


@dataclass
class AuctionTask:
    task_id: str
    description: str
    required_capabilities: List[str] = field(default_factory=list)
    base_value: float = 1.0       # How valuable completing this is
    deadline: float = 0.0         # Unix timestamp, 0 = no deadline
    complexity: float = 0.5       # 0.0-1.0 estimated difficulty
    min_agents: int = 1           # How many agents needed
    max_agents: int = 5           # Max agents (for swarm tasks)
    status: str = "open"          # open, bidding, awarded, done
    awarded_to: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    auction_end: float = 0.0


@dataclass
class Bid:
    agent_id: str
    task_id: str
    amount: float                 # Bid amount (higher = more "want")
    confidence: float = 0.5       # How confident in completing
    estimated_minutes: float = 5.0
    strategy: BidStrategy = BidStrategy.BALANCED
    timestamp: float = field(default_factory=time.time)

    @property
    def effective_bid(self) -> float:
        """Bid adjusted by confidence: confident agents get discount."""
        return self.amount * (0.5 + self.confidence * 0.5)


class AuctionMarket:
    """
    Decentralized task allocation through bidding.

    Agents don't wait to be assigned — they SEE tasks and BID.
    The market naturally:
      - Routes tasks to most capable agents (they bid highest)
      - Balances load (busy agents can't bid high)
      - Prioritizes urgent tasks (deadline pressure increases bids)
    """

    AUCTION_DURATION = 3.0  # seconds bidding window

    def __init__(self):
        self.tasks: Dict[str, AuctionTask] = {}       # open auctions
        self.bids: Dict[str, List[Bid]] = defaultdict(list)  # task_id → bids
        self.agent_credit: Dict[str, float] = defaultdict(lambda: 100.0)  # agent → credit
        self.completed_auctions: List[Dict] = []
        self.total_volume = 0.0     # Total value traded
        self._lock = threading.Lock()

    def list_task(self, description: str, required_capabilities: List[str] = None,
                  base_value: float = 1.0, deadline: float = 0.0,
                  complexity: float = 0.5, min_agents: int = 1,
                  max_agents: int = 5) -> AuctionTask:
        """Put a task on the auction board."""
        task = AuctionTask(
            task_id=str(uuid.uuid4())[:8],
            description=description,
            required_capabilities=required_capabilities or [],
            base_value=base_value,
            deadline=deadline,
            complexity=complexity,
            min_agents=min_agents,
            max_agents=max_agents,
            status="open",
            auction_end=time.time() + self.AUCTION_DURATION,
        )
        with self._lock:
            self.tasks[task.task_id] = task
        return task

    def bid(self, agent_id: str, task_id: str, bid_amount: float,
            confidence: float = 0.5, estimated_minutes: float = 5.0,
            strategy: BidStrategy = BidStrategy.BALANCED,
            agent_credit: float = 100.0) -> Tuple[bool, str]:
        """Agent places a bid on a task. Returns (accepted, reason)."""
        with self._lock:
            if task_id not in self.tasks:
                return False, "Task not found"
            task = self.tasks[task_id]
            if task.status != "open":
                return False, f"Auction closed: {task.status}"

            # Check agent credit
            credit = self.agent_credit.get(agent_id, 100.0)
            if bid_amount > credit * 0.5:  # Can't bid more than 50% of credit
                return False, f"Bid {bid_amount} exceeds 50% of credit {credit}"

            # Compute effective bid (adjusted by confidence)
            bid = Bid(
                agent_id=agent_id, task_id=task_id,
                amount=bid_amount, confidence=confidence,
                estimated_minutes=estimated_minutes, strategy=strategy,
            )
            self.bids[task_id].append(bid)
            return True, f"Bid placed: {bid.effective_bid:.2f}"

    def close_auction(self, task_id: str) -> Dict[str, Any]:
        """Close auction and award task to winner(s)."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return {"error": "Task not found"}

            task_bids = self.bids.get(task_id, [])
            if not task_bids:
                task.status = "open"  # Re-open if no bids
                return {"task_id": task_id, "awarded_to": [], "reason": "No bids"}

            # Sort by effective bid (highest first)
            task_bids.sort(key=lambda b: b.effective_bid, reverse=True)

            # Select winners (up to max_agents)
            winners = task_bids[:task.max_agents]
            winner_ids = [w.agent_id for w in winners]

            # Transfer credit: winners pay their bid
            total_paid = 0.0
            for bid in winners:
                payment = bid.amount * 0.1  # Pay 10% of bid as commitment
                self.agent_credit[bid.agent_id] -= payment
                total_paid += payment

            task.status = "awarded"
            task.awarded_to = winner_ids
            self.total_volume += total_paid

            self.completed_auctions.append({
                "task_id": task_id,
                "description": task.description,
                "winner": winner_ids[0] if winner_ids else "",
                "winners": winner_ids,
                "num_bids": len(task_bids),
                "winning_bid": winners[0].effective_bid if winners else 0,
                "total_paid": total_paid,
                "time": time.time(),
            })

            # Remove from active
            del self.tasks[task_id]
            del self.bids[task_id]

            return {
                "task_id": task_id,
                "awarded_to": winner_ids,
                "num_bids": len(task_bids),
                "winning_bid": winners[0].effective_bid if winners else 0,
                "total_paid": round(total_paid, 2),
            }

    def get_open_auctions(self) -> List[AuctionTask]:
        now = time.time()
        with self._lock:
            return [t for t in self.tasks.values()
                   if t.status == "open" and t.auction_end > now]

    def agent_portfolio(self, agent_id: str) -> Dict:
        with self._lock:
            won = sum(1 for a in self.completed_auctions if agent_id in a.get("winners", []))
            return {
                "agent_id": agent_id,
                "credit": round(self.agent_credit.get(agent_id, 100.0), 1),
                "auctions_won": won,
                "active_bids": sum(1 for bids in self.bids.values()
                                  for b in bids if b.agent_id == agent_id),
            }

    def stats(self) -> Dict:
        return {
            "open_auctions": len(self.tasks),
            "total_bids": sum(len(b) for b in self.bids.values()),
            "completed": len(self.completed_auctions),
            "total_volume": round(self.total_volume, 2),
            "agent_count": len(self.agent_credit),
        }


# ════════════════════════════════════════════════════════════
# 2. Swarm Formation Engine
# ════════════════════════════════════════════════════════════

class SwarmRole(str, Enum):
    LEAD = "lead"          # Coordinates, synthesizes
    EXPLORER = "explorer"  # Tries different approaches
    CRITIC = "critic"      # Finds flaws, edge cases
    IMPLEMENTER = "implementer"  # Writes code
    VERIFIER = "verifier"  # Tests, validates


@dataclass
class SwarmMember:
    agent_id: str
    role: SwarmRole
    status: str = "active"
    contribution: str = ""


@dataclass
class Swarm:
    swarm_id: str
    task_description: str
    members: List[SwarmMember] = field(default_factory=list)
    state: str = "forming"   # forming, brainstorming, executing, reviewing, done
    collective_context: str = ""  # Shared understanding
    approaches: List[str] = field(default_factory=list)  # Different solution paths
    best_solution: str = ""
    created_at: float = field(default_factory=time.time)


class SwarmOrchestrator:
    """
    Forms temporary swarms for complex tasks.

    Instead of one agent doing everything, a swarm:
      - Explorer agents try DIFFERENT approaches simultaneously
      - Critic agents find flaws in each approach
      - Lead agent synthesizes best parts of all approaches
      - Implementer builds the final solution
      - Verifier tests it

    Result: parallel exploration + consensus synthesis = better solutions.
    """

    SWARM_TIMEOUT = 300  # 5 minutes max per swarm

    def __init__(self):
        self.swarms: Dict[str, Swarm] = {}
        self.completed_swarms: List[Dict] = []
        self.total_swarms = 0
        self._lock = threading.Lock()

    def form_swarm(self, task_description: str, agents: List[Dict],
                   complexity: float = 0.5) -> Swarm:
        """
        Form a swarm from available agents.

        agents: [{"id": "xxx", "capabilities": [...], "role": "coder"}, ...]
        """
        self.total_swarms += 1

        # Assign roles based on capabilities
        role_assignments = self._assign_roles(agents)

        swarm = Swarm(
            swarm_id=str(uuid.uuid4())[:8],
            task_description=task_description,
            members=[
                SwarmMember(agent_id=a["id"], role=role)
                for a, role in role_assignments
            ],
        )

        with self._lock:
            self.swarms[swarm.swarm_id] = swarm

        return swarm

    def share_approach(self, swarm_id: str, agent_id: str,
                       approach: str) -> bool:
        """An agent shares its solution approach with the swarm."""
        with self._lock:
            swarm = self.swarms.get(swarm_id)
            if not swarm:
                return False
            swarm.approaches.append(f"[{agent_id}]: {approach}")
            swarm.state = "brainstorming"
            return True

    def critique(self, swarm_id: str, agent_id: str,
                 approach_index: int, flaw: str) -> bool:
        """Critic finds a flaw in an approach."""
        with self._lock:
            swarm = self.swarms.get(swarm_id)
            if not swarm or approach_index >= len(swarm.approaches):
                return False
            swarm.approaches[approach_index] += f" [FLAW({agent_id}): {flaw}]"
            return True

    def synthesize(self, swarm_id: str, lead_agent_id: str) -> Dict:
        """Lead agent synthesizes best solution from all approaches."""
        with self._lock:
            swarm = self.swarms.get(swarm_id)
            if not swarm:
                return {"error": "Swarm not found"}

            swarm.state = "executing"
            swarm.best_solution = (
                f"Synthesized from {len(swarm.approaches)} approaches "
                f"by lead {lead_agent_id}"
            )

            return {
                "swarm_id": swarm_id,
                "num_approaches": len(swarm.approaches),
                "synthesis": swarm.best_solution,
                "members": len(swarm.members),
            }

    def complete_swarm(self, swarm_id: str, result: str = "",
                       success: bool = True):
        """Dissolve swarm after task completion."""
        with self._lock:
            swarm = self.swarms.pop(swarm_id, None)
            if not swarm:
                return

            swarm.state = "done"
            self.completed_swarms.append({
                "swarm_id": swarm_id,
                "task": swarm.task_description[:100],
                "members": len(swarm.members),
                "approaches": len(swarm.approaches),
                "success": success,
                "duration": time.time() - swarm.created_at,
            })

    def _assign_roles(self, agents: List[Dict]) -> List[Tuple[Dict, SwarmRole]]:
        """Assign roles to agents based on their capabilities."""
        # Sort agents: most capable first
        scored = []
        for a in agents:
            caps = a.get("capabilities", [])
            score = len(caps)
            scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)

        assignments = []
        roles_needed = list(SwarmRole)
        role_idx = 0

        for _, agent in scored:
            if role_idx < len(roles_needed):
                assignments.append((agent, roles_needed[role_idx]))
                role_idx += 1
            else:
                # Extra agents become explorers
                assignments.append((agent, SwarmRole.EXPLORER))

        return assignments

    def stats(self) -> Dict:
        return {
            "active_swarms": len(self.swarms),
            "completed": len(self.completed_swarms),
            "total": self.total_swarms,
        }


# ════════════════════════════════════════════════════════════
# 3. Hive Mind — Shared Consciousness
# ════════════════════════════════════════════════════════════

@dataclass
class HiveSignal:
    """A piece of information broadcast to all agents."""
    signal_id: str
    source_agent: str
    signal_type: str  # insight, warning, discovery, status, request
    content: str
    confidence: float = 0.5
    tags: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    ttl: int = 60  # Time-to-live in seconds


class HiveMind:
    """
    Shared consciousness bus across all agents.

    When Agent A learns something, ALL agents immediately have that context.
    No agent works in isolation — the hive KNOWS what every member knows.
    """

    MAX_SIGNALS = 200  # Keep recent signals only

    def __init__(self):
        self.signals: deque = deque(maxlen=self.MAX_SIGNALS)
        self.knowledge_base: Dict[str, Dict] = {}  # topic → shared knowledge
        self.context_injections: Dict[str, str] = {}  # agent_id → context
        self.active_agents: Set[str] = set()
        self._lock = threading.Lock()

    def broadcast(self, source_agent: str, signal_type: str,
                  content: str, confidence: float = 0.5,
                  tags: List[str] = None, ttl: int = 60) -> HiveSignal:
        """Broadcast a signal to all agents in the hive."""
        signal = HiveSignal(
            signal_id=str(uuid.uuid4())[:8],
            source_agent=source_agent,
            signal_type=signal_type,
            content=content,
            confidence=confidence,
            tags=tags or [],
            ttl=ttl,
        )
        with self._lock:
            self.signals.append(signal)

            # Update knowledge base
            for tag in signal.tags:
                if tag not in self.knowledge_base:
                    self.knowledge_base[tag] = {
                        "last_content": content,
                        "confidence": confidence,
                        "sources": [],
                        "updated_at": time.time(),
                    }
                kb_entry = self.knowledge_base[tag]
                if source_agent not in kb_entry["sources"]:
                    kb_entry["sources"].append(source_agent)
                if confidence > kb_entry["confidence"]:
                    kb_entry["confidence"] = confidence
                    kb_entry["last_content"] = content
                    kb_entry["updated_at"] = time.time()

        return signal

    def get_context(self, agent_id: str, max_signals: int = 10) -> str:
        """
        Get the current hive context for an agent.
        This is what the agent "knows" from the collective.
        """
        with self._lock:
            now = time.time()
            relevant = [s for s in self.signals
                       if s.source_agent != agent_id
                       and now - s.timestamp < s.ttl]

            # Prioritize: warnings > discoveries > insights > status
            priority = {"warning": 0, "discovery": 1, "insight": 2, "status": 3, "request": 4}
            relevant.sort(key=lambda s: priority.get(s.signal_type, 5))

            lines = ["[HIVE CONTEXT]"]
            for s in relevant[:max_signals]:
                lines.append(
                    f"[{s.signal_type.upper()}] {s.source_agent}: {s.content[:120]} "
                    f"(conf={s.confidence:.0%})"
                )

            return "\n".join(lines) if len(lines) > 1 else "[HIVE: No active signals]"

    def query_knowledge(self, topic: str) -> Optional[Dict]:
        """Query the collective knowledge base."""
        return self.knowledge_base.get(topic)

    def register_agent(self, agent_id: str):
        with self._lock:
            self.active_agents.add(agent_id)

    def unregister_agent(self, agent_id: str):
        with self._lock:
            self.active_agents.discard(agent_id)

    def stats(self) -> Dict:
        return {
            "active_agents": len(self.active_agents),
            "signals": len(self.signals),
            "knowledge_topics": len(self.knowledge_base),
        }


# ════════════════════════════════════════════════════════════
# 4. Consensus Engine — Multi-Agent Agreement
# ════════════════════════════════════════════════════════════

@dataclass
class Proposal:
    proposal_id: str
    description: str
    risk_level: str = "medium"  # low, medium, high, critical
    proposed_by: str = ""
    votes_for: int = 0
    votes_against: int = 0
    required_approvals: int = 2
    voters: Dict[str, str] = field(default_factory=dict)  # agent_id → vote
    status: str = "pending"  # pending, voting, approved, rejected
    created_at: float = field(default_factory=time.time)


class ConsensusEngine:
    """
    Multi-agent agreement for high-stakes decisions.

    Before any CRITICAL code change:
      1. Proposal is created
      2. N-of-M agents must approve
      3. Veto from any primary agent blocks
      4. Consensus reached → change proceeds
      5. Deadlock → escalate to human
    """

    VETO_POWER_ROLES = {"primary", "reviewer"}

    def __init__(self):
        self.proposals: Dict[str, Proposal] = {}
        self.approved: List[Dict] = []
        self.rejected: List[Dict] = []
        self.total_proposals = 0

    def propose(self, description: str, proposed_by: str,
                risk_level: str = "medium",
                required_approvals: int = 2) -> Proposal:
        """Create a proposal for multi-agent voting."""
        self.total_proposals += 1
        proposal = Proposal(
            proposal_id=str(uuid.uuid4())[:8],
            description=description,
            risk_level=risk_level,
            proposed_by=proposed_by,
            required_approvals=required_approvals,
        )
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def vote(self, proposal_id: str, agent_id: str,
             vote: str, agent_role: str = "worker") -> str:
        """
        Cast a vote. Returns current status.

        vote: "approve" or "reject"
        agent_role: determines veto power
        """
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return "not_found"
        if proposal.status != "pending":
            return proposal.status

        proposal.voters[agent_id] = vote
        proposal.status = "voting"

        if vote == "approve":
            proposal.votes_for += 1
        else:
            proposal.votes_against += 1
            # Veto: primary/reviewer rejection kills proposal
            if agent_role in self.VETO_POWER_ROLES:
                proposal.status = "rejected"
                self.rejected.append({
                    "proposal_id": proposal_id,
                    "description": proposal.description[:100],
                    "vetoed_by": agent_id,
                    "time": time.time(),
                })
                del self.proposals[proposal_id]
                return "rejected (veto)"

        # Check consensus
        if proposal.votes_for >= proposal.required_approvals:
            proposal.status = "approved"
            self.approved.append({
                "proposal_id": proposal_id,
                "description": proposal.description[:100],
                "votes": proposal.votes_for,
                "time": time.time(),
            })
            del self.proposals[proposal_id]
            return "approved"

        return "voting"

    def stats(self) -> Dict:
        return {
            "pending": len(self.proposals),
            "approved": len(self.approved),
            "rejected": len(self.rejected),
            "total": self.total_proposals,
        }


# ════════════════════════════════════════════════════════════
# 5. SwarmSystem — Unified Interface
# ════════════════════════════════════════════════════════════

class SwarmSystem:
    """
    Complete advanced collaboration system.

    Wires together: Auction Market + Swarm Formation + Hive Mind + Consensus.

    Workflow:
      1. Task arrives → listed on Auction Market
      2. Agents bid → best agent(s) win
      3. Complex tasks → Swarm formed with role assignment
      4. During work → Hive Mind shares all discoveries
      5. Before deployment → Consensus vote required (if high-risk)
      """

    def __init__(self):
        self.market = AuctionMarket()
        self.swarms = SwarmOrchestrator()
        self.hive = HiveMind()
        self.consensus = ConsensusEngine()

        self.total_tasks_processed = 0
        self.created_at = time.time()

    def process_task(self, description: str,
                     capabilities: List[str] = None,
                     complexity: float = 0.5,
                     risk_level: str = "medium",
                     available_agents: List[Dict] = None) -> Dict[str, Any]:
        """
        Full task processing pipeline.

        Returns detailed execution plan.
        """
        self.total_tasks_processed += 1
        result = {"task_description": description, "steps": []}

        # Step 1: List on auction market
        task = self.market.list_task(
            description=description,
            required_capabilities=capabilities,
            complexity=complexity,
            max_agents=3 if complexity > 0.6 else 1,
        )
        result["auction_task_id"] = task.task_id
        result["steps"].append({"step": "listed_on_market", "task_id": task.task_id})

        # Step 2: Simulate bidding from available agents
        if available_agents:
            for agent in available_agents:
                agent_caps = agent.get("capabilities", [])
                match_score = self._cap_match(capabilities or [], agent_caps)
                if match_score > 0:
                    bid_amount = match_score * task.base_value * (0.5 + random.random() * 0.5)
                    self.market.bid(
                        agent["id"], task.task_id,
                        bid_amount=min(bid_amount, 50.0),
                        confidence=match_score,
                        estimated_minutes=5 + complexity * 20,
                    )

        # Step 3: Close auction
        auction_result = self.market.close_auction(task.task_id)
        result["auction"] = auction_result
        result["steps"].append({"step": "auction_closed", "winners": auction_result.get("awarded_to", [])})

        # Step 4: If complex, form swarm
        if complexity > 0.5 and auction_result.get("awarded_to"):
            matching_agents = [a for a in available_agents or []
                             if a["id"] in auction_result["awarded_to"]]
            if len(matching_agents) >= 2:
                swarm = self.swarms.form_swarm(description, matching_agents, complexity)
                result["swarm_id"] = swarm.swarm_id
                result["steps"].append({
                    "step": "swarm_formed",
                    "swarm_id": swarm.swarm_id,
                    "members": [{"id": m.agent_id, "role": m.role.value}
                               for m in swarm.members],
                })

        # Step 5: If high risk, start consensus
        if risk_level in ("high", "critical"):
            winner = auction_result.get("awarded_to", [""])[0] if auction_result.get("awarded_to") else ""
            proposal = self.consensus.propose(
                description=f"Deploy: {description}",
                proposed_by=winner or "system",
                risk_level=risk_level,
                required_approvals=2 if risk_level == "high" else 3,
            )
            result["consensus_proposal_id"] = proposal.proposal_id
            result["steps"].append({"step": "consensus_required", "proposal_id": proposal.proposal_id})

        # Step 6: Broadcast to hive
        self.hive.broadcast(
            source_agent="swarm_system",
            signal_type="discovery" if complexity > 0.5 else "status",
            content=f"Task processed: {description[:80]}",
            tags=capabilities or ["general"],
        )

        return result

    def _cap_match(self, required: List[str], available: List[str]) -> float:
        if not required: return 0.5
        if not available: return 0.0
        matches = sum(1 for r in required
                     for a in available
                     if r.lower() in a.lower() or a.lower() in r.lower())
        return matches / len(required)

    def get_unified_status(self) -> Dict[str, Any]:
        return {
            "market": self.market.stats(),
            "swarms": self.swarms.stats(),
            "hive": self.hive.stats(),
            "consensus": self.consensus.stats(),
            "total_processed": self.total_tasks_processed,
            "uptime_seconds": time.time() - self.created_at,
        }


def integrate_swarm_system(agent) -> SwarmSystem:
    swarm = SwarmSystem()
    agent.swarm_system = swarm
    logger.info(f"SwarmSystem integrated into {getattr(agent, 'name', 'agent')}")
    return swarm
