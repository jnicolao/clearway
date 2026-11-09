"""Text helpers shared by every document template."""

from decimal import Decimal


def money(value: Decimal) -> str:
    return f"{value:,.2f}"


def wrap(text: str, width: int, lines: int = 2) -> list[str]:
    """Wrap to at most `lines`, eliding the middle rather than the tail.

    HTS descriptions are composed from a hierarchy, so items in one chapter
    share long prefixes and differ only at the end — "…, Other pig fat,
    Yellow". Truncating the tail would render several line items identically,
    which makes it ambiguous which extracted row belongs to which item.
    Eliding the middle keeps the distinguishing part and reads the way real
    shipping paperwork abbreviates.
    """
    budget = width * lines
    if len(text) > budget:
        head = budget // 2 - 2
        tail = budget - head - 3
        text = f"{text[:head].rstrip()}... {text[-tail:].lstrip()}"

    out: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            out.append(current)
            current = word
        if len(out) == lines:
            break
    if current and len(out) < lines:
        out.append(current)
    return out
