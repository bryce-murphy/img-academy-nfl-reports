"""Field diagrams for recorded plays: which plays get one, where the marks go, and the SVG.

Pure functions. The offense always moves left to right; x = 100 - yardline_100 (0 = the offense's goal line).
Only where a play started and ended is drawn; nothing about player movement is invented.
"""
from __future__ import annotations

from html import escape

SPECIAL_TEAMS = {"kickoff", "punt", "field_goal", "extra_point"}
TEXT_ONLY_FLAGS = ("penalty", "fumble", "interception", "lateral", "qb_kneel", "qb_spike", "two_point_attempt")
DOMAIN = (-10, 110)
MIN_WIDTH = 30
CAPTION = "Where the play started and ended; not a tracking diagram."
SIZES = {"strip": (320, 56), "medium": (480, 90), "large": (960, 160)}
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def kind(play):
    """'sack' | 'run' | 'complete' | 'incomplete', or None when the play is shown as text only."""
    if play.get("play_type") in SPECIAL_TEAMS | {"no_play", "", None}:
        return None
    if any(play.get(flag) == 1 for flag in TEXT_ONLY_FLAGS):
        return None
    spot, gained, to_go = play.get("yardline_100"), play.get("yards_gained"), play.get("ydstogo")
    if spot is None or not 1 <= spot <= 99 or gained is None or to_go is None or not 1 <= to_go <= 99:
        return None
    if play.get("sack") == 1:
        return "sack"
    if play.get("rush_attempt") == 1:
        return "run"
    if play.get("pass_attempt") == 1 and play.get("air_yards") is not None:
        return "complete" if play.get("complete_pass") == 1 else "incomplete"
    return None


def geometry(play):
    """Marks in field yards, or None for text-only plays."""
    shape = kind(play)
    if shape is None:
        return None
    x0 = 100 - play["yardline_100"]
    marker = 100 if play.get("goal_to_go") == 1 else min(x0 + play["ydstogo"], 100)
    end = x0 + play["yards_gained"]
    air_end = x0 + play["air_yards"] if shape in ("complete", "incomplete") else None
    points = [x0, marker, end] + ([air_end] if air_end is not None else [])
    lo, hi = min(points) - 10, max(points) + 10
    if hi - lo < MIN_WIDTH:
        pad = (MIN_WIDTH - (hi - lo)) / 2
        lo, hi = lo - pad, hi + pad
    lo, hi = max(lo, DOMAIN[0]), min(hi, DOMAIN[1])
    if hi - lo < MIN_WIDTH:
        lo, hi = (DOMAIN[0], DOMAIN[0] + MIN_WIDTH) if lo == DOMAIN[0] else (DOMAIN[1] - MIN_WIDTH, DOMAIN[1])
    return {"kind": shape, "x0": x0, "marker": marker, "air_end": air_end, "end": end, "lo": lo, "hi": hi}


def spot_line(play):
    down, spot = play.get("down"), play.get("yardline_100")
    if down not in ORDINALS or spot is None:
        return ""
    goal_to_go = play.get("goal_to_go") == 1
    if not goal_to_go and play.get("ydstogo") is None:
        return ""
    distance = "goal" if goal_to_go else play.get("ydstogo")
    if spot == 50:
        where = "midfield"
    elif spot < 50:
        where = f"the {play.get('defense', '')} {spot}"
    else:
        where = f"the {play.get('offense', '')} {100 - spot}"
    return f"{ORDINALS[down]} & {distance} at {where}"


def _yards(n):
    return f"{n} yard" if n == 1 else f"{n} yards"


def result_line(play):
    shape, gained = kind(play), play.get("yards_gained")
    if shape == "sack":
        return "Sacked for no gain" if gained == 0 else f"Sacked for a loss of {abs(gained)}"
    if shape == "run":
        return "Run for no gain" if gained == 0 else (f"Run for a loss of {abs(gained)}" if gained < 0 else f"Run for {_yards(gained)}")
    if shape == "complete":
        return f"Complete for {_yards(gained)}"
    if shape == "incomplete":
        return "Incomplete"
    return None


def svg(play, size, team_color="#0057b8"):
    g = geometry(play)
    if g is None:
        return None
    width, height = SIZES[size]
    scale = width / (g["hi"] - g["lo"])
    x = lambda yards: round((yards - g["lo"]) * scale, 1)
    mid = height / 2
    label = escape(". ".join(t for t in (spot_line(play), result_line(play)) if t), quote=True)
    parts = [f'<svg class="field field-{size}" viewBox="0 0 {width} {height}" role="img" aria-label="{label}" xmlns="http://www.w3.org/2000/svg">',
             f'<rect class="turf" x="0" y="0" width="{width}" height="{height}"/>']
    for goal, lo, hi, team in ((0, g["lo"], 0, play.get("offense", "")), (100, 100, g["hi"], play.get("defense", ""))):
        if g["lo"] < goal < g["hi"] or (goal == 0 and g["lo"] < 0) or (goal == 100 and g["hi"] > 100):
            left, right = x(max(lo, g["lo"])), x(min(hi, g["hi"]))
            if right > left:
                parts.append(f'<rect class="endzone" x="{left}" y="0" width="{round(right - left, 1)}" height="{height}"/>')
                if size != "strip":
                    parts.append(f'<text class="endzone-label" x="{round((left + right) / 2, 1)}" y="{mid + 4}" text-anchor="middle">{escape(team)}</text>')
    for yard in range(0, 101, 5):
        if g["lo"] <= yard <= g["hi"]:
            parts.append(f'<line class="{"yard-major" if yard % 10 == 0 else "yard-minor"}" x1="{x(yard)}" y1="0" x2="{x(yard)}" y2="{height}"/>')
    parts.append(f'<line class="los" x1="{x(g["x0"])}" y1="0" x2="{x(g["x0"])}" y2="{height}"/>')
    parts.append(f'<line class="marker" x1="{x(g["marker"])}" y1="0" x2="{x(g["marker"])}" y2="{height}"/>')
    if g["air_end"] is not None:
        top = max(6, mid - height * 0.35)
        parts.append(f'<path class="air" d="M{x(g["x0"])} {mid} Q{round((x(g["x0"]) + x(g["air_end"])) / 2, 1)} {top} {x(g["air_end"])} {mid}"/>')
        if g["kind"] == "complete":
            parts.append(f'<line class="run" x1="{x(g["air_end"])}" y1="{mid}" x2="{x(g["end"])}" y2="{mid}" style="stroke:{escape(team_color)}"/>')
        else:
            parts.append(f'<circle class="target" cx="{x(g["air_end"])}" cy="{mid}" r="4"/>')
    else:
        parts.append(f'<line class="run" x1="{x(g["x0"])}" y1="{mid}" x2="{x(g["end"])}" y2="{mid}" style="stroke:{escape(team_color)}"/>')
    if g["kind"] != "incomplete":
        parts.append(f'<circle class="ball" cx="{x(g["end"])}" cy="{mid}" r="4"/>')
    parts.append("</svg>")
    return "".join(parts)
