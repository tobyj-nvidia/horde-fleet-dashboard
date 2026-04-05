"""Server-side SVG line chart generator for the Horde Fleet Dashboard."""

from datetime import datetime


def render_line_chart(
    series: list[dict],
    width: int = 800,
    height: int = 200,
    y_label: str = "%",
    y_min: float = 0,
    y_max: float = 100,
    show_grid: bool = True,
) -> str:
    """Generate an SVG line chart string.

    Args:
        series: List of dicts with keys: label, color, data (list of {x: datetime, y: float})
        width: SVG width in pixels
        height: SVG height in pixels
        y_label: Label for y-axis unit
        y_min: Minimum y value
        y_max: Maximum y value
        show_grid: Whether to render horizontal gridlines

    Returns:
        SVG markup as a string.
    """
    PAD_LEFT = 48
    PAD_RIGHT = 16
    PAD_TOP = 12
    PAD_BOTTOM = 36
    LEGEND_HEIGHT = 20

    chart_w = width - PAD_LEFT - PAD_RIGHT
    chart_h = height - PAD_TOP - PAD_BOTTOM - LEGEND_HEIGHT

    # Collect all x values across all series to determine domain
    all_x: list[datetime] = []
    for s in series:
        for pt in s.get("data", []):
            if isinstance(pt["x"], datetime):
                all_x.append(pt["x"])

    if not all_x:
        # Return empty placeholder
        return (
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="{width//2}" y="{height//2}" text-anchor="middle" '
            f'fill="#a0a0c0" font-size="12">No data</text></svg>'
        )

    x_min = min(all_x)
    x_max = max(all_x)
    x_range = (x_max - x_min).total_seconds()
    if x_range == 0:
        x_range = 1

    y_range = y_max - y_min
    if y_range == 0:
        y_range = 1

    def to_svg_x(dt: datetime) -> float:
        return PAD_LEFT + (dt - x_min).total_seconds() / x_range * chart_w

    def to_svg_y(val: float) -> float:
        clamped = max(y_min, min(y_max, val))
        return PAD_TOP + (1.0 - (clamped - y_min) / y_range) * chart_h

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="font-family:system-ui,sans-serif;">'
    )

    # Background rect
    parts.append(
        f'<rect x="{PAD_LEFT}" y="{PAD_TOP}" width="{chart_w}" height="{chart_h}" '
        f'fill="#0f0f1e" rx="2"/>'
    )

    # Gridlines & y-axis labels
    if show_grid:
        grid_values = [y_min, y_min + y_range * 0.25, y_min + y_range * 0.5,
                       y_min + y_range * 0.75, y_max]
        for gv in grid_values:
            gy = to_svg_y(gv)
            parts.append(
                f'<line x1="{PAD_LEFT}" y1="{gy:.1f}" x2="{PAD_LEFT + chart_w}" y2="{gy:.1f}" '
                f'stroke="#3a3a5a" stroke-width="1"/>'
            )
            label = f"{int(gv)}{y_label}"
            parts.append(
                f'<text x="{PAD_LEFT - 4}" y="{gy + 4:.1f}" text-anchor="end" '
                f'fill="#a0a0c0" font-size="10">{label}</text>'
            )

    # X-axis labels: show every 6 hours
    from datetime import timedelta
    total_hours = x_range / 3600
    if total_hours <= 12:
        tick_interval_h = 2
    elif total_hours <= 24:
        tick_interval_h = 4
    else:
        tick_interval_h = 6

    # Start from first tick boundary
    import math
    first_tick_ts = math.ceil(x_min.timestamp() / (tick_interval_h * 3600)) * (tick_interval_h * 3600)
    tick_ts = first_tick_ts
    while tick_ts <= x_max.timestamp():
        tick_dt = datetime.utcfromtimestamp(tick_ts)
        tx = PAD_LEFT + (tick_ts - x_min.timestamp()) / x_range * chart_w
        # tick line
        parts.append(
            f'<line x1="{tx:.1f}" y1="{PAD_TOP + chart_h}" x2="{tx:.1f}" '
            f'y2="{PAD_TOP + chart_h + 4}" stroke="#3a3a5a" stroke-width="1"/>'
        )
        label = tick_dt.strftime("%H:%M")
        parts.append(
            f'<text x="{tx:.1f}" y="{PAD_TOP + chart_h + 14}" text-anchor="middle" '
            f'fill="#a0a0c0" font-size="9">{label}</text>'
        )
        tick_ts += tick_interval_h * 3600

    # Axis border lines
    parts.append(
        f'<line x1="{PAD_LEFT}" y1="{PAD_TOP}" x2="{PAD_LEFT}" y2="{PAD_TOP + chart_h}" '
        f'stroke="#3a3a5a" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{PAD_LEFT}" y1="{PAD_TOP + chart_h}" '
        f'x2="{PAD_LEFT + chart_w}" y2="{PAD_TOP + chart_h}" '
        f'stroke="#3a3a5a" stroke-width="1"/>'
    )

    # Series lines
    for s in series:
        data = s.get("data", [])
        if not data:
            continue
        color = s.get("color", "#ffffff")
        points = " ".join(
            f"{to_svg_x(pt['x']):.1f},{to_svg_y(float(pt['y'] or 0)):.1f}"
            for pt in data
            if isinstance(pt["x"], datetime)
        )
        if points:
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" '
                f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
            )

    # Legend
    legend_y = PAD_TOP + chart_h + LEGEND_HEIGHT + 18
    lx = PAD_LEFT
    for s in series:
        color = s.get("color", "#ffffff")
        label = s.get("label", "")
        parts.append(
            f'<rect x="{lx}" y="{legend_y - 8}" width="12" height="3" fill="{color}" rx="1"/>'
        )
        parts.append(
            f'<text x="{lx + 16}" y="{legend_y}" fill="#a0a0c0" font-size="10">{label}</text>'
        )
        lx += len(label) * 7 + 28

    parts.append("</svg>")
    return "".join(parts)
