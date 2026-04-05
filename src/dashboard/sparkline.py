"""Unicode sparkline helper for the Horde Fleet Dashboard."""

_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[int]) -> str:
    """Convert a list of ints to a unicode sparkline string using 8-level block chars."""
    if not values:
        return ""
    lo = min(values)
    hi = max(values)
    span = hi - lo
    result = []
    for v in values:
        if span == 0:
            idx = 4
        else:
            idx = round((v - lo) / span * 7)
        result.append(_BLOCKS[idx])
    return "".join(result)
