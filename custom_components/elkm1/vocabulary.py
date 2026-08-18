"""Voice vocabulary mapping for Elk-M1 integration."""

from __future__ import annotations

from collections.abc import Iterable

ELK_VOICE_VOCABULARY = {
    0: "",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
    100: "hundred",
    101: "thousand",
    102: "million",
    103: "period",
    104: "point",
    105: "zero",
    106: "am",
    107: "pm",
    108: "alarm",
    109: "alert",
    110: "area",
    111: "armed",
    112: "away",
    113: "stay",
    114: "instant",
    115: "night",
    116: "vacation",
    117: "disarmed",
    118: "bypassed",
    119: "trouble",
    120: "tamper",
    121: "door",
    122: "window",
    123: "motion",
    124: "smoke",
    125: "fire",
    126: "carbon monoxide",
    127: "freeze",
    128: "water",
    129: "leak",
    130: "temperature",
    131: "humidity",
    132: "battery",
    133: "low",
    134: "high",
    135: "normal",
    136: "warning",
    137: "emergency",
    138: "police",
    139: "medical",
    140: "security",
    141: "system",
    142: "zone",
    143: "front",
    144: "back",
    145: "side",
    146: "garage",
    147: "kitchen",
    148: "living room",
    149: "family room",
    150: "dining room",
    151: "bedroom",
    152: "master",
    153: "guest",
    154: "hallway",
    155: "stairs",
    156: "basement",
    157: "attic",
    158: "office",
    159: "patio",
    160: "deck",
    161: "porch",
    162: "yard",
    163: "driveway",
    164: "shed",
    165: "gate",
    166: "open",
    167: "closed",
    168: "on",
    169: "off",
    170: "ready",
    171: "not ready",
    172: "exit now",
    173: "entry warning",
    174: "time",
    175: "date",
    176: "good morning",
    177: "good afternoon",
    178: "good evening",
    179: "goodbye",
    180: "welcome",
}


def translate_elk_voice(word_ids: Iterable[int | str]) -> str:
    """Translate a list of Elk-M1 voice IDs into a readable string.

    Args:
        word_ids: An iterable collection of integer or string IDs representing Elk words.

    Returns:
        Space-separated human-readable translated phrase string.
    """
    translated_words: list[str] = []

    for raw_id in word_ids:
        try:
            word_id = int(raw_id)
        except (ValueError, TypeError):
            continue

        # Skip blanks and internal silence/tone identifiers
        if word_id in (0, 51, 52, 53):
            continue

        word = ELK_VOICE_VOCABULARY.get(word_id)
        if word:
            translated_words.append(word)
        else:
            translated_words.append(f"[Unknown ID: {word_id}]")

    return " ".join(translated_words).strip()
