"""Ticket / portfolio generation.

A "ticket" is 6 distinct numbers in [1,45]. A "portfolio" is PORTFOLIO_SIZE
tickets, each internally unique (guaranteed by sampling without replacement)
and mutually distinct from each other (no two games share the exact same
combination).
"""
import numpy as np

from lotto_quant_v3.config.settings import NUM_MIN, NUM_MAX, PICK_SIZE, PORTFOLIO_SIZE

Ticket = tuple[int, ...]


def sample_ticket(rng: np.random.Generator, weights: np.ndarray | None) -> Ticket:
    pool = np.arange(NUM_MIN, NUM_MAX + 1)
    if weights is None:
        chosen = rng.choice(pool, size=PICK_SIZE, replace=False)
    else:
        p = weights / weights.sum()
        chosen = rng.choice(pool, size=PICK_SIZE, replace=False, p=p)
    return tuple(sorted(int(x) for x in chosen))


def generate_portfolio(
    size: int = PORTFOLIO_SIZE,
    weights: np.ndarray | None = None,
    seed: int | None = None,
) -> list[Ticket]:
    """Generate `size` distinct tickets. `weights` (length 45, index i =
    number i+1) biases sampling, e.g. toward historically frequent numbers;
    pass None for uniform random."""
    rng = np.random.default_rng(seed)
    tickets: set[Ticket] = set()
    guard = 0
    while len(tickets) < size:
        guard += 1
        if guard > 10_000:
            raise RuntimeError("failed to generate a distinct portfolio (weights too skewed?)")
        tickets.add(sample_ticket(rng, weights))
    return sorted(tickets)


def random_baseline_portfolio(size: int = PORTFOLIO_SIZE, seed: int | None = None) -> list[Ticket]:
    """Uniform-random portfolio, used as the null-model benchmark (section 20)."""
    return generate_portfolio(size=size, weights=None, seed=seed)


def validate_portfolio(tickets: list[Ticket]) -> None:
    for t in tickets:
        assert len(t) == PICK_SIZE, f"ticket {t} does not have {PICK_SIZE} numbers"
        assert len(set(t)) == PICK_SIZE, f"ticket {t} has internal duplicates"
        assert all(NUM_MIN <= n <= NUM_MAX for n in t), f"ticket {t} out of range"
    assert len(set(tickets)) == len(tickets), "portfolio contains duplicate tickets"
