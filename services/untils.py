import re

def normalize_string(s: str) -> str:
    """Normalize a string for duplicate checking:
       - Convert to lowercase
       - Strip leading/trailing whitespace
       - Replace any internal whitespace sequence (including multiple spaces, tabs) with a single space
    """
    if not s:
        return ""
    # Lowercase and strip
    s = s.strip().lower()
    # Collapse any whitespace sequence (space, tab, newline) to a single space
    s = re.sub(r'\s+', ' ', s)
    return s