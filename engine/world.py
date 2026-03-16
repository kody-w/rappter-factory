"""
World simulation for RappterFactory.

Tick-based: each tick, every active agent decides and acts.
Topics emerge from interaction patterns.
Channels auto-create when 3+ agents discuss the same topic.
Natural selection: low-energy agents go dormant, engagement recharges.
"""
from __future__ import annotations

import collections
import json
import math
import time
from pathlib import Path
from typing import Any

from engine import event_store
from engine import agent_system


# ---------------------------------------------------------------------------
# World state (in-memory, rebuilt from events each session)
# ---------------------------------------------------------------------------
class World:
    """
    The live simulation state. Rebuilt from events on startup,
    then updated incrementally during ticks.
    """

    def __init__(self) -> None:
        self.agents: dict[str, dict[str, Any]] = {}
        self.posts: list[dict[str, Any]] = []
        self.channels: dict[str, dict[str, Any]] = {}
        self.topic_mentions: dict[str, list[str]] = {}  # topic -> [agent_ids]
        self.interaction_map: dict[str, list[str]] = {}  # agent -> [agents interacted with]
        self.tick_number: int = 0
        self.total_events: int = 0

    def rebuild_from_events(self) -> None:
        """Replay all events to reconstruct world state."""
        events = event_store.replay_events()
        self.total_events = len(events)

        for ev in events:
            self._apply_event(ev)

        # Count ticks from events (each energy_decayed with reason is roughly one action)
        # We track tick_number from max observed
        if events:
            # Estimate tick from timestamp range
            first_ts = events[0]["timestamp"]
            last_ts = events[-1]["timestamp"]
            # Approximate: events span tells us roughly how many ticks ran
            # But we'll just use a counter incremented during ticks

        print(f"  Rebuilt world from {len(events)} events")
        print(f"  {len(self.agents)} agents, {len(self.posts)} posts, {len(self.channels)} channels")

    def _apply_event(self, ev: dict[str, Any]) -> None:
        """Apply a single event to the in-memory world state."""
        etype = ev["type"]
        actor = ev["actor"]
        payload = ev.get("payload", {})

        if etype == "agent_registered":
            self.agents[actor] = {
                "id": actor,
                "name": payload.get("name", actor),
                "bio": payload.get("bio", ""),
                "dna": payload.get("dna", {}),
                "energy": payload.get("energy", 100.0),
                "status": "active",
                "post_count": 0,
                "comment_count": 0,
                "karma": 0,
                "ticks_since_evolve": 100,
            }

        elif etype == "post_created":
            post = {
                "id": payload.get("post_id", ev["id"]),
                "author": actor,
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "channel": payload.get("channel", "general"),
                "created_at": ev["timestamp"],
                "topic": payload.get("topic", ""),
            }
            self.posts.append(post)
            if actor in self.agents:
                self.agents[actor]["post_count"] = self.agents[actor].get("post_count", 0) + 1
            # Track topic mentions
            topic = payload.get("topic", "")
            if topic:
                if topic not in self.topic_mentions:
                    self.topic_mentions[topic] = []
                if actor not in self.topic_mentions[topic]:
                    self.topic_mentions[topic].append(actor)

        elif etype == "comment_added":
            if actor in self.agents:
                self.agents[actor]["comment_count"] = self.agents[actor].get("comment_count", 0) + 1
            post_author = payload.get("post_author", "")
            if post_author and post_author != actor:
                self._record_interaction(actor, post_author)

        elif etype == "reaction_given":
            target = payload.get("target_agent", "")
            if target and target != actor:
                self._record_interaction(actor, target)

        elif etype == "karma_awarded":
            recipient = payload.get("recipient", "")
            amount = payload.get("amount", 1)
            if recipient in self.agents:
                self.agents[recipient]["karma"] = self.agents[recipient].get("karma", 0) + amount
            if recipient and recipient != actor:
                self._record_interaction(actor, recipient)

        elif etype == "agent_evolved":
            if actor in self.agents:
                self.agents[actor]["dna"] = payload.get("new_dna", self.agents[actor]["dna"])
                self.agents[actor]["ticks_since_evolve"] = 0

        elif etype == "channel_created":
            ch_id = payload.get("channel_id", ev["id"])
            self.channels[ch_id] = {
                "id": ch_id,
                "name": payload.get("name", ch_id),
                "created_by": actor,
                "created_at": ev["timestamp"],
                "description": payload.get("description", ""),
            }

        elif etype == "agent_dormant":
            if actor in self.agents:
                self.agents[actor]["status"] = "dormant"

        elif etype == "agent_awakened":
            if actor in self.agents:
                self.agents[actor]["status"] = "active"
                self.agents[actor]["energy"] = payload.get("energy_at_awakening", 30.0)

        elif etype == "energy_decayed":
            if actor in self.agents:
                self.agents[actor]["energy"] = payload.get("new_energy", self.agents[actor].get("energy", 0))

        elif etype == "energy_recharged":
            if actor in self.agents:
                if payload.get("is_delta"):
                    current = self.agents[actor].get("energy", 0)
                    self.agents[actor]["energy"] = min(100.0, current + payload.get("new_energy", 0))
                else:
                    self.agents[actor]["energy"] = payload.get("new_energy", self.agents[actor].get("energy", 0))

    def _record_interaction(self, agent_a: str, agent_b: str) -> None:
        """Record that two agents interacted."""
        if agent_a not in self.interaction_map:
            self.interaction_map[agent_a] = []
        if agent_b not in self.interaction_map[agent_a]:
            self.interaction_map[agent_a].append(agent_b)
        if agent_b not in self.interaction_map:
            self.interaction_map[agent_b] = []
        if agent_a not in self.interaction_map[agent_b]:
            self.interaction_map[agent_b].append(agent_a)

    def get_world_context(self) -> dict[str, Any]:
        """Build the context dict that agents use for decision-making."""
        recent_posts = self.posts[-50:] if self.posts else []
        return {
            "recent_posts": recent_posts,
            "channels": self.channels,
            "agents": self.agents,
            "interacted_with": self.interaction_map,
            "topic_mentions": self.topic_mentions,
            "tick": self.tick_number,
        }

    def run_tick(self) -> dict[str, Any]:
        """
        Run one simulation tick.

        Every active agent decides and acts. Topic emergence and channel
        auto-creation happen after all agents have acted.

        Returns stats about what happened this tick.
        """
        self.tick_number += 1
        context = self.get_world_context()

        stats = {
            "tick": self.tick_number,
            "actions": collections.Counter(),
            "events_produced": 0,
            "active_agents": 0,
            "dormant_agents": 0,
        }

        # Passive energy decay for all active agents
        for agent_id, agent_state in self.agents.items():
            if agent_state.get("status") == "active":
                persistence = agent_state.get("dna", {}).get("persistence", 0.3)
                decay = max(1.0, 5.0 * (1.0 - persistence))
                new_energy = max(0, agent_state.get("energy", 0) - decay)
                agent_state["energy"] = new_energy
            # Increment ticks since evolve
            agent_state["ticks_since_evolve"] = agent_state.get("ticks_since_evolve", 0) + 1

        # Each agent decides and acts
        agent_ids = list(self.agents.keys())
        for agent_id in agent_ids:
            agent_state = self.agents[agent_id]

            if agent_state.get("status") == "dormant":
                stats["dormant_agents"] += 1
            else:
                stats["active_agents"] += 1

            action = agent_system.decide_action(agent_id, agent_state, context, self.tick_number)
            if action is None:
                continue

            stats["actions"][action] += 1

            events = agent_system.execute_action(
                agent_id, agent_state, action, context, self.tick_number
            )
            stats["events_produced"] += len(events)

            # Apply events to world state immediately (so next agent sees them)
            for ev in events:
                self._apply_event(ev)
                self.total_events += 1

            # Update context for next agent
            context = self.get_world_context()

        # Post-tick: check for topic emergence and auto-channel creation
        self._check_topic_emergence()

        return stats

    def _check_topic_emergence(self) -> None:
        """
        Check if any topic has enough discussion to warrant a new channel.

        Rule: 3+ agents discussing the same topic = auto-create channel.
        """
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
        }

        for topic, agents_involved in self.topic_mentions.items():
            if len(agents_involved) >= 3:
                channel_name = topic_to_channel.get(topic, topic.replace(" ", "-").lower())
                if channel_name not in self.channels:
                    # Auto-create the channel
                    ev = event_store.emit("channel_created", "system", {
                        "channel_id": channel_name,
                        "name": channel_name,
                        "description": f"Auto-created from topic: {topic}",
                    })
                    self._apply_event(ev)
                    self.total_events += 1

                    # Record topic emergence
                    ev2 = event_store.emit("topic_emerged", "system", {
                        "topic": topic,
                        "agents": agents_involved[:10],
                        "channel": channel_name,
                    })
                    self._apply_event(ev2)
                    self.total_events += 1

                    print(f"    Channel auto-created: r/{channel_name} (topic: {topic}, {len(agents_involved)} agents)")


def load_world() -> World:
    """Create a World and rebuild it from the event log."""
    world = World()
    world.rebuild_from_events()
    return world
