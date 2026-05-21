"""
backend/utils/code_gen.py
Generates 6-character alphanumeric invite codes.
Excludes ambiguous characters: O, 0, I, 1
"""
import random
import string

# Alphabet: A-Z + 0-9, minus ambiguous O/0/I/1
ALPHABET = "".join(
    c for c in string.ascii_uppercase + string.digits
    if c not in {"O", "0", "I", "1"}
)  # 32 characters → 32^6 ≈ 1 billion combinations


def generate_invite_code() -> str:
    """Return a random 6-character invite code like FX39KA."""
    return "".join(random.choices(ALPHABET, k=6))


def normalize_code(code: str) -> str:
    """Uppercase and strip whitespace so codes are case-insensitive."""
    return code.strip().upper()
