"""Logic 6: find the flavour order with the least total changeover time."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

BRUTE_FORCE_LIMIT = 8   # 8! = 40,320 orders: well under a second


@dataclass
class Order:
    flavour_id: int
    name: str
    qty_cases: int
    due_min: float | None = None   # minutes after the day starts; None = no due time
    priority: int = 2              # 1 = must run first


@dataclass
class Plan:
    sequence: list[Order]
    changeover_min: float
    feasible: bool
    finishes: list[float] = field(default_factory=list)   # minutes after day start
    steps: list[tuple[str, str, float]] = field(default_factory=list)
    method: str = ""


def evaluate(start_id: int, seq: list[Order], cost: dict, cases_per_hour: float,
             start_name: str = "") -> Plan:
    t, total, prev, prev_name = 0.0, 0.0, start_id, start_name
    finishes, steps, feasible = [], [], True
    for o in seq:
        c = 0.0 if prev == o.flavour_id else cost[(prev, o.flavour_id)]
        steps.append((prev_name, o.name, c))
        total += c
        t += c + 60.0 * o.qty_cases / cases_per_hour
        finishes.append(t)
        if o.due_min is not None and t > o.due_min:
            feasible = False
        prev, prev_name = o.flavour_id, o.name
    return Plan(list(seq), total, feasible, finishes, steps)


def _respects_priority(seq: list[Order]) -> bool:
    seen_other = False
    for o in seq:
        if o.priority == 1 and seen_other:
            return False
        if o.priority != 1:
            seen_other = True
    return True


def _neighbours(seq):
    n = len(seq)
    for i in range(n - 1):                      # reverse a segment (2-opt)
        for j in range(i + 1, n):
            yield seq[:i] + seq[i:j + 1][::-1] + seq[j + 1:]
    for i in range(n):                          # move one flavour elsewhere (or-opt)
        rest = seq[:i] + seq[i + 1:]
        for j in range(n):
            if j != i:
                yield rest[:j] + [seq[i]] + rest[j:]
    for i in range(n - 1):                      # swap two flavours
        for j in range(i + 1, n):
            c = list(seq)
            c[i], c[j] = c[j], c[i]
            yield c


def _local_search(start_id, seq, cost, rate, start_name):
    best = evaluate(start_id, seq, cost, rate, start_name)
    improved = True
    while improved:
        improved = False
        for cand in _neighbours(best.sequence):
            if not _respects_priority(cand):
                continue
            p = evaluate(start_id, cand, cost, rate, start_name)
            if (p.feasible, -p.changeover_min) > (best.feasible, -best.changeover_min):
                best, improved = p, True
                break
    return best


def _nearest_neighbour(start_id, orders, cost, first=None):
    firsts = [o for o in orders if o.priority == 1]
    rest = [o for o in orders if o.priority != 1]
    seq, prev = [], start_id
    for group in (firsts, rest):
        group = list(group)
        if first is not None and first in group and not seq:
            seq.append(first)
            group.remove(first)
            prev = first.flavour_id
        while group:
            nxt = min(group, key=lambda o: 0 if o.flavour_id == prev else cost[(prev, o.flavour_id)])
            seq.append(nxt)
            group.remove(nxt)
            prev = nxt.flavour_id
    return seq


def optimise(start_id: int, orders: list[Order], cost: dict, cases_per_hour: float,
             start_name: str = "") -> Plan:
    """Best feasible order; if none meets every due time, the cheapest order is returned
    with feasible=False so the screen can warn."""
    if not orders:
        return Plan([], 0.0, True, method="nothing to plan")
    if len(orders) <= BRUTE_FORCE_LIMIT:
        best = None
        tried = 0
        for perm in permutations(orders):
            perm = list(perm)
            if not _respects_priority(perm):
                continue
            tried += 1
            p = evaluate(start_id, perm, cost, cases_per_hour, start_name)
            if best is None or (p.feasible, -p.changeover_min) > (best.feasible, -best.changeover_min):
                best = p
        best.method = f"tried all {tried:,} orders"
        return best
    # too many to try them all: nearest neighbour from every first flavour, then local search
    best = None
    for first in orders:
        seq = _nearest_neighbour(start_id, orders, cost, first)
        p = _local_search(start_id, seq, cost, cases_per_hour, start_name)
        if best is None or (p.feasible, -p.changeover_min) > (best.feasible, -best.changeover_min):
            best = p
    best.method = "nearest neighbour + 2-opt / move / swap"
    return best
