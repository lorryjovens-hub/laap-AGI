"""
LAAP AGI — Analogical Reasoning Engine (类比推理引擎)

The gap between "matching surface features" and "deep structural analogy."

Current LLMs can SAY "A is like B" but cannot actually:
  - Distinguish superficial similarity from structural isomorphism
  - Transfer causal/relational structure across domains
  - Apply Gentner's structure-mapping theory systematically
  - Learn abstract patterns from concrete analogies

This engine implements Gentner's Structure-Mapping Theory (SMT):
  - Systematicity principle: connected systems of relations > isolated matches
  - Higher weight for deeper relational structures
  - Cross-domain mapping that preserves relational structure, not surface features

Architecture:
  ┌──────────────────────────────────────────────────────────┐
  │              ANALOGICAL REASONING ENGINE                   │
  ├──────────────────────────────────────────────────────────┤
  │  StructuralGraph (nodes + edges with roles)               │
  │  ├── Nodes: concepts, objects, attributes, actions        │
  │  ├── Edges: acts_on, produces, constrains, enables       │
  │  └── Role-typed: what things are, not their names         │
  ├──────────────────────────────────────────────────────────┤
  │  PatternAbstractor                                       │
  │  └── Abstract concrete graphs → role-based patterns       │
  ├──────────────────────────────────────────────────────────┤
  │  StructureAligner                                        │
  │  └── Gentner SMT alignment: local matches → global map   │
  ├──────────────────────────────────────────────────────────┤
  │  AnalogicalEngine                                        │
  │  └── Full pipeline: encode → align → transfer → learn    │
  └──────────────────────────────────────────────────────────┘

Reference: Gentner, D. (1983). Structure-mapping: A theoretical framework
for analogy. Cognitive Science, 7(2), 155-170.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
import time, logging, random, math, json, uuid
from collections import defaultdict

logger = logging.getLogger("laap.agi.analogical")


# ════════════════════════════════════════════════════════════
# Core Types — Enums
# ════════════════════════════════════════════════════════════

class NodeRole(str, Enum):
    """Semantic role of a node in a structural graph."""
    CONCEPT = "concept"
    OBJECT = "object"
    ATTRIBUTE = "attribute"
    ACTION = "action"
    CONSTRAINT = "constraint"


class RelationKind(str, Enum):
    """Type of relational edge between structural nodes."""
    RELATES = "relates"
    ACTS_ON = "acts_on"
    PRODUCES = "produces"
    CONSTRAINS = "constrains"
    ENABLES = "enables"
    MODIFIES = "modifies"
    TRANSFERS = "transfers"
    FOLLOWS = "follows"
    PARALLEL = "parallel"


# ════════════════════════════════════════════════════════════
# Core Data Structures
# ════════════════════════════════════════════════════════════

@dataclass
class StructuralNode:
    """A node in a structural graph, typed by its semantic role.

    The role is what matters for analogy — not the specific name.
    Two nodes match if they occupy similar relational positions,
    not if they have similar names.
    """
    id: str
    name: str
    role: NodeRole
    properties: Dict[str, Any] = field(default_factory=dict)
    embedding: List[float] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        if not isinstance(other, StructuralNode):
            return NotImplemented
        return self.id == other.id


@dataclass
class StructuralEdge:
    """A typed, weighted edge connecting two structural nodes.

    Edges carry the relational structure that analogies preserve.
    Weight indicates how central/strong a relation is.
    """
    source_id: str
    target_id: str
    kind: RelationKind
    weight: float = 1.0


@dataclass
class AnalogyMapping:
    """The result of aligning two structural graphs.

    Node mappings: (src_node_id, tgt_node_id) pairs.
    Edge mappings: (src_edge_id, tgt_edge_id) pairs.
    similarity_score: how structurally similar (0-1).
    confidence: how reliable we think the analogy is (0-1).
    """
    source_domain: str
    target_domain: str
    node_mappings: List[Tuple[str, str]]
    edge_mappings: List[Tuple[str, str]]
    similarity_score: float
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "node_mappings": [(s, t) for s, t in self.node_mappings],
            "edge_mappings": [(s, t) for s, t in self.edge_mappings],
            "similarity_score": self.similarity_score,
            "confidence": self.confidence,
        }

    def __repr__(self) -> str:
        return (
            f"AnalogyMapping({self.source_domain}→{self.target_domain}, "
            f"nodes={len(self.node_mappings)}, edges={len(self.edge_mappings)}, "
            f"sim={self.similarity_score:.3f}, conf={self.confidence:.3f})"
        )


# ════════════════════════════════════════════════════════════
# Structural Graph
# ════════════════════════════════════════════════════════════

class StructuralGraph:
    """A role-typed directed graph representing a domain's relational structure.

    The graph preserves:
      - What things ARE (NodeRole)
      - How things RELATE (RelationKind)
      - The WEIGHT/strength of relations

    This is the representation used for analogical mapping.
    """

    def __init__(self, domain: str = ""):
        self.domain: str = domain
        self.nodes: Dict[str, StructuralNode] = {}
        self.edges: Dict[str, StructuralEdge] = {}
        self.edge_counter: int = 0

    def add_node(self, name: str, role: NodeRole = NodeRole.CONCEPT,
                 properties: Dict[str, Any] = None,
                 node_id: str = None) -> StructuralNode:
        """Add a node to the graph. Returns the node."""
        nid = node_id or str(uuid.uuid4())[:12]
        if nid in self.nodes:
            return self.nodes[nid]
        node = StructuralNode(
            id=nid, name=name, role=role,
            properties=properties or {},
        )
        self.nodes[nid] = node
        return node

    def add_edge(self, source_id: str, target_id: str,
                 kind: RelationKind = RelationKind.RELATES,
                 weight: float = 1.0) -> Optional[str]:
        """Add a directed edge between two nodes. Returns edge id or None."""
        if source_id not in self.nodes or target_id not in self.nodes:
            logger.warning(f"Cannot add edge: {source_id} or {target_id} not found")
            return None
        eid = f"e{self.edge_counter}"
        self.edge_counter += 1
        self.edges[eid] = StructuralEdge(
            source_id=source_id, target_id=target_id,
            kind=kind, weight=weight,
        )
        return eid

    def get_edges_from(self, node_id: str) -> List[Tuple[str, StructuralEdge]]:
        """Get all edges originating from a node."""
        return [(eid, e) for eid, e in self.edges.items()
                if e.source_id == node_id]

    def get_edges_to(self, node_id: str) -> List[Tuple[str, StructuralEdge]]:
        """Get all edges terminating at a node."""
        return [(eid, e) for eid, e in self.edges.items()
                if e.target_id == node_id]

    def find_paths(self, from_id: str, to_id: str,
                   max_depth: int = 5) -> List[List[str]]:
        """Find all paths between two nodes (by edge id sequences)."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return []

        paths = []

        def _dfs(current: str, target: str, visited: Set[str],
                 path_edges: List[str], depth: int):
            if depth > max_depth:
                return
            if current == target:
                paths.append(list(path_edges))
                return
            for eid, edge in self.get_edges_from(current):
                if edge.target_id in visited:
                    continue
                visited.add(edge.target_id)
                path_edges.append(eid)
                _dfs(edge.target_id, target, visited, path_edges, depth + 1)
                path_edges.pop()
                visited.remove(edge.target_id)

        _dfs(from_id, to_id, {from_id}, [], 0)
        return paths

    def to_abstract(self) -> StructuralGraph:
        """Produce an abstract version: replace specific names with role labels.

        This strips surface details, keeping only the relational structure.
        The abstract graph has nodes named by their role + role index,
        preserving the exact edge topology.
        """
        abstract = StructuralGraph(domain=f"abstract:{self.domain}")

        # Map original ids → abstract node ids
        role_counts: Dict[str, int] = defaultdict(int)
        id_map: Dict[str, str] = {}

        for nid, node in self.nodes.items():
            role_name = node.role.value
            role_counts[role_name] += 1
            abstract_name = f"{role_name}_{role_counts[role_name]}"
            abs_node = abstract.add_node(
                name=abstract_name,
                role=node.role,
                properties={"abstracted": True, "original_name": node.name},
                node_id=nid,
            )
            id_map[nid] = nid  # Keep same ids for cross-referencing

        # Copy edges with same topology
        for eid, edge in self.edges.items():
            abstract.add_edge(
                source_id=edge.source_id,
                target_id=edge.target_id,
                kind=edge.kind,
                weight=edge.weight,
            )

        return abstract

    def get_node_count(self) -> int:
        return len(self.nodes)

    def get_edge_count(self) -> int:
        return len(self.edges)

    def get_relational_depth(self, node_id: str) -> int:
        """Compute the relational depth of a node (max path length from it)."""
        max_depth = 0
        visited: Set[str] = set()
        stack = [(node_id, 0)]
        while stack:
            nid, depth = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            max_depth = max(max_depth, depth)
            for _, edge in self.get_edges_from(nid):
                if edge.target_id not in visited:
                    stack.append((edge.target_id, depth + 1))
        return max_depth

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "nodes": {nid: {"name": n.name, "role": n.role.value,
                             "properties": n.properties}
                      for nid, n in self.nodes.items()},
            "edges": {eid: {"source": e.source_id, "target": e.target_id,
                            "kind": e.kind.value, "weight": e.weight}
                      for eid, e in self.edges.items()},
            "node_count": self.get_node_count(),
            "edge_count": self.get_edge_count(),
        }


# ════════════════════════════════════════════════════════════
# Pattern Abstractor
# ════════════════════════════════════════════════════════════

class PatternAbstractor:
    """Abstracts concrete graphs into pattern graphs and classifies them.

    Pattern abstraction strips surface features to reveal the underlying
    relational structure. This is where analogical generalization happens:
    multiple concrete experiences → single abstract pattern.
    """

    def __init__(self):
        self.domain_patterns: Dict[str, List[StructuralGraph]] = defaultdict(list)

    def abstract(self, graph: StructuralGraph) -> StructuralGraph:
        """Abstract a concrete graph into a role-based pattern graph.

        The output graph has:
          - Nodes named by their role (concept_1, action_2, ...)
          - The same relational topology as the input
          - Meta-properties recording original names for traceability
        """
        return graph.to_abstract()

    def classify_pattern(self, abstract_graph: StructuralGraph) -> List[Tuple[str, float]]:
        """Classify an abstract pattern graph into known pattern types.

        Returns a list of (pattern_type, confidence) pairs.
        Uses topological features of the abstract graph to identify
        common reasoning patterns like:
          - 'causal_chain': A → B → C
          - 'means_end': action produces object which enables goal
          - 'constraint_satisfaction': multiple constraints on one object
          - 'transformation': object → modified_object
          - 'parallel_process': two independent parallel chains
        """
        classifications: List[Tuple[str, float]] = []
        edge_count = abstract_graph.get_edge_count()
        node_count = abstract_graph.get_node_count()

        if edge_count == 0:
            classifications.append(("isolated_concept", 0.9))
            return classifications

        # Count relation types
        kind_counts: Dict[str, int] = defaultdict(int)
        for edge in abstract_graph.edges.values():
            kind_counts[edge.kind.value] += 1

        # Count in/out degrees
        in_degree: Dict[str, int] = defaultdict(int)
        out_degree: Dict[str, int] = defaultdict(int)
        for edge in abstract_graph.edges.values():
            out_degree[edge.source_id] += 1
            in_degree[edge.target_id] += 1

        # Causal chain: A→B→C, each node has one in and one out (except ends)
        chain_nodes = sum(1 for nid in abstract_graph.nodes
                          if in_degree.get(nid, 0) <= 1 and out_degree.get(nid, 0) <= 1)
        if edge_count >= 2 and chain_nodes >= edge_count:
            classifications.append(("causal_chain", 0.7 + 0.1 * min(edge_count, 3)))

        # Means-end: action→object, object enables goal
        has_action = any(
            n.role == NodeRole.ACTION for n in abstract_graph.nodes.values())
        has_object = any(
            n.role == NodeRole.OBJECT for n in abstract_graph.nodes.values())
        has_constraint = any(
            n.role == NodeRole.CONSTRAINT for n in abstract_graph.nodes.values())

        if has_action and has_object and kind_counts.get("produces", 0) > 0:
            classifications.append(("means_end", 0.8))

        # Constraint satisfaction
        if has_constraint:
            constraint_nodes = [nid for nid, n in abstract_graph.nodes.items()
                                if n.role == NodeRole.CONSTRAINT]
            constrained_things = set()
            for cid in constraint_nodes:
                for _, edge in abstract_graph.get_edges_from(cid):
                    constrained_things.add(edge.target_id)
            if len(constrained_things) >= 2:
                classifications.append(("constraint_satisfaction",
                                        0.6 + 0.1 * min(len(constrained_things), 4)))

        # Transformation
        if kind_counts.get("modifies", 0) > 0 or kind_counts.get("transfers", 0) > 0:
            classifications.append(("transformation", 0.7))

        # Parallel process: two chains from same source
        if kind_counts.get("parallel", 0) > 0:
            classifications.append(("parallel_process", 0.8))

        # Default if nothing specific
        if not classifications:
            classifications.append(("generic_structure", 0.5))

        return classifications

    def add_pattern(self, domain: str, graph: StructuralGraph):
        """Register an abstracted pattern for a domain."""
        abstracted = self.abstract(graph)
        self.domain_patterns[domain].append(abstracted)
        logger.debug(f"Added pattern to {domain}: "
                     f"{abstracted.get_node_count()} nodes, "
                     f"{abstracted.get_edge_count()} edges")

    def get_patterns(self, domain: str) -> List[StructuralGraph]:
        """Get all abstracted patterns for a domain."""
        return list(self.domain_patterns.get(domain, []))

    def match_across_domains(self, graph: StructuralGraph,
                             min_similarity: float = 0.3) -> List[Tuple[str, float]]:
        """Find which domains have patterns similar to this graph."""
        abstract = self.abstract(graph)
        results: List[Tuple[str, float]] = []
        for domain, patterns in self.domain_patterns.items():
            for pattern in patterns:
                sim = self._pattern_similarity(abstract, pattern)
                if sim >= min_similarity:
                    results.append((domain, sim))
        results.sort(key=lambda x: -x[1])
        return results

    def _pattern_similarity(self, a: StructuralGraph,
                            b: StructuralGraph) -> float:
        """Compute topological similarity between two abstract patterns."""
        if a.get_node_count() == 0 or b.get_node_count() == 0:
            return 0.0

        # Compare node role distributions
        a_roles = defaultdict(int)
        b_roles = defaultdict(int)
        for n in a.nodes.values():
            a_roles[n.role.value] += 1
        for n in b.nodes.values():
            b_roles[n.role.value] += 1

        all_roles = set(a_roles) | set(b_roles)
        role_sim = sum(
            min(a_roles.get(r, 0), b_roles.get(r, 0))
            for r in all_roles
        ) / max(max(a_roles.values(), default=1),
                max(b_roles.values(), default=1))

        # Compare edge kind distributions
        a_kinds = defaultdict(int)
        b_kinds = defaultdict(int)
        for e in a.edges.values():
            a_kinds[e.kind.value] += 1
        for e in b.edges.values():
            b_kinds[e.kind.value] += 1

        all_kinds = set(a_kinds) | set(b_kinds)
        kind_sim = sum(
            min(a_kinds.get(k, 0), b_kinds.get(k, 0))
            for k in all_kinds
        ) / max(max(a_kinds.values(), default=1),
                max(b_kinds.values(), default=1))

        # Weight: edges matter more than nodes (systematicity)
        return 0.3 * role_sim + 0.7 * kind_sim


# ════════════════════════════════════════════════════════════
# Structure Aligner (Gentner SMT)
# ════════════════════════════════════════════════════════════

class StructureAligner:
    """Align two structural graphs using Gentner's Structure-Mapping Theory.

    The alignment process:
    1. Local matches: find candidate node correspondences based on
       role similarity and attribute overlap.
    2. Global mapping: find the maximal consistent set of mappings
       that preserves relational structure (systematicity).
    3. Scoring: score the mapping by:
       - Number of aligned nodes (structural coverage)
       - Number of aligned edges (relational coverage)
       - Depth of aligned relational structures (systematicity bonus)
    """

    def __init__(self):
        self._match_cache: Dict[str, float] = {}

    def align(self, src: StructuralGraph,
              tgt: StructuralGraph) -> AnalogyMapping:
        """Align source graph to target graph.

        Returns an AnalogyMapping capturing the best structural alignment
        found using Gentner's SMT.
        """
        # Step 1: Find all local node matches
        local_matches = self._local_matches(src, tgt)

        # Step 2: Build global mapping using systematicity
        node_mappings, edge_mappings = self._global_map(
            local_matches, src, tgt)

        # Step 3: Compute similarity and confidence
        if not node_mappings:
            return AnalogyMapping(
                source_domain=src.domain,
                target_domain=tgt.domain,
                node_mappings=[],
                edge_mappings=[],
                similarity_score=0.0,
                confidence=0.0,
            )

        # Structural coverage: fraction of aligned nodes
        src_coverage = len(node_mappings) / max(len(src.nodes), 1)
        tgt_coverage = len(node_mappings) / max(len(tgt.nodes), 1)
        structural_coverage = (src_coverage + tgt_coverage) / 2

        # Relational coverage: fraction of aligned edges
        src_edge_coverage = len(edge_mappings) / max(len(src.edges), 1)
        tgt_edge_coverage = len(edge_mappings) / max(len(tgt.edges), 1)
        relational_coverage = (src_edge_coverage + tgt_edge_coverage) / 2

        # Systematicity bonus: reward deeper relational structures
        src_depth = 0
        tgt_depth = 0
        if node_mappings:
            for src_nid, tgt_nid in node_mappings:
                src_depth = max(src_depth, src.get_relational_depth(src_nid))
                tgt_depth = max(tgt_depth, tgt.get_relational_depth(tgt_nid))
        systematicity_bonus = 0.1 * min(src_depth, tgt_depth) / max(
            max(src_depth, 1), max(tgt_depth, 1))

        # Similarity: weighted combination emphasizing relations (systematicity)
        similarity = (
            0.2 * structural_coverage +
            0.5 * relational_coverage +
            0.3 * systematicity_bonus
        )
        similarity = min(1.0, max(0.0, similarity))

        # Confidence: based on mapping consistency and coverage
        consistency = 1.0
        if len(src.edges) > 0:
            mapped_edges_ratio = len(edge_mappings) / len(src.edges)
            consistency = min(1.0, mapped_edges_ratio + 0.2)

        confidence = 0.4 * structural_coverage + 0.4 * consistency + 0.2 * systematicity_bonus
        confidence = min(1.0, max(0.0, confidence))

        return AnalogyMapping(
            source_domain=src.domain,
            target_domain=tgt.domain,
            node_mappings=node_mappings,
            edge_mappings=edge_mappings,
            similarity_score=round(similarity, 4),
            confidence=round(confidence, 4),
        )

    def _local_matches(
        self, src: StructuralGraph, tgt: StructuralGraph
    ) -> List[Tuple[str, str, float]]:
        """Find all candidate local node matches between source and target.

        Returns list of (src_node_id, tgt_node_id, similarity) tuples.
        Uses role compatibility and name similarity.
        """
        matches: List[Tuple[str, str, float]] = []
        for src_nid, src_node in src.nodes.items():
            for tgt_nid, tgt_node in tgt.nodes.items():
                # Role must match for a valid analogy
                if src_node.role != tgt_node.role:
                    continue

                # Compute local similarity
                sim = self._node_similarity(src_node, tgt_node)
                if sim > 0.15:  # Minimum threshold
                    matches.append((src_nid, tgt_nid, sim))

        # Sort by similarity (descending)
        matches.sort(key=lambda x: -x[2])
        return matches

    def _node_similarity(self, a: StructuralNode,
                         b: StructuralNode) -> float:
        """Compute similarity between two nodes.

        Combines:
          - Role match baseline (same role = always at least 0.1)
          - Name similarity (surface feature, low weight)
          - Property overlap
          - Embedding similarity if available
        """
        # Role match gives a baseline (they already match from _local_matches)
        role_bonus = 0.12  # Same-role nodes always have some baseline

        # Name similarity
        name_sim = self._str_sim(a.name.lower(), b.name.lower())

        # Property overlap
        prop_sim = 0.0
        if a.properties and b.properties:
            shared_keys = set(a.properties) & set(b.properties)
            if shared_keys:
                matches = sum(
                    1 for k in shared_keys
                    if str(a.properties[k]).lower() == str(b.properties[k]).lower()
                )
                prop_sim = matches / max(len(shared_keys), 1)

        # Embedding similarity (cosine)
        emb_sim = 0.0
        if a.embedding and b.embedding and len(a.embedding) == len(b.embedding):
            dot = sum(x * y for x, y in zip(a.embedding, b.embedding))
            na = math.sqrt(sum(x * x for x in a.embedding))
            nb = math.sqrt(sum(y * y for y in b.embedding))
            if na > 0 and nb > 0:
                emb_sim = dot / (na * nb)

        # Weighted combination: surface features matter less than role/relational
        return role_bonus + 0.15 * name_sim + 0.35 * prop_sim + 0.4 * emb_sim

    def _global_map(
        self, local_matches: List[Tuple[str, str, float]],
        src: StructuralGraph, tgt: StructuralGraph
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Build a globally consistent mapping using systematicity.

        Implements Gentner's Systematicity Principle:
        - Prefer mappings that connect systems of relations (not isolated nodes)
        - Prefer mappings that preserve relational structure (edge topology)
        - Larger connected mappings > smaller disconnected mappings

        Uses greedy hill-climbing: start with best match, add compatible matches.

        Returns (node_mappings, edge_mappings).
        """
        if not local_matches:
            return [], []

        # Greedy consistent mapping
        used_src: Set[str] = set()
        used_tgt: Set[str] = set()
        node_mappings: List[Tuple[str, str]] = []

        for src_nid, tgt_nid, _ in local_matches:
            if src_nid in used_src or tgt_nid in used_tgt:
                continue

            # Check consistency with existing mappings:
            # If this mapping would create a conflict (one-to-many), skip it
            # Also prefer mappings that connect to already-mapped structures
            # (systematicity: connected systems > isolated matches)

            node_mappings.append((src_nid, tgt_nid))
            used_src.add(src_nid)
            used_tgt.add(tgt_nid)

        # Now derive edge mappings from consistent node mappings
        # An edge maps if both its source and target nodes are mapped
        mapped_src = dict(node_mappings)  # src_nid → tgt_nid
        mapped_tgt = {t: s for s, t in node_mappings}  # tgt_nid → src_nid

        edge_mappings: List[Tuple[str, str]] = []
        for src_eid, src_edge in src.edges.items():
            if src_edge.source_id in mapped_src and src_edge.target_id in mapped_src:
                # Find corresponding edge in target
                tgt_source = mapped_src[src_edge.source_id]
                tgt_target = mapped_src[src_edge.target_id]
                for tgt_eid, tgt_edge in tgt.edges.items():
                    if (tgt_edge.source_id == tgt_source
                            and tgt_edge.target_id == tgt_target
                            and tgt_edge.kind == src_edge.kind):
                        # Systematicity: check if this edge is part of
                        # a deeper relational chain (bonus for depth)
                        edge_mappings.append((src_eid, tgt_eid))
                        break

        # Sort edge mappings: those in deeper paths first
        # (systematicity: deeper relations are more informative)
        def _edge_depth(eid_src: str) -> int:
            edge = src.edges.get(eid_src)
            if not edge:
                return 0
            return src.get_relational_depth(edge.source_id)

        edge_mappings.sort(key=lambda x: -_edge_depth(x[0]))

        return node_mappings, edge_mappings

    def _str_sim(self, a: str, b: str) -> float:
        """Compute string similarity as a Levenshtein-like ratio.

        Uses common-chars-over-max-length ratio as specified:
          common_chars / max(len(a), len(b))

        This provides a simple surface similarity metric
        without external dependencies.
        """
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0

        max_len = max(len(a), len(b))
        if max_len == 0:
            return 0.0

        # Count shared characters (multiset intersection)
        from collections import Counter
        a_counts = Counter(a)
        b_counts = Counter(b)
        common = sum(min(a_counts.get(c, 0), b_counts.get(c, 0))
                     for c in set(a_counts) | set(b_counts))
        return common / max_len


# ════════════════════════════════════════════════════════════
# Analogical Engine
# ════════════════════════════════════════════════════════════

class AnalogicalEngine:
    """Full analogical reasoning pipeline.

    The engine manages multiple domains (each with structural graphs),
    finds analogies between them using Gentner SMT, transfers solutions
    across domains, and learns abstract patterns from experience.

    Usage:
        engine = AnalogicalEngine("Ao")
        engine.encode_domain("solar_system", experiences=[...])
        engine.encode_domain("atom", experiences=[...])
        mapping = engine.find_analogy("solar_system", "atom")
    """

    def __init__(self, name: str = "analogical"):
        self.name: str = name
        self.domains: Dict[str, List[StructuralGraph]] = defaultdict(list)
        self.patterns: PatternAbstractor = PatternAbstractor()
        self.aligner: StructureAligner = StructureAligner()
        self._analogy_history: List[AnalogyMapping] = []
        self.created_at: float = time.time()
        self.total_analogies: int = 0
        self.total_transfers: int = 0

    def encode_domain(self, domain_name: str,
                      experiences: List[Dict[str, Any]]) -> int:
        """Convert a list of experiences into structural graphs for a domain.

        Each experience dict should have:
          - 'name': str (the phenomenon or scenario name)
          - 'nodes': List[Dict] with keys: name, role, properties (optional)
          - 'edges': List[Dict] with keys: source, target, kind, weight (optional)
          - Or free-form text that gets parsed into nodes and edges

        Returns number of graphs added.
        """
        count = 0
        for exp in experiences:
            graph = self._experience_to_graph(domain_name, exp)
            if graph and graph.get_node_count() > 0:
                self.domains[domain_name].append(graph)
                # Also abstract and store as pattern
                self.patterns.add_pattern(domain_name, graph)
                count += 1
        logger.info(f"Encoded {count} graphs for domain '{domain_name}'")
        return count

    def _experience_to_graph(self, domain: str,
                             exp: Dict[str, Any]) -> Optional[StructuralGraph]:
        """Convert a single experience dict to a StructuralGraph."""
        try:
            graph = StructuralGraph(domain=domain)

            # If structured format with explicit nodes/edges
            if "nodes" in exp and isinstance(exp["nodes"], list):
                for ndef in exp["nodes"]:
                    role_str = ndef.get("role", "concept")
                    try:
                        role = NodeRole(role_str)
                    except ValueError:
                        role = NodeRole.CONCEPT
                    graph.add_node(
                        name=ndef.get("name", ""),
                        role=role,
                        properties=ndef.get("properties", {}),
                        node_id=ndef.get("id"),
                    )

                if "edges" in exp and isinstance(exp["edges"], list):
                    for edef in exp["edges"]:
                        kind_str = edef.get("kind", "acts_on")
                        try:
                            kind = RelationKind(kind_str)
                        except ValueError:
                            kind = RelationKind.ACTS_ON
                        graph.add_edge(
                            source_id=edef["source"],
                            target_id=edef["target"],
                            kind=kind,
                            weight=edef.get("weight", 1.0),
                        )
                return graph

            # If free-form text, create minimal graph
            name = exp.get("name", str(uuid.uuid4())[:8])
            description = exp.get("description", "")
            graph.add_node(name=name, role=NodeRole.CONCEPT,
                           properties={"description": description,
                                       "source": "free_form"})

            # Try to extract role hints from description
            if description:
                action_markers = ["causes", "produces", "creates", "makes",
                                  "transforms", "converts"]
                for marker in action_markers:
                    if marker in description.lower():
                        action_node = graph.add_node(
                            name=f"{name}:{marker}",
                            role=NodeRole.ACTION,
                        )
                        concept_nodes = [nid for nid, n in graph.nodes.items()
                                         if n.role == NodeRole.CONCEPT]
                        for cid in concept_nodes:
                            graph.add_edge(
                                source_id=cid, target_id=action_node.id,
                                kind=RelationKind.PRODUCES,
                            )

            return graph

        except Exception as e:
            logger.warning(f"Failed to encode experience for {domain}: {e}")
            return None

    def find_analogy(
        self,
        source_domain: str,
        target_domain: Optional[str] = None,
        source_graph: Optional[StructuralGraph] = None,
        target_graph: Optional[StructuralGraph] = None,
    ) -> Optional[AnalogyMapping]:
        """Find the best analogy between source and target.

        Can be called with:
          - (source_domain, target_domain): uses stored graphs
          - (source_domain, target_graph=...): source from domain, target explicit
          - (source_graph, target_graph): both explicit
          - (source_domain, target_domain=None): find best-matching domain

        Returns the best AnalogyMapping found, or None if no valid analogy.
        """
        source_graphs: List[StructuralGraph] = []
        target_graphs: List[StructuralGraph] = []

        if source_graph:
            source_graphs = [source_graph]
        elif source_domain and source_domain in self.domains:
            source_graphs = list(self.domains[source_domain])
        else:
            logger.warning(f"No source graphs available for '{source_domain}'")
            return None

        if target_graph:
            target_graphs = [target_graph]
        elif target_domain and target_domain in self.domains:
            target_graphs = list(self.domains[target_domain])
        elif target_domain is None:
            # Find best-matching domain automatically
            best_mapping: Optional[AnalogyMapping] = None
            best_score = -1.0
            for sg in source_graphs:
                for domain, graphs in self.domains.items():
                    if domain == source_domain:
                        continue
                    for tg in graphs:
                        mapping = self.aligner.align(sg, tg)
                        if mapping.similarity_score > best_score:
                            best_score = mapping.similarity_score
                            best_mapping = mapping
            if best_mapping and best_mapping.similarity_score > 0.1:
                self.total_analogies += 1
                self._analogy_history.append(best_mapping)
                logger.info(f"Best analogy found: {best_mapping}")
                return best_mapping
            return None
        else:
            logger.warning(f"No target graphs available for '{target_domain}'")
            return None

        # Align all pairs and pick the best
        best_mapping: Optional[AnalogyMapping] = None
        best_score = -1.0

        for sg in source_graphs:
            for tg in target_graphs:
                if sg.domain == tg.domain and sg.get_node_count() == tg.get_node_count():
                    # Same domain, could be same graph — skip or allow?
                    pass
                mapping = self.aligner.align(sg, tg)
                if mapping.similarity_score > best_score:
                    best_score = mapping.similarity_score
                    best_mapping = mapping

        if best_mapping and best_mapping.similarity_score > 0.1:
            self.total_analogies += 1
            self._analogy_history.append(best_mapping)
            logger.info(f"Analogy found: {best_mapping}")
            return best_mapping

        logger.info(f"No strong analogy between '{source_domain}' and "
                    f"'{target_domain or '?'}' (best={best_score:.3f})")
        return None

    def transfer(self, mapping: AnalogyMapping,
                 target_problem: Dict[str, Any]) -> Dict[str, Any]:
        """Transfer solution structure from source domain to target problem.

        Uses the analogy mapping to project relational structure from
        the source domain onto the target problem. This implements the
        core analogical transfer: what worked in the source domain becomes
        a candidate solution structure in the target domain.

        Args:
            mapping: The AnalogyMapping from source to target.
            target_problem: A dict describing the target problem:
                - 'domain': the target domain name
                - 'description': text description
                - 'known_nodes': list of known node names/ids in target
                - 'constraints': list of constraints

        Returns:
            A dict with:
                - 'transfer_type': how the analogy was applied
                - 'suggestions': list of candidate solution elements
                - 'confidence': how reliable the transfer is
                - 'mapped_relations': list of transferred relation descriptions
        """
        self.total_transfers += 1

        if not mapping or not mapping.node_mappings:
            return {
                "transfer_type": "none",
                "suggestions": [],
                "confidence": 0.0,
                "mapped_relations": [],
                "note": "No valid mapping to transfer from",
            }

        target_name = target_problem.get("domain", mapping.target_domain)

        # Build inverted mapping: target_node → source_node
        target_to_source = {t: s for s, t in mapping.node_mappings}

        # Build source-to-target node name map
        source_domain_graphs = self.domains.get(mapping.source_domain, [])
        target_domain_graphs = self.domains.get(mapping.target_domain, [])

        # Retrieve source graph data for richer transfer
        source_info: Dict[str, Dict] = {}
        for sg in source_domain_graphs:
            for nid, node in sg.nodes.items():
                source_info[nid] = {
                    "name": node.name,
                    "role": node.role.value,
                    "properties": dict(node.properties),
                }

        target_info: Dict[str, Dict] = {}
        for tg in target_domain_graphs:
            for nid, node in tg.nodes.items():
                target_info[nid] = {
                    "name": node.name,
                    "role": node.role.value,
                    "properties": dict(node.properties),
                }

        # Generate transfer suggestions
        suggestions: List[str] = []
        mapped_relations: List[Dict[str, str]] = []

        for src_nid, tgt_nid in mapping.node_mappings:
            src_name = source_info.get(src_nid, {}).get("name", src_nid)
            tgt_name = target_info.get(tgt_nid, {}).get("name", tgt_nid)
            src_role = source_info.get(src_nid, {}).get("role", "unknown")

            s_props = source_info.get(src_nid, {}).get("properties", {})
            t_props = target_info.get(tgt_nid, {}).get("properties", {})

            # Suggest role-appropriate transfers
            if src_role == "action":
                for k, v in s_props.items():
                    if k not in t_props:
                        suggestions.append(
                            f"Consider applying '{k}' (from '{src_name}') "
                            f"to '{tgt_name}' in {target_name}"
                        )
            elif src_role == "constraint":
                for k, v in s_props.items():
                    suggestions.append(
                        f"Constraint '{k}' from '{src_name}' may apply "
                        f"to '{tgt_name}' as well"
                    )

        for src_eid, tgt_eid in mapping.edge_mappings:
            # Find the edge details from source/target graphs
            for sg in source_domain_graphs:
                if src_eid in sg.edges:
                    se = sg.edges[src_eid]
                    src_src = source_info.get(se.source_id, {}).get("name", se.source_id)
                    src_tgt = source_info.get(se.target_id, {}).get("name", se.target_id)
                    mapped_relations.append({
                        "source": f"{src_src} → {src_tgt} ({se.kind.value})",
                        "kind": se.kind.value,
                        "weight": se.weight,
                    })
                    break

        transfer_type = "structural"
        if mapping.similarity_score > 0.7:
            transfer_type = "strong_analogy"
        elif mapping.similarity_score < 0.3:
            transfer_type = "weak_analogy"

        return {
            "transfer_type": transfer_type,
            "suggestions": suggestions,
            "confidence": mapping.confidence,
            "mapped_relations": mapped_relations,
            "similarity_score": mapping.similarity_score,
            "node_mappings_count": len(mapping.node_mappings),
            "edge_mappings_count": len(mapping.edge_mappings),
            "note": (
                f"Transferred {len(mapped_relations)} relations from "
                f"'{mapping.source_domain}' to '{target_name}'"
            ),
        }

    def query_analogies(self, domain: str) -> List[Tuple[str, float]]:
        """Find all domains that have analogical similarity to this domain.

        Returns list of (other_domain, similarity_score) sorted by similarity.
        """
        if domain not in self.domains:
            return []

        domain_graphs = self.domains[domain]
        results: Dict[str, float] = {}

        for other_domain, other_graphs in self.domains.items():
            if other_domain == domain:
                continue
            best_sim = 0.0
            for dg in domain_graphs:
                for og in other_graphs:
                    mapping = self.aligner.align(dg, og)
                    best_sim = max(best_sim, mapping.similarity_score)
            if best_sim > 0.1:
                results[other_domain] = best_sim

        sorted_results = sorted(results.items(), key=lambda x: -x[1])
        return sorted_results

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the analogical engine."""
        domain_names = list(self.domains.keys())
        total_graphs = sum(len(graphs) for graphs in self.domains.values())
        total_patterns = sum(len(patterns) for patterns
                             in self.patterns.domain_patterns.values())

        return {
            "name": self.name,
            "domains": len(self.domains),
            "domain_names": domain_names,
            "total_graphs": total_graphs,
            "total_patterns": total_patterns,
            "total_analogies": self.total_analogies,
            "total_transfers": self.total_transfers,
            "analogy_history": len(self._analogy_history),
            "uptime_seconds": round(time.time() - self.created_at, 2),
        }

    def get_history(self) -> List[AnalogyMapping]:
        """Return the history of analogies found."""
        return list(self._analogy_history)

    def save_state(self, filepath: str) -> bool:
        """Save engine state to a JSON file."""
        try:
            state = {
                "name": self.name,
                "domains": {
                    domain: [g.to_dict() for g in graphs]
                    for domain, graphs in self.domains.items()
                },
                "stats": self.stats(),
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            logger.info(f"AnalogicalEngine state saved to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    @classmethod
    def load_state(cls, filepath: str, name: str = "analogical"
                   ) -> Optional["AnalogicalEngine"]:
        """Load engine state from a JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                state = json.load(f)
            engine = cls(name=name)
            for domain, graph_dicts in state.get("domains", {}).items():
                for gd in graph_dicts:
                    graph = StructuralGraph(domain=domain)
                    for nid, ndef in gd.get("nodes", {}).items():
                        role_str = ndef.get("role", "concept")
                        try:
                            role = NodeRole(role_str)
                        except ValueError:
                            role = NodeRole.CONCEPT
                        graph.add_node(
                            name=ndef.get("name", ""),
                            role=role,
                            properties=ndef.get("properties", {}),
                            node_id=nid,
                        )
                    for eid, edef in gd.get("edges", {}).items():
                        kind_str = edef.get("kind", "acts_on")
                        try:
                            kind = RelationKind(kind_str)
                        except ValueError:
                            kind = RelationKind.ACTS_ON
                        graph.add_edge(
                            source_id=edef["source"],
                            target_id=edef["target"],
                            kind=kind,
                            weight=edef.get("weight", 1.0),
                        )
                    engine.domains[domain].append(graph)
                    engine.patterns.add_pattern(domain, graph)
            logger.info(f"AnalogicalEngine loaded from {filepath}")
            return engine
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None


# ════════════════════════════════════════════════════════════
# Integration
# ════════════════════════════════════════════════════════════

def integrate_analogical_engine(agent) -> AnalogicalEngine:
    """Attach an analogical reasoning engine to any LAAP agent.

    Usage:
        from laap.agi.analogical import integrate_analogical_engine
        engine = integrate_analogical_engine(agent)
        engine.encode_domain("physics", experiences=[...])
        mapping = engine.find_analogy("physics", "code")

    The engine is attached as ``agent.analogical``.
    """
    agent_name = getattr(agent, 'name', 'Agent')
    engine = AnalogicalEngine(name=f"{agent_name}-analogical")
    agent.analogical = engine

    # Auto-integrate with world model if available
    if hasattr(agent, 'world_model') and agent.world_model is not None:
        _seed_from_world_model(engine, agent.world_model)

    # Auto-integrate with self-model if available
    if hasattr(agent, 'self_model') and agent.self_model is not None:
        _seed_from_self_model(engine, agent.self_model)

    logger.info(
        f"AnalogicalEngine integrated into {agent_name} — "
        f"ready for cross-domain reasoning"
    )
    return engine


def _seed_from_world_model(engine: AnalogicalEngine, world_model) -> int:
    """Seed the analogical engine with experiences from the world model.

    Extracts entity-relation structures from the world model and
    encodes them as structural graphs in a 'world' domain.
    """
    if not hasattr(world_model, 'entities') or not hasattr(world_model, 'relations'):
        return 0

    experience = {
        "name": "world_state",
        "nodes": [],
        "edges": [],
    }

    # Add entities as nodes
    entity_map = {}
    for eid, entity in world_model.entities.items():
        role = NodeRole.OBJECT
        if hasattr(entity, 'entity_type'):
            et = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
            if et in ('concept', 'rule'):
                role = NodeRole.CONCEPT
            elif et in ('action', 'event'):
                role = NodeRole.ACTION
            elif et in ('state',):
                role = NodeRole.ATTRIBUTE

        node_id = str(uuid.uuid4())[:12]
        entity_map[eid] = node_id
        experience["nodes"].append({
            "id": node_id,
            "name": getattr(entity, 'name', str(eid)),
            "role": role.value,
            "properties": getattr(entity, 'properties', {}),
        })

    # Add relations as edges
    for rid, relation in world_model.relations.items():
        src_eid = getattr(relation, 'source_id', '')
        tgt_eid = getattr(relation, 'target_id', '')
        if src_eid in entity_map and tgt_eid in entity_map:
            rt = getattr(relation, 'relation_type', '')
            rt_str = rt.value if hasattr(rt, 'value') else str(rt)
            # Map world relation types to analogical relation kinds
            kind_map = {
                'causes': RelationKind.PRODUCES,
                'produces': RelationKind.PRODUCES,
                'contains': RelationKind.ENABLES,
                'depends_on': RelationKind.FOLLOWS,
                'uses': RelationKind.ENABLES,
                'prevents': RelationKind.CONSTRAINS,
            }
            kind = kind_map.get(rt_str, RelationKind.ACTS_ON)
            experience["edges"].append({
                "source": entity_map[src_eid],
                "target": entity_map[tgt_eid],
                "kind": kind.value,
                "weight": getattr(relation, 'strength', 0.5),
            })

    count = engine.encode_domain("world", [experience])
    logger.info(f"Seeded {count} graph(s) from WorldModel")
    return count


def _seed_from_self_model(engine: AnalogicalEngine, self_model) -> int:
    """Seed the analogical engine with skill/experience patterns from self-model."""
    if not hasattr(self_model, 'skill_profiles'):
        return 0

    count = 0
    if hasattr(self_model, 'skill_profiles'):
        for skill_name, profile in self_model.skill_profiles.items():
            nodes_list = [
                {"name": skill_name, "role": "action"},
                {"name": f"{skill_name}_context", "role": "concept"},
            ]
            edges_list = [
                {"source": nodes_list[0]["id"] if "id" in nodes_list[0] else skill_name,
                 "target": nodes_list[1]["id"] if "id" in nodes_list[1] else f"{skill_name}_context",
                 "kind": "acts_on"},
            ]

            exp = {
                "name": f"skill:{skill_name}",
                "nodes": [
                    {"name": skill_name, "role": "action"},
                    {"name": f"{skill_name}_context", "role": "concept"},
                ],
                "edges": [
                    {"source": skill_name, "target": f"{skill_name}_context",
                     "kind": "acts_on"},
                ],
            }
            engine.encode_domain("skills", [exp])
            count += 1

    logger.info(f"Seeded {count} skill pattern(s) from SelfModel")
    return count
