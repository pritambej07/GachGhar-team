import re

INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
PHONE_INPUT_RE = re.compile(r"^[+()\d\s.-]+$")


def normalize_phone(raw):
    """Return a 10-digit Indian mobile number, or None if the input is not valid."""
    raw = raw or ""
    first_digit = next((index for index, character in enumerate(raw) if character.isdigit()), len(raw))
    if (
        not PHONE_INPUT_RE.fullmatch(raw)
        or raw.count("+") > 1
        or "+" in raw and raw.index("+") > first_digit
    ):
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if INDIAN_MOBILE_RE.match(digits) else None
