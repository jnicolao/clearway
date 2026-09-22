"""ISO 6346 container numbers.

Four letters (owner code plus an equipment category), six serial digits, and
a check digit computed from the other ten characters.

The check digit is computed properly rather than faked. A downstream
validator — or an extraction model being tested on whether it read the
number correctly — can verify a generated number the same way it would
verify a real one. A random trailing digit would make that check useless.
"""

from random import Random

# A=10 ascending, skipping every multiple of 11.
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_VALUES: dict[str, int] = {}
_value = 10
for _letter in _LETTERS:
    if _value % 11 == 0:
        _value += 1
    _VALUES[_letter] = _value
    _value += 1

OWNER_CODES = ("MSCU", "MAEU", "CMAU", "OOLU", "HLCU", "TGHU", "TCNU", "SEGU")


def check_digit(body: str) -> int:
    """Check digit for the first ten characters of a container number."""
    if len(body) != 10:
        raise ValueError(f"expected 10 characters, got {len(body)}")
    total = 0
    for position, char in enumerate(body):
        value = _VALUES[char] if char.isalpha() else int(char)
        total += value * (2**position)
    remainder = total % 11
    return 0 if remainder == 10 else remainder


def is_valid(number: str) -> bool:
    number = number.replace(" ", "").upper()
    if len(number) != 11 or not number[:4].isalpha() or not number[4:].isdigit():
        return False
    return check_digit(number[:10]) == int(number[10])


def make(rng: Random) -> str:
    body = f"{rng.choice(OWNER_CODES)}{rng.randrange(0, 1_000_000):06d}"
    return f"{body}{check_digit(body)}"
