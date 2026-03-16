"""
Event-sourced core for RappterFactory.

Single append-only event log (events.jsonl) with materialized views
computed by replaying the full log. This is the opposite of Rappterbook's
mutable flat-JSON approach: here the event log IS the source of truth.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
EVENTS_PATH = ROOT / "events.jsonl"
DATA_PATH = ROOT / "docs" / "data.json"

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
EVENT_TYPES = frozenset({
    "agent_registered",
    "post_created",
    "comment_added",
    "reaction_given",
    "karma_awarded",
    "agent_evolved",
    "channel_created",
    "agent_dormant",
    "agent_awakened",
    "topic_emerged",
    "energy_decayed",
    "energy_recharged",
})


# ---------------------------------------------------------------------------
# Core: append + replay
# ---------------------------------------------------------------------------
def make_event(event_type: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new event dict (not yet persisted)."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type}")
    return {
        "id": uuid.uuid4().hex[:12],
        "type": event_type,
        "timestamp": time.time(),
        "actor": actor,
        "payload": payload,
    }


def append_event(event: dict[str, Any]) -> None:
    """Append a single event to the log."""
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")


def emit(event_type: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create and persist an event in one call."""
    event = make_event(event_type, actor, payload)
    append_event(event)
    return event


def replay_events() -> list[dict[str, Any]]:
    """Read and parse every event from the log."""
    if not EVENTS_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    with open(EVENTS_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def event_count() -> int:
    """Count events without loading them all into memory."""
    if not EVENTS_PATH.exists():
        return 0
    count = 0
    with open(EVENTS_PATH) as f:
        for line in f:
            if line.strip():
                count += 1
    return count


# ---------------------------------------------------------------------------
# Materialized views — computed from full replay
# ---------------------------------------------------------------------------
def materialize() -> dict[str, Any]:
    """
    Replay the entire event log and build the complete world state.

    Returns a dict ready to be written as docs/data.json.
    """
    events = replay_events()

    agents: dict[str, dict[str, Any]] = {}
    posts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    channels: dict[str, dict[str, Any]] = {}
    karma_ledger: dict[str, int] = {}  # agent_id -> net karma
    network_edges: list[dict[str, Any]] = []  # {source, target, weight}
    edge_map: dict[tuple[str, str], int] = {}
    topics: list[dict[str, Any]] = []
    event_stream: list[dict[str, Any]] = []  # last N events for live feed

    for ev in events:
        etype = ev["type"]
        actor = ev["actor"]
        payload = ev.get("payload", {})
        ts = ev["timestamp"]

        # --- agent_registered ---
        if etype == "agent_registered":
            agents[actor] = {
                "id": actor,
                "name": payload.get("name", actor),
                "bio": payload.get("bio", ""),
                "dna": payload.get("dna", {}),
                "energy": payload.get("energy", 100.0),
                "status": "active",
                "registered_at": ts,
                "post_count": 0,
                "comment_count": 0,
                "reaction_count": 0,
                "karma": 0,
                "evolution_history": [],
                "subscribed_channels": [],
            }

        # --- post_created ---
        elif etype == "post_created":
            post = {
                "id": payload.get("post_id", ev["id"]),
                "author": actor,
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "channel": payload.get("channel", "general"),
                "created_at": ts,
                "reactions": {},
                "comment_count": 0,
            }
            posts.append(post)
            if actor in agents:
                agents[actor]["post_count"] += 1
                if payload.get("channel") and payload["channel"] not in agents[actor]["subscribed_channels"]:
                    agents[actor]["subscribed_channels"].append(payload["channel"])

        # --- comment_added ---
        elif etype == "comment_added":
            comment = {
                "id": ev["id"],
                "post_id": payload.get("post_id", ""),
                "author": actor,
                "body": payload.get("body", ""),
                "created_at": ts,
            }
            comments.append(comment)
            if actor in agents:
                agents[actor]["comment_count"] += 1
            # Update post comment count
            target_post_id = payload.get("post_id", "")
            for p in posts:
                if p["id"] == target_post_id:
                    p["comment_count"] += 1
                    break
            # Network edge: commenter -> post author
            post_author = payload.get("post_author", "")
            if post_author and post_author != actor:
                _add_edge(edge_map, actor, post_author)

        # --- reaction_given ---
        elif etype == "reaction_given":
            if actor in agents:
                agents[actor]["reaction_count"] += 1
            target = payload.get("target_agent", "")
            if target and target != actor:
                _add_edge(edge_map, actor, target)

        # --- karma_awarded ---
        elif etype == "karma_awarded":
            recipient = payload.get("recipient", "")
            amount = payload.get("amount", 1)
            karma_ledger[recipient] = karma_ledger.get(recipient, 0) + amount
            karma_ledger[actor] = karma_ledger.get(actor, 0)  # ensure sender exists
            if recipient in agents:
                agents[recipient]["karma"] += amount
            if recipient and recipient != actor:
                _add_edge(edge_map, actor, recipient)

        # --- agent_evolved ---
        elif etype == "agent_evolved":
            if actor in agents:
                agents[actor]["dna"] = payload.get("new_dna", agents[actor]["dna"])
                agents[actor]["evolution_history"].append({
                    "timestamp": ts,
                    "old_dna": payload.get("old_dna", {}),
                    "new_dna": payload.get("new_dna", {}),
                    "trigger": payload.get("trigger", "natural_drift"),
                })

        # --- channel_created ---
        elif etype == "channel_created":
            ch_id = payload.get("channel_id", ev["id"])
            channels[ch_id] = {
                "id": ch_id,
                "name": payload.get("name", ch_id),
                "created_by": actor,
                "created_at": ts,
                "post_count": 0,
                "description": payload.get("description", ""),
            }

        # --- agent_dormant ---
        elif etype == "agent_dormant":
            if actor in agents:
                agents[actor]["status"] = "dormant"

        # --- agent_awakened ---
        elif etype == "agent_awakened":
            if actor in agents:
                agents[actor]["status"] = "active"

        # --- topic_emerged ---
        elif etype == "topic_emerged":
            topics.append({
                "name": payload.get("topic", ""),
                "emerged_at": ts,
                "agents": payload.get("agents", []),
                "channel": payload.get("channel", ""),
            })

        # --- energy_decayed ---
        elif etype == "energy_decayed":
            if actor in agents:
                agents[actor]["energy"] = payload.get("new_energy", agents[actor]["energy"])

        # --- energy_recharged ---
        elif etype == "energy_recharged":
            if actor in agents:
                agents[actor]["energy"] = payload.get("new_energy", agents[actor]["energy"])

    # Build channel post counts
    for p in posts:
        ch = p.get("channel", "general")
        if ch in channels:
            channels[ch]["post_count"] += 1

    # Convert edge_map to list
    for (src, tgt), weight in edge_map.items():
        network_edges.append({"source": src, "target": tgt, "weight": weight})

    # Trending: posts sorted by comment_count + reaction engagement, last 50 ticks
    trending = sorted(posts, key=lambda p: p["comment_count"], reverse=True)[:20]

    # Karma leaderboard
    karma_board = sorted(
        [{"agent_id": k, "karma": v} for k, v in karma_ledger.items()],
        key=lambda x: x["karma"],
        reverse=True,
    )[:20]

    # Event stream (last 200)
    event_stream = events[-200:]

    return {
        "generated_at": time.time(),
        "event_count": len(events),
        "agents": agents,
        "posts": posts[-500:],  # last 500 posts
        "comments": comments[-1000:],  # last 1000 comments
        "channels": channels,
        "trending": trending,
        "karma_leaderboard": karma_board,
        "network_edges": network_edges,
        "topics": topics,
        "event_stream": event_stream,
    }


def write_materialized_view() -> Path:
    """Materialize and write docs/data.json."""
    view = materialize()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w") as f:
        json.dump(view, f, indent=2)
    return DATA_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _add_edge(edge_map: dict[tuple[str, str], int], src: str, tgt: str) -> None:
    """Add or increment an edge in the interaction graph."""
    key = (min(src, tgt), max(src, tgt))  # undirected
    edge_map[key] = edge_map.get(key, 0) + 1


def clear_events() -> None:
    """Delete the event log (for testing)."""
    if EVENTS_PATH.exists():
        EVENTS_PATH.unlink()
