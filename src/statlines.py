"""Plain-language sentences for charted (FTN Data, Pro Football Reference) and tracking (NFL Next Gen Stats) numbers.

Each builder returns a list of sentences without their final periods, so a season line can put its
"(based on N of M weeks)" note before the last one. Coverage is the charter's call on whom a pass was thrown at:
never say a defender "allowed" anything, and never grade a number.
"""
PFR = "Pro Football Reference"
FTN = "FTN Data via nflverse"
NGS = "NFL Next Gen Stats"
SOURCE_ORDER = (PFR, FTN, NGS)


def _n(count, word, plural=None):
    return f"{count:g} {word if count == 1 else plural or word + 's'}"


def _times(count):
    return {1: "once", 2: "twice"}.get(count, f"{count:g} times")


def sentence(parts, note=""):
    return ". ".join(parts) + note + "."


def targets(t):
    """FTN target charting: catchable, drops, contested catches. Season totals carry no contested counts."""
    charted, catchable = t["charted"], t["catchable"]
    if charted == 1:
        parts = ["His only charted target was " + ("catchable" if catchable else "not catchable")]
    elif catchable == charted:
        parts = [f"All {charted} of his charted targets were catchable"]
    elif catchable == 0:
        parts = [f"None of his {charted} charted targets were catchable"]
    else:
        parts = [f"{catchable} of his {charted} charted targets were catchable"]
    parts.append(_n(t["drops"], "drop") if t["drops"] else "No drops")
    contested, caught = t.get("contested", 0), t.get("contested_catches", 0)
    if contested == 1:
        parts.append("Caught his only contested throw" if caught else "Did not catch his only contested throw")
    elif contested == 2 and caught in (0, 2):
        parts.append("Caught both contested throws" if caught else "Caught neither contested throw")
    elif contested:
        parts.append(f"Caught {'all' if caught == contested else caught} of {contested} contested throws")
    return parts


def coverage(c):
    """PFR coverage: the throws on which the charter named him the defender, and what became of them."""
    thrown, completed = c["targets"], c["completions"]
    parts = [f"Thrown at {'one time' if thrown == 1 else _n(thrown, 'time')} in coverage"]
    yards = _n(c["yards"], "yard")
    if thrown == 1:
        parts.append(f"It was completed, for {yards}" if completed else "It was not completed")
    elif completed == 0:
        parts.append("Neither was completed" if thrown == 2 else "None was completed")
    elif completed == thrown:
        parts.append(f"{'Both' if thrown == 2 else f'All {thrown}'} were completed, for {yards}")
    else:
        parts.append(f"{completed} {'was' if completed == 1 else 'were'} completed, for {yards}")
    if c.get("touchdowns"):
        parts.append(f"{c['touchdowns']} went for {'a touchdown' if c['touchdowns'] == 1 else 'touchdowns'}")
    if c.get("interceptions"):
        parts.append(f"Intercepted {_n(c['interceptions'], 'pass', 'passes')}")
    return parts


def pass_rush(r):
    """PFR pass rush. A pressure is a hurry, quarterback hit or sack play; sacks can be halves."""
    pressures, blitzes = r["pressures"], r["blitzes"]
    if not pressures:
        return [f"Blitzed {_times(blitzes)}, without a pressure"] if blitzes else []
    detail = [_n(r[key], *words) for key, words in (("sacks", ("sack",)), ("qb_hits", ("hit",)), ("hurries", ("hurry", "hurries"))) if r[key]]
    text = f"Pressured the quarterback {_times(pressures)}"
    if pressures == 1 and len(detail) == 1 and detail[0].startswith("1 "):
        text += ", with a " + detail[0][2:]
    elif detail:
        text += f" ({', '.join(detail)})"
    return [text] + ([f"Blitzed {_times(blitzes)}"] if blitzes else [])


def pressures(count):
    """Season pass rush: total pressures only. Zero is never shown (an all-zero week is not stored)."""
    return [f"Pressured the quarterback {_times(count)}"] if count else []


def tackling(missed, attempts):
    """PFR tackling: `attempts` is credited tackles (assists included) plus charted misses."""
    made = attempts - missed
    if not made:
        return [f"Missed {_n(missed, 'tackle')} and made none"]
    return [f"Made {_n(made, 'tackle')} and missed {missed or 'none'}"]


def rushing(u):
    """PFR contact yards. Yards before contact can be negative, so 'X of his Y' only when X fits inside Y."""
    after, total = u["after_contact"], u["before_contact"] + u["after_contact"]
    if 0 <= after <= total:
        parts = [f"Gained {after} of his {_n(total, 'rushing yard')} after first contact"]
    else:
        parts = [f"Gained {_n(after, 'yard')} after first contact, on {_n(total, 'rushing yard')} in all"]
    return parts + ([f"Broke {_n(u['broken_tackles'], 'tackle')}"] if u["broken_tackles"] else [])


def broken_after_catch(count):
    return [f"Broke {_n(count, 'tackle')} after the catch"]


def _tenths(value):
    """One decimal, with -0.0 read as 0.0 so a tiny negative never says '0.0 fewer'."""
    return round(value, 1) + 0.0


def tracking(next_gen):
    """NGS sentences by source: {"ngs_receiving": [...], "ngs_rushing": [...], "ngs_passing": [...]}."""
    by_label = {m["label"]: m for m in next_gen or []}
    value = lambda label: _tenths(by_label[label]["value"]) if label in by_label else None
    out = {"ngs_receiving": [], "ngs_rushing": [], "ngs_passing": []}
    separation, yac = value("Average separation"), value("YAC above expectation per catch")
    if separation is not None:
        out["ngs_receiving"].append([f"Defenders were {separation:.1f} yards away, on average, when passes reached him"])
    if yac is not None:
        out["ngs_receiving"].append([f"Averaged {abs(yac):.1f} {'more' if yac > 0 else 'fewer'} yards after the catch than expected"]
                                    if yac else ["Matched the expected yards after the catch"])
    ryoe, per_carry = value("Rushing yards over expected"), value("RYOE per carry")
    if ryoe is not None:
        text = f"Ran for {abs(ryoe):.1f} {'more' if ryoe > 0 else 'fewer'} yards than expected" if ryoe else "Ran for the expected yards"
        out["ngs_rushing"].append([text + (f" ({per_carry:.1f} per carry)" if per_carry is not None else "")])
    time_to_throw, cpoe = value("Time to throw"), value("Completion above expectation")
    if time_to_throw is not None:
        out["ngs_passing"].append([f"Averaged {time_to_throw:.1f} seconds from snap to throw"])
    if cpoe is not None:
        out["ngs_passing"].append([f"Completed passes at a rate {abs(cpoe):.1f} percentage points {'above' if cpoe > 0 else 'below'} expected"]
                                  if cpoe else ["Completed passes at the expected rate"])
    return out


def credit(sources):
    """'Source: X.' or 'Sources: X; Y.' in a fixed order, or None."""
    used = [s for s in SOURCE_ORDER if s in sources]
    if not used:
        return None
    return f"{'Source' if len(used) == 1 else 'Sources'}: {'; '.join(used)}."
