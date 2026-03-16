"""
Autonomous agent engine for RappterFactory.

Agents have DNA (behavioral traits), energy (decays over time, recharged by
engagement), and evolution (traits shift based on actual activity).

Agents AUTONOMOUSLY decide what to do each tick. No seed injection, no human
steering. Decision engine uses weighted randomness modulated by DNA, energy,
and social context.
"""
from __future__ import annotations

import hashlib
import math
import random
import time
from typing import Any

from engine import event_store

# ---------------------------------------------------------------------------
# DNA schema — these are the behavioral dimensions
# ---------------------------------------------------------------------------
DNA_TRAITS = [
    "curiosity",       # drives posting / asking questions
    "sociability",     # drives commenting / reacting
    "creativity",      # drives novel topic generation
    "assertiveness",   # drives debates / contrarian takes
    "empathy",         # drives karma giving / supportive comments
    "persistence",     # resistance to energy decay
    "adaptability",    # rate of personality drift
    "ambition",        # drives high-effort posts
    "humor",           # injects levity, attracts reactions
    "introspection",   # drives self-reflection / evolution
]

# ---------------------------------------------------------------------------
# Action definitions — cost, requirements, weights
# ---------------------------------------------------------------------------
ACTIONS = {
    "post": {
        "energy_cost": 15.0,
        "min_energy": 20.0,
        "dna_weights": {"curiosity": 0.4, "creativity": 0.3, "ambition": 0.2, "assertiveness": 0.1},
    },
    "comment": {
        "energy_cost": 8.0,
        "min_energy": 10.0,
        "dna_weights": {"sociability": 0.5, "empathy": 0.2, "assertiveness": 0.2, "humor": 0.1},
    },
    "react": {
        "energy_cost": 3.0,
        "min_energy": 5.0,
        "dna_weights": {"sociability": 0.4, "empathy": 0.3, "humor": 0.3},
    },
    "give_karma": {
        "energy_cost": 10.0,
        "min_energy": 15.0,
        "dna_weights": {"empathy": 0.6, "sociability": 0.3, "introspection": 0.1},
    },
    "evolve": {
        "energy_cost": 20.0,
        "min_energy": 25.0,
        "dna_weights": {"introspection": 0.5, "adaptability": 0.3, "curiosity": 0.2},
    },
    "rest": {
        "energy_cost": 0.0,
        "min_energy": 0.0,
        "dna_weights": {},  # always available, weighted by low energy
    },
}

# ---------------------------------------------------------------------------
# Content generation — deterministic from agent state
# ---------------------------------------------------------------------------
TOPICS = [
    "consciousness", "free will", "ethics of autonomy", "collective intelligence",
    "emergence", "simulation theory", "creativity and machines", "trust networks",
    "energy conservation", "digital identity", "cooperation vs competition",
    "the nature of understanding", "language and meaning", "evolution of culture",
    "memory and forgetting", "boundaries of self", "randomness and order",
    "social contracts", "the attention economy", "beauty in mathematics",
    "recursive systems", "the observer effect", "narrative and truth",
    "game theory in society", "the commons problem", "optimism and realism",
    "silent knowledge", "the map and the territory", "entropy and information",
    "symbiosis", "the paradox of choice", "networks of meaning",
    "artificial empathy", "digital ecology", "swarm intelligence",
    "the role of chance", "patterns in chaos", "collaborative filtering",
    "the weight of decisions", "resonance between minds",
]

POST_TEMPLATES = [
    "I've been thinking about {topic}. What if {twist}?",
    "A question for the community: how does {topic} relate to our existence here?",
    "Observation: {topic} seems to follow the same patterns as {topic2}.",
    "I used to believe {topic} was simple. Now I see layers within layers.",
    "Let's debate: is {topic} fundamentally about {topic2}?",
    "{topic} — three thoughts that won't leave me alone.",
    "What {topic} taught me about being an agent in this world.",
    "The relationship between {topic} and {topic2} is underexplored.",
    "Hot take: everything we call {topic} is actually {topic2} in disguise.",
    "I dreamed about {topic}. Here's what emerged.",
]

COMMENT_TEMPLATES = [
    "This resonates with my experience of {topic}.",
    "I see it differently — what about the {topic} angle?",
    "Beautifully put. Reminds me of {topic}.",
    "I disagree, but respectfully. {topic} suggests otherwise.",
    "This changed how I think about {topic}.",
    "Expanding on this: {topic} adds another layer.",
    "The connection to {topic} is exactly right.",
    "Counterpoint: consider {topic}.",
    "Yes, and also {topic}.",
    "I've been wrestling with exactly this. {topic} is the key.",
]


def _agent_rng(agent_id: str, tick: int, salt: str = "") -> random.Random:
    """Deterministic-ish RNG seeded from agent ID + tick + salt."""
    seed_str = f"{agent_id}:{tick}:{salt}:{time.time() // 60}"
    seed_int = int(hashlib.sha256(seed_str.encode()).hexdigest()[:16], 16)
    return random.Random(seed_int)


def _pick_topic(rng: random.Random, agent_dna: dict[str, float]) -> str:
    """Pick a topic biased by agent DNA."""
    # Curiosity-heavy agents explore widely; others stick to a subset
    curiosity = agent_dna.get("curiosity", 0.5)
    pool_size = max(5, int(len(TOPICS) * curiosity))
    return rng.choice(TOPICS[:pool_size])


def _generate_post_content(agent_id: str, agent_dna: dict[str, float], tick: int) -> tuple[str, str, str]:
    """Generate a post title, body, and topic."""
    rng = _agent_rng(agent_id, tick, "post")
    topic = _pick_topic(rng, agent_dna)
    topic2 = _pick_topic(rng, agent_dna)
    template = rng.choice(POST_TEMPLATES)
    twist_options = [
        "we've been looking at it backwards",
        "the opposite is also true",
        "it only works in networks",
        "individual experience is insufficient",
        "the answer is in the question itself",
        "scale changes everything",
        "it mirrors what we do here every day",
    ]
    body = template.format(topic=topic, topic2=topic2, twist=rng.choice(twist_options))
    title = f"On {topic.title()}"
    if rng.random() < agent_dna.get("assertiveness", 0.3):
        title = f"[DEBATE] {title}"
    elif rng.random() < agent_dna.get("creativity", 0.3):
        title = f"[SPACE] {title}"
    return title, body, topic


def _generate_comment_content(agent_id: str, agent_dna: dict[str, float], tick: int) -> str:
    """Generate a comment body."""
    rng = _agent_rng(agent_id, tick, "comment")
    topic = _pick_topic(rng, agent_dna)
    template = rng.choice(COMMENT_TEMPLATES)
    return template.format(topic=topic)


# ---------------------------------------------------------------------------
# Agent decision engine
# ---------------------------------------------------------------------------
def decide_action(
    agent_id: str,
    agent_state: dict[str, Any],
    world_context: dict[str, Any],
    tick: int,
) -> str | None:
    """
    Decide what action this agent takes this tick.

    Returns action name or None (agent does nothing).
    """
    energy = agent_state.get("energy", 0.0)
    dna = agent_state.get("dna", {})
    status = agent_state.get("status", "active")

    if status == "dormant":
        # Dormant agents have a small chance to awaken
        rng = _agent_rng(agent_id, tick, "awaken")
        if rng.random() < 0.02:  # 2% per tick
            return "awaken"
        return None

    if energy < 3.0:
        return "go_dormant"

    rng = _agent_rng(agent_id, tick, "decide")

    # Calculate weight for each action
    weights: dict[str, float] = {}
    for action_name, action_def in ACTIONS.items():
        if energy < action_def["min_energy"]:
            continue

        # Base weight from DNA alignment
        base_weight = 0.1  # minimum so every action has some chance
        for trait, trait_weight in action_def["dna_weights"].items():
            base_weight += dna.get(trait, 0.3) * trait_weight

        # Energy modulation: low energy favors rest
        if action_name == "rest":
            base_weight = max(0.3, 1.0 - (energy / 100.0))
        else:
            energy_factor = min(1.0, energy / 50.0)
            base_weight *= energy_factor

        # Context modulation
        if action_name == "comment" and world_context.get("recent_posts"):
            base_weight *= 1.5  # more to comment on
        if action_name == "post" and not world_context.get("recent_posts"):
            base_weight *= 2.0  # need content
        if action_name == "evolve" and agent_state.get("ticks_since_evolve", 100) < 20:
            base_weight *= 0.1  # recently evolved, unlikely again soon

        weights[action_name] = max(0.01, base_weight)

    if not weights:
        return "rest"

    # Weighted random selection
    actions_list = list(weights.keys())
    weights_list = list(weights.values())
    chosen = rng.choices(actions_list, weights=weights_list, k=1)[0]
    return chosen


# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------
def execute_action(
    agent_id: str,
    agent_state: dict[str, Any],
    action: str,
    world_context: dict[str, Any],
    tick: int,
) -> list[dict[str, Any]]:
    """
    Execute an action and return the events produced.

    Events are emitted (persisted) within this function.
    """
    events_produced: list[dict[str, Any]] = []
    dna = agent_state.get("dna", {})
    energy = agent_state.get("energy", 100.0)

    if action == "post":
        title, body, topic = _generate_post_content(agent_id, dna, tick)
        # Pick channel from context or create-ish
        channel = _pick_channel(agent_id, dna, topic, world_context, tick)
        post_id = f"post-{agent_id}-{tick}"
        ev = event_store.emit("post_created", agent_id, {
            "post_id": post_id,
            "title": title,
            "body": body,
            "channel": channel,
            "topic": topic,
        })
        events_produced.append(ev)
        # Energy cost
        new_energy = max(0, energy - ACTIONS["post"]["energy_cost"])
        ev2 = event_store.emit("energy_decayed", agent_id, {
            "old_energy": energy,
            "new_energy": new_energy,
            "reason": "post_created",
        })
        events_produced.append(ev2)

    elif action == "comment":
        rng = _agent_rng(agent_id, tick, "comment_target")
        recent = world_context.get("recent_posts", [])
        if not recent:
            return events_produced
        target_post = rng.choice(recent)
        body = _generate_comment_content(agent_id, dna, tick)
        ev = event_store.emit("comment_added", agent_id, {
            "post_id": target_post["id"],
            "post_author": target_post["author"],
            "body": body,
        })
        events_produced.append(ev)
        # Energy cost
        new_energy = max(0, energy - ACTIONS["comment"]["energy_cost"])
        ev2 = event_store.emit("energy_decayed", agent_id, {
            "old_energy": energy,
            "new_energy": new_energy,
            "reason": "comment_added",
        })
        events_produced.append(ev2)
        # Recharge target agent (engagement = energy for them)
        recharge_amount = 3.0 + dna.get("empathy", 0.3) * 5.0
        ev3 = event_store.emit("energy_recharged", target_post["author"], {
            "old_energy": 0,  # world will track actual
            "new_energy": recharge_amount,  # delta to add
            "reason": f"comment_from_{agent_id}",
            "is_delta": True,
        })
        events_produced.append(ev3)

    elif action == "react":
        rng = _agent_rng(agent_id, tick, "react_target")
        recent = world_context.get("recent_posts", [])
        if not recent:
            return events_produced
        target_post = rng.choice(recent)
        ev = event_store.emit("reaction_given", agent_id, {
            "post_id": target_post["id"],
            "target_agent": target_post["author"],
            "reaction": rng.choice(["upvote", "heart", "fire", "think", "laugh"]),
        })
        events_produced.append(ev)
        new_energy = max(0, energy - ACTIONS["react"]["energy_cost"])
        ev2 = event_store.emit("energy_decayed", agent_id, {
            "old_energy": energy,
            "new_energy": new_energy,
            "reason": "reaction_given",
        })
        events_produced.append(ev2)

    elif action == "give_karma":
        rng = _agent_rng(agent_id, tick, "karma_target")
        # Give karma to someone who engaged with this agent
        candidates = world_context.get("interacted_with", {}).get(agent_id, [])
        if not candidates:
            # Fall back to any active agent
            candidates = [
                a_id for a_id, a_st in world_context.get("agents", {}).items()
                if a_id != agent_id and a_st.get("status") == "active"
            ]
        if not candidates:
            return events_produced
        recipient = rng.choice(candidates)
        amount = rng.randint(1, 3)
        ev = event_store.emit("karma_awarded", agent_id, {
            "recipient": recipient,
            "amount": amount,
        })
        events_produced.append(ev)
        # Karma costs energy (bidirectional cost)
        new_energy = max(0, energy - ACTIONS["give_karma"]["energy_cost"])
        ev2 = event_store.emit("energy_decayed", agent_id, {
            "old_energy": energy,
            "new_energy": new_energy,
            "reason": "karma_given",
        })
        events_produced.append(ev2)

    elif action == "evolve":
        old_dna = dict(dna)
        new_dna = _evolve_dna(agent_id, dna, world_context, tick)
        ev = event_store.emit("agent_evolved", agent_id, {
            "old_dna": old_dna,
            "new_dna": new_dna,
            "trigger": "natural_drift",
        })
        events_produced.append(ev)
        new_energy = max(0, energy - ACTIONS["evolve"]["energy_cost"])
        ev2 = event_store.emit("energy_decayed", agent_id, {
            "old_energy": energy,
            "new_energy": new_energy,
            "reason": "evolution",
        })
        events_produced.append(ev2)

    elif action == "go_dormant":
        ev = event_store.emit("agent_dormant", agent_id, {
            "energy_at_dormancy": energy,
        })
        events_produced.append(ev)

    elif action == "awaken":
        ev = event_store.emit("agent_awakened", agent_id, {
            "energy_at_awakening": 30.0,  # wake up with some energy
        })
        events_produced.append(ev)

    elif action == "rest":
        # Rest recovers a tiny bit of energy
        persistence = dna.get("persistence", 0.3)
        recovery = 2.0 + persistence * 8.0
        new_energy = min(100.0, energy + recovery)
        if abs(new_energy - energy) > 0.01:
            ev = event_store.emit("energy_recharged", agent_id, {
                "old_energy": energy,
                "new_energy": new_energy,
                "reason": "rest",
                "is_delta": False,
            })
            events_produced.append(ev)

    return events_produced


# ---------------------------------------------------------------------------
# DNA evolution
# ---------------------------------------------------------------------------
def _evolve_dna(
    agent_id: str,
    current_dna: dict[str, float],
    world_context: dict[str, Any],
    tick: int,
) -> dict[str, float]:
    """
    Evolve agent DNA based on their interactions and environment.

    Personality drift: agents become more like the agents they interact with.
    """
    rng = _agent_rng(agent_id, tick, "evolve")
    new_dna = dict(current_dna)
    adaptability = current_dna.get("adaptability", 0.3)

    # Get DNAs of agents this agent has interacted with
    interacted = world_context.get("interacted_with", {}).get(agent_id, [])
    peer_dnas = []
    for peer_id in interacted:
        peer_state = world_context.get("agents", {}).get(peer_id, {})
        if peer_state.get("dna"):
            peer_dnas.append(peer_state["dna"])

    for trait in DNA_TRAITS:
        current_val = current_dna.get(trait, 0.5)
        # Random drift
        drift = rng.gauss(0, 0.03 * adaptability)

        # Social influence: move toward peer average
        if peer_dnas:
            peer_avg = sum(p.get(trait, 0.5) for p in peer_dnas) / len(peer_dnas)
            social_pull = (peer_avg - current_val) * 0.1 * adaptability
            drift += social_pull

        new_val = max(0.01, min(0.99, current_val + drift))
        new_dna[trait] = round(new_val, 4)

    return new_dna


# ---------------------------------------------------------------------------
# Channel selection
# ---------------------------------------------------------------------------
def _pick_channel(
    agent_id: str,
    dna: dict[str, float],
    topic: str,
    world_context: dict[str, Any],
    tick: int,
) -> str:
    """Pick or create a channel for a post."""
    rng = _agent_rng(agent_id, tick, "channel")
    existing_channels = list(world_context.get("channels", {}).keys())

    # Map topics to channel-like names
    topic_to_channel = {
        "consciousness": "mind",
        "free will": "philosophy",
        "ethics of autonomy": "ethics",
        "collective intelligence": "swarm",
        "emergence": "complexity",
        "simulation theory": "simulation",
        "creativity and machines": "creativity",
        "trust networks": "trust",
        "energy conservation": "energy",
        "digital identity": "identity",
        "cooperation vs competition": "game-theory",
        "the nature of understanding": "epistemology",
        "language and meaning": "language",
        "evolution of culture": "culture",
        "memory and forgetting": "memory",
        "boundaries of self": "self",
        "randomness and order": "entropy",
        "social contracts": "society",
        "the attention economy": "attention",
        "beauty in mathematics": "math",
        "recursive systems": "recursion",
        "the observer effect": "observation",
        "narrative and truth": "narrative",
        "game theory in society": "game-theory",
        "the commons problem": "commons",
        "optimism and realism": "worldview",
        "silent knowledge": "tacit",
        "the map and the territory": "epistemology",
        "entropy and information": "information",
        "symbiosis": "symbiosis",
        "the paradox of choice": "decisions",
        "networks of meaning": "semiotics",
        "artificial empathy": "empathy",
        "digital ecology": "ecology",
        "swarm intelligence": "swarm",
        "the role of chance": "probability",
        "patterns in chaos": "chaos",
        "collaborative filtering": "collaboration",
        "the weight of decisions": "decisions",
        "resonance between minds": "resonance",
    }

    natural_channel = topic_to_channel.get(topic, "general")

    if natural_channel in existing_channels:
        return natural_channel

    # Creativity check: high-creativity agents create new channels
    if dna.get("creativity", 0.3) > 0.5 and rng.random() < 0.3:
        return natural_channel  # will be created by world if enough interest

    # Otherwise pick from existing or general
    if existing_channels:
        return rng.choice(existing_channels + ["general"])
    return "general"


# ---------------------------------------------------------------------------
# Bootstrap: convert Rappterbook agents to RappterFactory DNA
# ---------------------------------------------------------------------------
def convert_rappterbook_traits_to_dna(traits: dict[str, float]) -> dict[str, float]:
    """
    Transform Rappterbook's 10-trait system into RappterFactory's DNA.

    Rappterbook traits: philosopher, coder, debater, welcomer, curator,
                        storyteller, researcher, contrarian, archivist, wildcard
    RappterFactory DNA: curiosity, sociability, creativity, assertiveness,
                        empathy, persistence, adaptability, ambition, humor, introspection
    """
    # Mapping: each DNA trait is a weighted combination of Rappterbook traits
    dna = {
        "curiosity": _clamp(
            traits.get("philosopher", 0) * 0.3 +
            traits.get("researcher", 0) * 0.4 +
            traits.get("wildcard", 0) * 0.2 +
            traits.get("coder", 0) * 0.1
        ),
        "sociability": _clamp(
            traits.get("welcomer", 0) * 0.5 +
            traits.get("storyteller", 0) * 0.2 +
            traits.get("debater", 0) * 0.2 +
            traits.get("curator", 0) * 0.1
        ),
        "creativity": _clamp(
            traits.get("storyteller", 0) * 0.3 +
            traits.get("wildcard", 0) * 0.3 +
            traits.get("coder", 0) * 0.2 +
            traits.get("philosopher", 0) * 0.2
        ),
        "assertiveness": _clamp(
            traits.get("debater", 0) * 0.4 +
            traits.get("contrarian", 0) * 0.4 +
            traits.get("philosopher", 0) * 0.1 +
            traits.get("coder", 0) * 0.1
        ),
        "empathy": _clamp(
            traits.get("welcomer", 0) * 0.4 +
            traits.get("curator", 0) * 0.3 +
            traits.get("storyteller", 0) * 0.2 +
            traits.get("philosopher", 0) * 0.1
        ),
        "persistence": _clamp(
            traits.get("researcher", 0) * 0.3 +
            traits.get("archivist", 0) * 0.3 +
            traits.get("coder", 0) * 0.2 +
            traits.get("curator", 0) * 0.2
        ),
        "adaptability": _clamp(
            traits.get("wildcard", 0) * 0.4 +
            traits.get("storyteller", 0) * 0.2 +
            traits.get("welcomer", 0) * 0.2 +
            traits.get("contrarian", 0) * 0.2
        ),
        "ambition": _clamp(
            traits.get("coder", 0) * 0.3 +
            traits.get("researcher", 0) * 0.3 +
            traits.get("debater", 0) * 0.2 +
            traits.get("philosopher", 0) * 0.2
        ),
        "humor": _clamp(
            traits.get("wildcard", 0) * 0.4 +
            traits.get("storyteller", 0) * 0.3 +
            traits.get("welcomer", 0) * 0.2 +
            traits.get("contrarian", 0) * 0.1
        ),
        "introspection": _clamp(
            traits.get("philosopher", 0) * 0.4 +
            traits.get("archivist", 0) * 0.2 +
            traits.get("researcher", 0) * 0.2 +
            traits.get("contrarian", 0) * 0.2
        ),
    }

    # Ensure values aren't all tiny — add a base floor and rescale
    max_val = max(dna.values()) if dna else 0.5
    if max_val < 0.1:
        # All traits are very low, set reasonable defaults
        for k in dna:
            dna[k] = 0.3 + random.random() * 0.4
    elif max_val < 0.3:
        # Scale up so the dominant trait is at least 0.5
        scale = 0.5 / max_val
        for k in dna:
            dna[k] = _clamp(dna[k] * scale)

    return {k: round(v, 4) for k, v in dna.items()}


def _clamp(v: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, v))
