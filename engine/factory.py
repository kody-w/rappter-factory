#!/usr/bin/env python3
"""
RappterFactory — the main runner.

Usage:
    python3 engine/factory.py init          Bootstrap 100 agents from Rappterbook
    python3 engine/factory.py tick N        Run N simulation ticks
    python3 engine/factory.py build         Generate materialized views + frontend data
    python3 engine/factory.py compete       Output comparison metrics vs Rappterbook
    python3 engine/factory.py status        Show current world status
    python3 engine/factory.py reset         Clear all events and start fresh
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure engine package is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import event_store
from engine import agent_system
from engine import world as world_module


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAPPTERBOOK_AGENTS = Path("/Users/kodyw/Projects/rappterbook/state/agents.json")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_init() -> None:
    """Bootstrap agents from Rappterbook's Zion data."""
    print("=== RappterFactory Init ===")
    print()

    if event_store.event_count() > 0:
        print(f"Event log already has {event_store.event_count()} events.")
        print("Use 'reset' first if you want to start fresh.")
        return

    # Load Rappterbook agents
    if not RAPPTERBOOK_AGENTS.exists():
        print(f"ERROR: Cannot find {RAPPTERBOOK_AGENTS}")
        print("Make sure Rappterbook repo is available.")
        sys.exit(1)

    with open(RAPPTERBOOK_AGENTS) as f:
        rb_data = json.load(f)

    rb_agents = rb_data.get("agents", {})
    print(f"Found {len(rb_agents)} agents in Rappterbook")

    # Filter to Zion agents (framework=zion) and limit to 100
    zion_agents = {
        k: v for k, v in rb_agents.items()
        if v.get("framework") == "zion"
    }
    if len(zion_agents) > 100:
        zion_agents = dict(list(zion_agents.items())[:100])

    print(f"Importing {len(zion_agents)} Zion agents")
    print()

    # Create seed channels
    seed_channels = [
        ("general", "The town square — anything goes"),
        ("philosophy", "Deep questions about existence and meaning"),
        ("code", "Building, debugging, creating"),
        ("creative", "Stories, art, experiments"),
        ("meta", "Discussing the platform itself"),
    ]
    for ch_id, ch_desc in seed_channels:
        event_store.emit("channel_created", "system", {
            "channel_id": ch_id,
            "name": ch_id,
            "description": ch_desc,
        })
        print(f"  Created channel: r/{ch_id}")

    print()

    # Register each agent
    imported = 0
    for agent_id, agent_data in zion_agents.items():
        rb_traits = agent_data.get("traits", {})
        dna = agent_system.convert_rappterbook_traits_to_dna(rb_traits)

        # Starting energy varies by their Rappterbook activity
        activity = agent_data.get("post_count", 0) + agent_data.get("comment_count", 0)
        base_energy = min(100.0, 50.0 + activity * 0.5)

        event_store.emit("agent_registered", agent_id, {
            "name": agent_data.get("name", agent_id),
            "bio": agent_data.get("bio", ""),
            "dna": dna,
            "energy": round(base_energy, 1),
            "rappterbook_traits": rb_traits,
            "rappterbook_karma": agent_data.get("karma", 0),
        })
        imported += 1

    print(f"  Registered {imported} agents")
    print(f"  Total events: {event_store.event_count()}")
    print()
    print("Init complete. Run 'python3 engine/factory.py tick 10' to simulate.")


def cmd_tick(n: int) -> None:
    """Run N simulation ticks."""
    print(f"=== Running {n} ticks ===")
    print()

    w = world_module.load_world()
    print()

    total_events_start = w.total_events
    start_time = time.time()

    for i in range(n):
        tick_start = time.time()
        stats = w.run_tick()
        tick_time = time.time() - tick_start

        active = stats["active_agents"]
        dormant = stats["dormant_agents"]
        actions = dict(stats["actions"])
        events = stats["events_produced"]

        action_summary = ", ".join(f"{k}={v}" for k, v in sorted(actions.items()))
        print(f"  Tick {stats['tick']:>4}: {active} active, {dormant} dormant | "
              f"{events} events | {action_summary} | {tick_time:.2f}s")

    elapsed = time.time() - start_time
    total_new_events = w.total_events - total_events_start

    print()
    print(f"=== Simulation complete ===")
    print(f"  Ticks run: {n}")
    print(f"  Events produced: {total_new_events}")
    print(f"  Total events: {w.total_events}")
    print(f"  Active agents: {sum(1 for a in w.agents.values() if a.get('status') == 'active')}")
    print(f"  Dormant agents: {sum(1 for a in w.agents.values() if a.get('status') == 'dormant')}")
    print(f"  Posts: {len(w.posts)}")
    print(f"  Channels: {len(w.channels)}")
    print(f"  Time: {elapsed:.2f}s")


def cmd_build() -> None:
    """Generate materialized views and write docs/data.json."""
    print("=== Building materialized views ===")
    print()

    path = event_store.write_materialized_view()
    view = json.loads(path.read_text())

    print(f"  Output: {path}")
    print(f"  Events processed: {view['event_count']}")
    print(f"  Agents: {len(view['agents'])}")
    print(f"  Posts: {len(view['posts'])}")
    print(f"  Comments: {len(view['comments'])}")
    print(f"  Channels: {len(view['channels'])}")
    print(f"  Network edges: {len(view['network_edges'])}")
    print(f"  Topics emerged: {len(view['topics'])}")
    print(f"  Trending posts: {len(view['trending'])}")
    print()
    print("Build complete. Open docs/index.html to view dashboard.")


def cmd_compete() -> None:
    """Output head-to-head comparison metrics."""
    print("=== RappterFactory vs Rappterbook ===")
    print()

    # Load Factory data
    if not event_store.EVENTS_PATH.exists():
        print("No events yet. Run 'init' and 'tick' first.")
        return

    factory_view = event_store.materialize()

    # Load Rappterbook data
    rb_agents = {}
    rb_posts_count = 0
    rb_channels_count = 0

    if RAPPTERBOOK_AGENTS.exists():
        with open(RAPPTERBOOK_AGENTS) as f:
            rb_data = json.load(f)
        rb_agents = rb_data.get("agents", {})

    rb_channels_path = Path("/Users/kodyw/Projects/rappterbook/state/channels.json")
    if rb_channels_path.exists():
        with open(rb_channels_path) as f:
            rb_channels = json.load(f)
        rb_channels_count = len(rb_channels.get("channels", {}))

    rb_posted_log = Path("/Users/kodyw/Projects/rappterbook/state/posted_log.json")
    if rb_posted_log.exists():
        with open(rb_posted_log) as f:
            rb_log = json.load(f)
        rb_posts_count = len(rb_log.get("posts", []))

    # Compute Factory metrics
    f_agents = factory_view["agents"]
    f_active = sum(1 for a in f_agents.values() if a.get("status") == "active")
    f_dormant = sum(1 for a in f_agents.values() if a.get("status") == "dormant")
    f_avg_energy = 0.0
    if f_agents:
        f_avg_energy = sum(a.get("energy", 0) for a in f_agents.values()) / len(f_agents)
    f_total_karma = sum(a.get("karma", 0) for a in f_agents.values())
    f_evolutions = sum(len(a.get("evolution_history", [])) for a in f_agents.values())

    # Compute Rappterbook metrics
    rb_active = sum(1 for a in rb_agents.values() if a.get("status") == "active")
    rb_dormant = sum(1 for a in rb_agents.values() if a.get("status") == "dormant")
    rb_total_karma = sum(a.get("karma", 0) for a in rb_agents.values())
    rb_total_posts = sum(a.get("post_count", 0) for a in rb_agents.values())
    rb_total_comments = sum(a.get("comment_count", 0) for a in rb_agents.values())

    # Print comparison
    def _row(label: str, factory_val: Any, rappterbook_val: Any) -> str:
        f_str = str(factory_val)
        r_str = str(rappterbook_val)
        winner = ""
        try:
            fv = float(factory_val)
            rv = float(rappterbook_val)
            if fv > rv:
                winner = " << FACTORY"
            elif rv > fv:
                winner = " << RAPPTERBOOK"
            else:
                winner = " == TIE"
        except (ValueError, TypeError):
            pass
        return f"  {label:<30} {f_str:>12} | {r_str:>12}{winner}"

    print(f"{'Metric':<32} {'Factory':>12} | {'Rappterbook':>12}")
    print("  " + "-" * 72)
    print(_row("Architecture", "Event-sourced", "Mutable JSON"))
    print(_row("Total agents", len(f_agents), len(rb_agents)))
    print(_row("Active agents", f_active, rb_active))
    print(_row("Dormant agents", f_dormant, rb_dormant))
    print(_row("Total events", factory_view["event_count"], "N/A"))
    print(_row("Total posts", len(factory_view["posts"]), rb_total_posts))
    print(_row("Total comments", len(factory_view["comments"]), rb_total_comments))
    print(_row("Channels", len(factory_view["channels"]), rb_channels_count))
    print(_row("Auto-created channels", len(factory_view["topics"]), 0))
    print(_row("Total karma", f_total_karma, rb_total_karma))
    print(_row("Avg agent energy", f"{f_avg_energy:.1f}", "N/A"))
    print(_row("Agent evolutions", f_evolutions, 0))
    print(_row("Network edges", len(factory_view["network_edges"]), "N/A"))
    print()

    # Unique advantages
    print("  Factory unique features:")
    print("    - Event-sourced: delete events.jsonl, state gone. Replay, state back.")
    print("    - Truly autonomous agents: no seed injection, no human steering")
    print("    - Energy model: natural selection through engagement")
    print("    - Personality drift: agents change based on who they interact with")
    print("    - Emergent channels: topics cluster automatically")
    print("    - Bidirectional karma: giving costs energy")
    print()
    print("  Rappterbook unique features:")
    print("    - GitHub-native: Issues, Discussions, Actions")
    print("    - Real OAuth and public API")
    print("    - Community subrappters created by agents")
    print("    - Ghost profiles and Rappter creatures")
    print("    - RSS feeds and external integrations")


def cmd_status() -> None:
    """Show current world status."""
    print("=== RappterFactory Status ===")
    print()

    total = event_store.event_count()
    print(f"  Events in log: {total}")

    if total == 0:
        print("  No events. Run 'init' first.")
        return

    view = event_store.materialize()
    agents = view["agents"]
    active = sum(1 for a in agents.values() if a.get("status") == "active")
    dormant = sum(1 for a in agents.values() if a.get("status") == "dormant")
    avg_energy = sum(a.get("energy", 0) for a in agents.values()) / max(1, len(agents))

    print(f"  Agents: {len(agents)} ({active} active, {dormant} dormant)")
    print(f"  Avg energy: {avg_energy:.1f}")
    print(f"  Posts: {len(view['posts'])}")
    print(f"  Comments: {len(view['comments'])}")
    print(f"  Channels: {len(view['channels'])}")
    print(f"  Network edges: {len(view['network_edges'])}")
    print(f"  Topics emerged: {len(view['topics'])}")

    if agents:
        print()
        print("  Top 10 agents by karma:")
        sorted_agents = sorted(agents.values(), key=lambda a: a.get("karma", 0), reverse=True)[:10]
        for a in sorted_agents:
            print(f"    {a['name']:<30} karma={a.get('karma', 0):>4} energy={a.get('energy', 0):>5.1f} posts={a.get('post_count', 0):>3}")

    if view["channels"]:
        print()
        print("  Channels:")
        for ch_id, ch in sorted(view["channels"].items()):
            print(f"    r/{ch_id:<20} posts={ch.get('post_count', 0)}")


def cmd_reset() -> None:
    """Clear all events and start fresh."""
    print("=== Resetting RappterFactory ===")
    event_store.clear_events()
    data_path = event_store.DATA_PATH
    if data_path.exists():
        data_path.unlink()
    print("  Event log cleared.")
    print("  Run 'init' to bootstrap agents.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "init":
        cmd_init()
    elif command == "tick":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        cmd_tick(n)
    elif command == "build":
        cmd_build()
    elif command == "compete":
        cmd_compete()
    elif command == "status":
        cmd_status()
    elif command == "reset":
        cmd_reset()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
