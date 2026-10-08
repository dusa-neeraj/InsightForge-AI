import re

MAX_PARTS = 15
NUMBERED_RE = re.compile(r"(?:^|\s)\d{1,2}[.)]\s+")  # "1. " or "2) "
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s*")


def _clean(part: str) -> str:
    return part.strip().strip(";,.").strip()


def split_question(text: str) -> list[str]:
    """Split a message that contains several requests. A single question comes back unchanged."""
    text = (text or "").strip()

    # "Give me: 1. Total sales 2. Total profit ..."
    if NUMBERED_RE.search(text):
        items = [_clean(piece) for piece in NUMBERED_RE.split(text)[1:]]  # [0] is the lead-in
        items = [item for item in items if item]
        if len(items) >= 2:
            return items

    # one request per line, optionally with bullets
    raw = [line for line in text.splitlines() if line.strip()]
    if len(raw) >= 2:
        bulleted = sum(1 for line in raw if BULLET_RE.match(line))
        lines = [_clean(BULLET_RE.sub("", line)) for line in raw]
        if not BULLET_RE.match(raw[0]) and lines[0].endswith(":"):
            lines = lines[1:]  # a lead-in such as "Analyze this dataset:"
        lines = [line for line in lines if line]
        if len(lines) >= 2 and (bulleted >= 2 or all(len(line) <= 100 for line in lines)):
            return lines

    # several questions in a row
    questions = [piece.strip() for piece in re.split(r"(?<=\?)\s+", text) if piece.strip()]
    if len(questions) >= 2:
        return questions

    return [text]