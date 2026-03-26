"""
Citation parser utility.

Parses AI responses with inline citation markers like [1], [2], [3]
into structured segments. Pure Python, no LLM calls.
"""

import re
from dataclasses import dataclass, field


@dataclass
class CitationSegment:
    """A segment of text attributed to one or more citations."""
    text: str
    citation_indices: list[int] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text.strip())


@dataclass
class CitationParseResult:
    """Result of parsing an AI response for citation markers."""
    segments: list[CitationSegment] = field(default_factory=list)
    total_char_count: int = 0
    unique_citation_indices: list[int] = field(default_factory=list)

    def text_for_citation(self, index: int) -> str:
        """Get all text segments attributed to a given citation index."""
        parts = [s.text.strip() for s in self.segments
                 if index in s.citation_indices and s.text.strip()]
        return " ".join(parts)

    def char_count_for_citation(self, index: int) -> int:
        """Total characters attributed to a given citation."""
        return sum(s.char_count for s in self.segments
                   if index in s.citation_indices)

    def coverage_percentage(self, index: int) -> float:
        """Percentage of total response text covered by this citation."""
        if self.total_char_count == 0:
            return 0.0
        return (self.char_count_for_citation(index) / self.total_char_count) * 100

    def uncited_percentage(self) -> float:
        """Percentage of text that has no citation."""
        if self.total_char_count == 0:
            return 0.0
        uncited_chars = sum(s.char_count for s in self.segments
                           if not s.citation_indices)
        return (uncited_chars / self.total_char_count) * 100

    def cited_percentage(self) -> float:
        """Percentage of text that has at least one citation."""
        return 100.0 - self.uncited_percentage()


# Regex: matches [N] where N is one or more digits.
# Does NOT match [REDACTED_FILEPATH] or other non-numeric brackets.
_CITATION_PATTERN = re.compile(r'\[(\d+)\]')


def parse_citations(ai_response: str) -> CitationParseResult:
    """
    Parse an AI response with inline citation markers into segments.

    Citation markers appear AFTER the text they cite, e.g.:
        "Some factual text. [3] More text here. [1]"

    This produces segments where "Some factual text." is attributed to [3],
    and "More text here." is attributed to [1].

    Args:
        ai_response: The AI-generated response text with [N] markers.

    Returns:
        CitationParseResult with parsed segments and coverage stats.
    """
    if not ai_response or not ai_response.strip():
        return CitationParseResult()

    segments: list[CitationSegment] = []
    total_text_chars = 0

    # Split on citation markers, keeping track of positions
    parts = _CITATION_PATTERN.split(ai_response)

    # parts alternates: [text, citation_num, text, citation_num, ...]
    # If response starts with text (no leading citation), parts[0] is that text.
    i = 0
    pending_text = ""

    while i < len(parts):
        if i % 2 == 0:
            # This is a text segment
            pending_text += parts[i]
            i += 1
        else:
            # This is a citation number — it applies to the pending_text
            citation_idx = int(parts[i])

            # Check if next part is also a citation (consecutive markers like [1][2])
            consecutive_citations = [citation_idx]
            j = i + 1
            while j + 1 < len(parts) and parts[j].strip() == "":
                # Empty text between citations means they're consecutive
                consecutive_citations.append(int(parts[j + 1]))
                j += 2

            text = pending_text
            if text.strip():
                total_text_chars += len(text.strip())
                segments.append(CitationSegment(
                    text=text,
                    citation_indices=consecutive_citations,
                ))

            pending_text = ""
            i = j

    # Handle any trailing uncited text
    if pending_text.strip():
        total_text_chars += len(pending_text.strip())
        segments.append(CitationSegment(
            text=pending_text,
            citation_indices=[],
        ))

    # Collect unique citation indices in order of appearance
    seen = set()
    unique_indices = []
    for seg in segments:
        for idx in seg.citation_indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

    return CitationParseResult(
        segments=segments,
        total_char_count=total_text_chars,
        unique_citation_indices=unique_indices,
    )
