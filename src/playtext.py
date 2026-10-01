"""Plain-language lines for player week pages: one sentence per play, outcome tags and a game summary.

Pure functions over saved play records. Every number comes from the play's own fields; a missing value makes a
simpler sentence, never a zero. When no template fits, the play-by-play text is shown, cleaned. Nothing is invented.
"""
from __future__ import annotations

import re

from .editorial import NAME_SUFFIXES
from .players import nickname

CLOCK = re.compile(r"^\(\d{1,2}:\d{2}\)\s*")
FORMATION = re.compile(r"\((?:No Huddle, )?Shotgun\)\s*|\(No Huddle\)\s*")
JERSEY = re.compile(r"\b\d{1,2}-(?=[A-Z])")
PBP_NAME = re.compile(r"[A-Z][a-z]{0,2}\.\s?(.+)")
SACKS = {"sack", "half_sack_1", "half_sack_2"}
FORCED = {"forced_fumble_player_1", "forced_fumble_player_2"}
BREAKUPS = {"pass_defense_1", "pass_defense_2"}
SOLO = {"solo_tackle_1", "solo_tackle_2", "tackle_with_assist_1", "tackle_with_assist_2", "tackle_for_loss_1", "tackle_for_loss_2"}
ASSISTS = {"assist_tackle_1", "assist_tackle_2", "assist_tackle_3", "assist_tackle_4"}
SPECIAL_TEAMS = {"kickoff", "punt", "field_goal", "extra_point"}
STOPS = ("3rd-down stop", "4th-down stop")


def last_name(pbp_name):
    """'J.Goff' -> 'Goff', 'A.St. Brown' -> 'St. Brown'; other shapes as written; blank -> None."""
    if not pbp_name or not pbp_name.strip():
        return None
    match = PBP_NAME.fullmatch(pbp_name.strip())
    return match.group(1) if match else pbp_name.strip()


def alum_name(full_name):
    parts = [part for part in full_name.split() if part not in NAME_SUFFIXES]
    return parts[-1] if parts else full_name


def clean_description(text):
    text = CLOCK.sub("", text or "")
    text = FORMATION.sub("", text)
    text = JERSEY.sub("", text)
    return " ".join(text.split())


def _yards(n):
    return f"{n} yard" if n == 1 else f"{n} yards"


def _a(n):
    """'a 10-yard', 'an 8-yard', 'an 11-yard', 'an 18-yard'."""
    return f"an {n}" if str(n).startswith("8") or n in (11, 18) else f"a {n}"


def _even(play):
    try:
        return int(float(play.get("play_id") or 0)) % 2 == 0
    except ValueError:
        return True


def _blocked(play, roles):
    """Flags whose meaning the templates can't carry; the alum's own takeaway role is the exception."""
    if play.get("play_type") in SPECIAL_TEAMS or play.get("penalty") == 1 or play.get("lateral") == 1 or play.get("two_point_attempt") == 1:
        return True
    if play.get("interception") == 1 and "interception" not in roles:
        return True
    return play.get("fumble") == 1 and not roles & (FORCED | {"fumble_recovery_1", "fumble_recovery_2"})


def _template(play, me, roles):
    if _blocked(play, roles):
        return None
    gained = play.get("yards_gained")
    qb, runner, target = (last_name(play.get(k)) for k in ("passer_name", "rusher_name", "receiver_name"))
    pick = lambda first, second: first if _even(play) else second
    if "interception" in roles:
        return pick(f"{me} intercepted {qb}.", f"{me} picked off {qb}.") if qb else None
    if roles & SACKS:
        if not qb:
            return None
        verb = f"{me} sacked {qb}" if "sack" in roles else f"{me} shared a sack of {qb}"
        if gained is None:
            return f"{verb}."
        if gained == 0:
            return f"{verb} for no gain."
        if gained < 0 and "sack" in roles:
            return pick(f"{verb} for {_a(abs(gained))}-yard loss.", f"{me} brought down {qb} for {_a(abs(gained))}-yard sack.")
        return f"{verb} for {_a(abs(gained))}-yard loss." if gained < 0 else f"{verb}."
    if roles & FORCED:
        return pick(f"{me} forced a fumble.", f"{me} knocked the ball loose.")
    if roles & BREAKUPS:
        if not qb:
            return None
        thrown = f"{qb}'s pass to {target}" if target else f"{qb}'s pass"
        return pick(f"{me} broke up {thrown}.", f"{me} got a hand on {thrown}.")
    if roles & (SOLO | ASSISTS):
        return _tackle(play, me, roles, gained, runner, target, pick)
    if "passer" in roles:
        return _passer(play, me, gained, target, pick)
    if "rusher" in roles:
        if gained is None:
            return f"{me} ran the ball."
        if gained > 0:
            return pick(f"{me} ran for {_yards(gained)}.", f"{me} picked up {_yards(gained)} on the ground.")
        return f"{me} was stopped for no gain." if gained == 0 else f"{me} lost {_yards(abs(gained))}."
    if "receiver" in roles:
        source = f" from {qb}" if qb else ""
        if play.get("complete_pass") == 1:
            if gained is None:
                return f"{me} caught a pass{source}."
            if gained > 0:
                return pick(f"{me} caught {_a(gained)}-yard pass{source}.", f"{qb} hit {me} for {_yards(gained)}." if qb else f"{me} caught {_a(gained)}-yard pass.")
            return f"{me} caught a pass{source} for no gain." if gained == 0 else f"{me} caught a pass{source} but lost {_yards(abs(gained))}."
        if play.get("complete_pass") == 0:
            return f"{qb}'s pass to {me} fell incomplete." if qb else f"A pass to {me} fell incomplete."
    return None


def _tackle(play, me, roles, gained, runner, target, pick):
    solo = bool(roles & SOLO)
    bring, stop = ("brought down", "stopped") if solo else ("helped bring down", "helped stop")
    made = "made the tackle" if solo else "helped make the tackle"
    if play.get("complete_pass") == 1 and target:
        who, after = target, "catch"
    elif play.get("rush_attempt") == 1 and runner:
        who, after = runner, "run"
    else:
        return None
    if gained is None:
        return f"{me} {bring} {who}."
    if gained > 0 and after == "catch":
        return pick(f"{me} {bring} {who} after {_a(gained)}-yard catch.", f"{who} caught {_a(gained)}-yard pass before {me} {made}.")
    if gained > 0:
        return pick(f"{me} {stop} {who} after {_a(gained)}-yard run.", f"{who} ran for {_yards(gained)} before {me} {made}.")
    tail = " after the catch" if after == "catch" else ""
    return f"{me} {stop} {who} for no gain{tail}." if gained == 0 else f"{me} {stop} {who} for {_a(abs(gained))}-yard loss{tail}."


def _passer(play, me, gained, target, pick):
    if play.get("sack") == 1:
        if gained is None:
            return f"{me} was sacked."
        return f"{me} was sacked for no gain." if gained == 0 else f"{me} was sacked for {_a(abs(gained))}-yard loss."
    if not target:
        return f"{me}'s pass fell incomplete." if play.get("complete_pass") == 0 else None
    if play.get("complete_pass") == 1:
        if gained is None:
            return f"{me} completed a pass to {target}."
        if gained > 0:
            return pick(f"{me} completed {_a(gained)}-yard pass to {target}.", f"{me} found {target} for {_yards(gained)}.")
        return f"{me} completed a pass to {target} for no gain." if gained == 0 else f"{me} completed a pass to {target} for {_a(abs(gained))}-yard loss."
    if play.get("complete_pass") == 0:
        return f"{me}'s pass to {target} fell incomplete."
    return None


def play_line(play, player):
    """One plain sentence for the alum's part in the play, or the cleaned play-by-play text."""
    roles = set(play.get("roles") or [])
    line = _template(play, alum_name(player["name"]), roles)
    if line is None:
        return clean_description(play.get("description", ""))
    if "td" in roles:
        line = line[:-1] + " for a touchdown."
    if play.get("impact") in STOPS and play.get("offense_name"):
        line = f"{line[:-1]}, stopping the {nickname(play['offense_name'])} on {play['impact'][:3]} down."
    return line
