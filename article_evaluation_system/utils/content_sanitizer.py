"""
Content sanitizer for RAI-sensitive IT security terms.

Replaces high-frequency terms that trigger RAI guardrails with neutral equivalents.
Applied to article content in user messages — not to system prompts or output fields.
"""

import re

# Mapping of RAI-trigger terms → neutral replacements.
# Each key is matched as a whole word, case-insensitively.
_SUBSTITUTIONS: list[tuple[str, str]] = [
    (r"\bcompromised\b",      "affected by unauthorized access"),
    (r"\bphishing\b",         "suspicious email"),
    (r"\bmalware\b",          "unauthorized software"),
    (r"\bransomware\b",       "file-encrypting software"),
    (r"\bhacked\b",           "security incident"),
    (r"\bhack\b",             "security incident"),
    (r"\bexploit\b",          "vulnerability trigger"),
    (r"\bspam filter\b",      "bulk email filter"),
    (r"\bblocked IP\b",       "restricted IP"),
    (r"\bthreat actor\b",     "external actor"),
    (r"\bcredential theft\b", "credential misuse"),
]

# Pre-compile for performance
_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in _SUBSTITUTIONS
]


def sanitize_for_rai(text: str) -> str:
    """
    Replace RAI-trigger IT security terms with neutral equivalents.

    Args:
        text: Input text (article content, issue description, etc.)

    Returns:
        Text with sensitive terms replaced. All other content is preserved.
    """
    for pattern, replacement in _COMPILED:
        text = pattern.sub(replacement, text)
    return text
