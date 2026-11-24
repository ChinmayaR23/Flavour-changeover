"""Logic 7: SMED split + crew scheduling for one changeover.

External steps (can_be_external) are moved to before the line stops.
Internal steps are list-scheduled on the crew: whenever someone is free they take
the ready step with the longest chain of work still after it (critical path first).
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass
class Task:
    id: int
    name: str
    minutes: float
    external: bool = False
    depends_on: tuple[int, ...] = ()


@dataclass
class Slot:
    task: str
    worker: str
    start: float    # minutes from the line stopping (negative = before the stop)
    end: float
    kind: str       # "external" or "internal"
    critical: bool = False


def _tails(tasks: dict[int, Task]) -> dict[int, float]:
    """Longest path from the start of each task to the end of the whole job."""
    children: dict[int, list[int]] = {t: [] for t in tasks}
    for t in tasks.values():
        for d in t.depends_on:
            if d in children:
                children[d].append(t.id)
    memo: dict[int, float] = {}

    def tail(i: int) -> float:
        if i not in memo:
            memo[i] = tasks[i].minutes + max((tail(c) for c in children[i]), default=0.0)
        return memo[i]

    for i in tasks:
        tail(i)
    return memo


def schedule(tasks: list[Task], crew: int) -> tuple[list[Slot], float]:
    """Returns the slots and the new line-stop time in minutes."""
    crew = max(1, int(crew))
    workers = [f"Operator {chr(65 + i)}" for i in range(crew)]
    tasks = [replace(t) for t in tasks]          # never change the caller's objects
    external = [t for t in tasks if t.external]
    internal = {t.id: t for t in tasks if not t.external}
    ext_ids = {t.id for t in external}
    # an internal step waiting on an external one is fine: that one is finished before the stop
    for t in internal.values():
        t.depends_on = tuple(d for d in t.depends_on if d not in ext_ids and d in internal)

    slots: list[Slot] = []
    # external work before the stop, spread across the crew, ending at time 0
    free_before = {w: 0.0 for w in workers}
    for t in sorted(external, key=lambda x: -x.minutes):
        w = max(free_before, key=lambda k: free_before[k])  # whoever's free latest-before-stop
        end = free_before[w]
        start = end - t.minutes
        slots.append(Slot(t.name, w, start, end, "external"))
        free_before[w] = start

    tails = _tails(internal)
    done: dict[int, float] = {}
    free = {w: 0.0 for w in workers}
    remaining = set(internal)
    while remaining:
        w = min(free, key=lambda k: free[k])
        now = free[w]
        ready = [i for i in remaining if all(d in done and done[d] <= now for d in internal[i].depends_on)]
        if not ready:
            # wait until the next dependency finishes
            upcoming = [done[d] for i in remaining for d in internal[i].depends_on if d in done and done[d] > now]
            if not upcoming:
                upcoming = [min(v for k, v in free.items() if v > now)] if any(v > now for v in free.values()) else []
            if not upcoming:
                raise ValueError("Steps depend on each other in a loop; check depends_on.")
            free[w] = min(upcoming)
            continue
        i = max(ready, key=lambda k: (tails[k], -k))
        t = internal[i]
        start, end = now, now + t.minutes
        slots.append(Slot(t.name, w, start, end, "internal"))
        done[i] = end
        free[w] = end
        remaining.remove(i)

    stop_time = max((s.end for s in slots if s.kind == "internal"), default=0.0)
    _mark_critical(slots, internal, done)
    return sorted(slots, key=lambda s: (s.worker, s.start)), stop_time


def _mark_critical(slots: list[Slot], internal: dict[int, Task], done: dict[int, float]) -> None:
    """Walk back from the last step to find the chain that sets the stop time."""
    if not done:
        return
    by_name = {s.task: s for s in slots if s.kind == "internal"}
    name_of = {i: t.name for i, t in internal.items()}
    cur = max(done, key=lambda k: done[k])
    while cur is not None:
        s = by_name[name_of[cur]]
        s.critical = True
        prev = [d for d in internal[cur].depends_on if abs(done[d] - s.start) < 1e-6]
        if prev:
            cur = prev[0]
            continue
        # otherwise the step waited for a person: follow whoever finished just before on that worker
        before = [i for i, t in internal.items() if by_name[t.name].worker == s.worker
                  and abs(done[i] - s.start) < 1e-6]
        cur = before[0] if before else None


def sequential_minutes(tasks: list[Task]) -> float:
    """How long the changeover takes today if every step is done one after another."""
    return sum(t.minutes for t in tasks if not t.external)
