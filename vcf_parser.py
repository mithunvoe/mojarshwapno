"""Parse VCF files and extract Bangladeshi phone numbers."""

import re
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class Contact:
    name: str
    phone: str  # normalized to 01XXXXXXXXX format


def normalize_bd_phone(raw: str) -> str | None:
    """Normalize a Bangladeshi phone number to 01XXXXXXXXX format.

    Returns None if not a valid BD mobile number.
    """
    digits = re.sub(r"[^\d+]", "", raw.strip())

    # Remove +880 or 880 prefix
    if digits.startswith("+880"):
        digits = "0" + digits[4:]
    elif digits.startswith("880"):
        digits = "0" + digits[3:]

    # Must be 11 digits starting with 01
    if re.fullmatch(r"01[3-9]\d{8}", digits):
        return digits
    return None


def parse_vcf(path: str | Path) -> list[Contact]:
    """Parse a VCF file and return contacts with valid BD phone numbers."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")

    contacts: list[Contact] = []
    current_name = ""

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("FN:"):
            current_name = line[3:].strip()
        elif line.startswith("TEL"):
            # TEL;CELL;PREF:01403551218 or TEL:+8801713006579
            _, _, number = line.partition(":")
            normalized = normalize_bd_phone(number)
            if normalized:
                contacts.append(Contact(name=current_name or "Unknown", phone=normalized))

    # Deduplicate by phone number, keep first occurrence
    seen: set[str] = set()
    unique: list[Contact] = []
    for c in contacts:
        if c.phone not in seen:
            seen.add(c.phone)
            unique.append(c)

    return unique
