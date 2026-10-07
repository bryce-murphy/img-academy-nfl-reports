"""Field diagrams for recorded plays: which plays get one, where the marks go, and the SVG.

Pure functions. The offense always moves left to right; x = 100 - yardline_100 (0 = the offense's goal line).
Only where a play started and ended is drawn; nothing about player movement is invented.
"""
from __future__ import annotations

from html import escape

SPECIAL_TEAMS = {"kickoff", "punt", "field_goal", "extra_point"}
TEXT_ONLY_FLAGS = ("penalty", "fumble", "lateral", "qb_kneel", "qb_spike", "two_point_attempt")
DOMAIN = (-10, 110)
MIN_WIDTH = 30
CAPTION = "Each drawing shows where the play started and ended, not player tracking."
THROWN_SHORT = ("incomplete", "interception")  # passes that end at the target spot, with no yards after the catch
SIZES = {"card": (240, 90), "medium": (480, 120), "large": (720, 300)}
MINUS = "−"
LABEL_FONT = {"card": 16, "medium": 17, "large": 26}  # rendered .yardage sizes in static/styles.css
LABEL_GAP = 4
LABEL_CLEARANCE = 8  # room a centered label keeps from the line of scrimmage and the first-down line
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def kind(play):
    """'sack' | 'run' | 'complete' | 'incomplete' | 'interception', or None when the play is shown as text only."""
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
        if play.get("interception") == 1:
            return "interception"
        if play.get("complete_pass") == 1:
            return "complete"
        if play.get("complete_pass") == 0:
            return "incomplete"
        return None
    return None


def geometry(play):
    """Marks in field yards, or None for text-only plays."""
    shape = kind(play)
    if shape is None:
        return None
    x0 = 100 - play["yardline_100"]
    marker = 100 if play.get("goal_to_go") == 1 else min(x0 + play["ydstogo"], 100)
    end = min(x0 + play["yards_gained"], 100)
    air_end = x0 + play["air_yards"] if shape in ("complete", *THROWN_SHORT) else None
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
        return f"Sacked for a loss of {abs(gained)}" if gained < 0 else "Sacked for no gain"
    if shape == "run":
        return "Run for no gain" if gained == 0 else (f"Run for a loss of {abs(gained)}" if gained < 0 else f"Run for {_yards(gained)}")
    if shape == "complete":
        if gained > 0:
            return f"Complete for {_yards(gained)}"
        return "Complete for no gain" if gained == 0 else f"Complete for a loss of {abs(gained)}"
    if shape == "incomplete":
        return "Incomplete"
    if shape == "interception":
        return "Intercepted"
    return None


def yardage_label(play):
    shape, gained = kind(play), play.get("yards_gained")
    if shape is None:
        return None
    if shape in THROWN_SHORT:
        return "Incomplete" if shape == "incomplete" else "Intercepted"
    return f"+{gained}" if gained > 0 else ("0" if gained == 0 else f"{MINUS}{abs(gained)}")


def _clear_label(text, font, width, lx, ly, tip, origin, marker, reach, on_line):
    """Place a yardage label clear of the line of scrimmage and the first-down line. Centered over the tip first;
    then on the play's own line just past the arrowhead, ball or target, away from the line of scrimmage; then on
    the play's line just across the line of scrimmage."""
    span = len(text) * font * 0.6  # a glyph is at most about 0.6 em wide, even in a fallback font
    forward = tip >= origin
    beyond = tip + reach + LABEL_GAP if forward else tip - reach - LABEL_GAP - span
    across = origin - LABEL_GAP - span if forward else origin + LABEL_GAP
    candidates = [(lx - span / 2, ly, LABEL_CLEARANCE), (beyond, on_line, 1), (across, on_line, 1)]

    def place(index, left, y):
        if index == 0:
            return "middle", lx, ly
        # Anchor the edge nearest the line it sits beside, so the gap holds whatever the font.
        return ("start", round(left, 1), y) if left > origin else ("end", round(left + span, 1), y)

    fits = [(index, left, y, [left - pad < line < left + span + pad for line in (origin, marker)])
            for index, (left, y, pad) in enumerate(candidates) if 0 <= left and left + span <= width]
    for index, left, y, crossed in fits:
        if not any(crossed):
            return place(index, left, y)
    if fits:
        # No clear place (a wide label on a narrow field): keep off the line of scrimmage if the first-down line will
        # do, and cross as few lines as possible. The label's halo (styles.css) breaks the line beneath it.
        index, left, y, _ = min(fits, key=lambda fit: (fit[3][0], sum(fit[3]), fit[0]))
        return place(index, left, y)
    return "middle", lx, ly


def svg(play, size, outcome="", helped=None, path_color="#0057b8", zones=None):
    """Broadcast view: the offense moves left to right. `helped` colors the ball's path (the alum's team bar color when
    True, slate when False, navy when unknown); `zones` gives each end zone its team bar (fill, ink)."""
    g = geometry(play)
    if g is None:
        return None
    width, height = SIZES[size]
    scale = width / (g["hi"] - g["lo"])
    clamp = lambda yards: max(g["lo"], min(g["hi"], yards))
    x = lambda yards: round((clamp(yards) - g["lo"]) * scale, 1)
    mid = round(height * 0.45, 1)
    label = escape(". ".join(t for t in (spot_line(play), result_line(play), outcome) if t), quote=True)
    parts = [f'<svg class="field field-{size}" viewBox="0 0 {width} {height}" role="img" aria-label="{label}" xmlns="http://www.w3.org/2000/svg">',
             f'<rect class="turf" x="0" y="0" width="{width}" height="{height}"/>']
    zones = zones or {}
    for zone_side, goal, lo, hi, team in (("offense", 0, g["lo"], 0, play.get("offense", "")), ("defense", 100, 100, g["hi"], play.get("defense", ""))):
        if g["lo"] < goal < g["hi"] or (goal == 0 and g["lo"] < 0) or (goal == 100 and g["hi"] > 100):
            left, right = x(max(lo, g["lo"])), x(min(hi, g["hi"]))
            if right > left:
                fill, ink = zones.get(zone_side, (None, None))
                fill_style = f' style="fill:{escape(fill)}"' if fill else ""
                parts.append(f'<rect class="endzone" x="{left}" y="0" width="{round(right - left, 1)}" height="{height}"{fill_style}/>')
                ink_style = f' style="fill:{escape(ink)}"' if ink else ""
                parts.append(f'<text class="endzone-label" x="{round((left + right) / 2, 1)}" y="{mid + 5}" text-anchor="middle"{ink_style}>{escape(team)}</text>')
    for yard in range(0, 101, 5):
        if g["lo"] <= yard <= g["hi"]:
            parts.append(f'<line class="{"yard-major" if yard % 10 == 0 else "yard-minor"}" x1="{x(yard)}" y1="0" x2="{x(yard)}" y2="{height}"/>')
    for yard in range(1, 100):
        if yard % 5 and g["lo"] < yard < g["hi"]:
            for top in (round(height * 0.25, 1), round(height * 0.62, 1)):
                parts.append(f'<line class="hash" x1="{x(yard)}" y1="{top}" x2="{x(yard)}" y2="{round(top + 6, 1)}"/>')
    for yard in range(10, 100, 10):
        if g["lo"] + 2 <= yard <= g["hi"] - 2:
            parts.append(f'<text class="yard-number" x="{x(yard)}" y="{height - 8}" text-anchor="middle">{yard if yard <= 50 else 100 - yard}</text>')
    parts.append(f'<line class="los" x1="{x(g["x0"])}" y1="0" x2="{x(g["x0"])}" y2="{height}"/>')
    parts.append(f'<line class="marker" x1="{x(g["marker"])}" y1="0" x2="{x(g["marker"])}" y2="{height}"/>')
    state = "helped" if helped else ("hurt" if helped is False else "neutral")
    color = f' style="color:{escape(path_color)}"' if helped else ""
    parts.append(f'<g class="path path-{state}"{color}>')
    head = {"large": 12, "medium": 9, "card": 8}[size]
    radius = 5
    origin = x(g["x0"])
    if g["air_end"] is not None:
        top = max(6, mid - height * 0.32)
        parts.append(f'<path class="air" d="M{origin} {mid} Q{round((origin + x(g["air_end"])) / 2, 1)} {round(top, 1)} {x(g["air_end"])} {mid}"/>')
    gained = play["yards_gained"]
    if g["kind"] in THROWN_SHORT:
        spot = x(g["air_end"])
        if g["kind"] == "interception":  # an X where the pass was caught by the defense (the intended target spot)
            reach = radius - 1
            parts.append(f'<path class="pick" d="M{round(spot - reach, 1)} {round(mid - reach, 1)} L{round(spot + reach, 1)} {round(mid + reach, 1)} M{round(spot - reach, 1)} {round(mid + reach, 1)} L{round(spot + reach, 1)} {round(mid - reach, 1)}"/>')
        else:
            parts.append(f'<circle class="target" cx="{spot}" cy="{mid}" r="{radius}"/>')
        tip = spot
    elif gained == 0:
        parts.append(f'<circle class="ball" cx="{origin}" cy="{mid}" r="{radius}"/>')
        tip = origin
    else:
        end = x(g["end"])
        direction = 1 if gained > 0 else -1
        back = round(end - direction * head, 1)
        if abs(end - origin) > head:
            parts.append(f'<line class="run" x1="{origin}" y1="{mid}" x2="{back}" y2="{mid}"/>')
        parts.append(f'<polygon class="arrow" points="{end},{mid} {back},{round(mid - head * 0.65, 1)} {back},{round(mid + head * 0.65, 1)}"/>')
        tip = end
    if g["kind"] == "complete":
        parts.append(f'<circle class="catch" cx="{x(g["air_end"])}" cy="{mid}" r="4"/>')
    parts.append("</g>")
    text = yardage_label(play)
    if text:
        anchor, lx = "middle", round(min(max(tip, 24), width - 24), 1)
        if g["kind"] not in THROWN_SHORT and gained != 0:
            # At a goal line the tip sits on the dark end zone; keep the label on the field beside it.
            if g["end"] >= 100:
                anchor, lx = "end", round(max(x(100) - 6, 24), 1)
            elif g["end"] <= 0:
                anchor, lx = "start", round(min(x(0) + 6, width - 24), 1)
        # A completion's air arc and catch marker sit above the mid line, so its label goes below it.
        ly = mid + head + 18 if g["kind"] == "complete" else mid - head - 6
        if anchor == "middle":  # goal-line labels keep their place beside the end zone
            anchor, lx, ly = _clear_label(text, LABEL_FONT[size], width, lx, ly, tip, origin, x(g["marker"]),
                                          reach=radius if g["kind"] in THROWN_SHORT or gained == 0 else 0,  # an arrow ends at its point
                                          on_line=mid + LABEL_FONT[size] * 0.35)
        parts.append(f'<text class="yardage" x="{lx}" y="{round(ly, 1)}" text-anchor="{anchor}">{escape(text)}</text>')
    parts.append("</svg>")
    return "".join(parts)
