"""
Area Classification Agent - Classifies a customer issue into a product area path.
"""

import logging

from . import BaseAgent
from ..models.issue import Issue
from ..config.area_definitions import get_area_definitions

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """You are an expert support engineer classifying Microsoft {product} customer issues into area paths.

Available area paths for {product}:
{area_list}

Given the customer issue, select the SINGLE most appropriate area path from the list above.

CRITICAL: Respond ONLY with valid JSON using these EXACT field names:
{{
    "area_path": "<exact area name from the list above>",
    "area_confidence": <integer from 0 to 100>,
    "area_reasoning": "brief explanation of why this area was chosen"
}}

Rules:
- area_path MUST exactly match one of the area names listed above
- area_confidence: 80-100 = clear match, 60-79 = likely match, 40-59 = best guess
- Choose the most specific area that covers the PRIMARY topic of the issue
- If the issue spans multiple areas, pick the one that best represents the core problem"""


class AreaClassificationAgent(BaseAgent):
    """Classifies a customer issue into a product-specific area path."""

    def evaluate(self, **kwargs) -> dict:
        """Not used directly — call classify() instead."""
        raise NotImplementedError("Use classify() instead")

    def classify(self, issue: Issue) -> dict | None:
        """Classify an issue into an area path.

        Args:
            issue: Parsed Issue object (must have product and raw_description set).

        Returns:
            Dict with area_path (str), area_confidence (int), area_reasoning (str),
            or None if no area definitions are configured for this product.
        """
        area_defs = get_area_definitions(issue.product)
        if not area_defs:
            logger.info(
                f"[AreaClassificationAgent] No area definitions for product "
                f"'{issue.product}' — skipping classification"
            )
            return None

        product_label = _resolve_product_label(issue.product)
        area_list = "\n".join(
            f"- {d['name']}: {d['description']}" for d in area_defs
        )
        valid_area_names = {d["name"] for d in area_defs}

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            product=product_label,
            area_list=area_list,
        )
        user_message = (
            f"Classify this {product_label} support issue:\n\n"
            f"{issue.raw_description[:2000]}"
        )

        try:
            self._refusal_context = {"case_id": getattr(issue, "case_id", "")}
            response = self._call_llm(system_prompt, user_message)
            parsed = self._parse_json_response(response)

            area_path = str(parsed.get("area_path", "")).strip()
            area_confidence = int(parsed.get("area_confidence", 0))
            area_reasoning = str(parsed.get("area_reasoning", ""))

            # Validate area_path is one of the known areas
            if area_path not in valid_area_names:
                # Try case-insensitive fallback
                lower_map = {n.lower(): n for n in valid_area_names}
                area_path = lower_map.get(area_path.lower(), "")
                if not area_path:
                    raise ValueError(
                        f"LLM returned unknown area_path: {parsed.get('area_path')!r}"
                    )

            logger.info(
                f"[AreaClassificationAgent] area_path='{area_path}', "
                f"confidence={area_confidence}, product='{issue.product}'"
            )
            return {
                "area_path": area_path,
                "area_confidence": area_confidence,
                "area_reasoning": area_reasoning,
            }

        except Exception as e:
            logger.warning(f"[AreaClassificationAgent] Classification failed: {e}")
            return None


def _resolve_product_label(product: str) -> str:
    """Return a clean short product label for prompt building."""
    product_lower = product.lower()
    if "teams" in product_lower:
        return "Teams"
    return product
