"""Field diagrams for recorded plays: which plays get one, where the marks go, and the SVG.

Pure functions. The offense always moves left to right; x = 100 - yardline_100 (0 = the offense's goal line).
Only where a play started and ended is drawn; nothing about player movement is invented.
"""
from __future__ import annotations

SPECIAL_TEAMS = {"kickoff", "punt", "field_goal", "extra_point"}
TEXT_ONLY_FLAGS = ("penalty", "fumble", "interception", "lateral", "qb_kneel", "qb_spike", "two_point_attempt")
DOMAIN = (-10, 110)
MIN_WIDTH = 30


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
