"""backend/utils/sanitize.py — file name sanitisation."""
import re
import os


def sanitize_filename(filename: str) -> str:
    """
    Remove path traversal characters and keep only safe characters.
    'my/../secret.pdf' → 'secret.pdf'
    """
    # Strip directory components
    filename = os.path.basename(filename)
    # Replace anything that isn't alphanumeric, dot, dash, underscore, space
    filename = re.sub(r"[^\w.\- ]", "_", filename)
    # Collapse multiple underscores/spaces
    filename = re.sub(r"[_\s]{2,}", "_", filename).strip("_")
    return filename or "unnamed_file"
