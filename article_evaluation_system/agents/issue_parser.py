"""
Issue Parser Agent - Extracts structured information from customer issue descriptions.
"""

import logging

from . import BaseAgent, _REFUSAL_PATTERNS, _log_refusal
from ..models.issue import Issue
from ..utils.prompts import AgentPrompts

logger = logging.getLogger(__name__)


class IssueParserAgent(BaseAgent):
    """
    Agent that parses customer issue descriptions into structured data.

    Extracts product, version, error codes, symptoms, and other
    relevant information for downstream evaluation.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.ISSUE_PARSER

    def evaluate(self, issue_description: str, product_info: dict | None = None) -> Issue:
        """
        Parse a customer issue description.

        Args:
            issue_description: Raw customer issue text
            product_info: SAP product metadata from CSV (optional)

        Returns:
            Parsed Issue object
        """
        known_product = self._resolve_product(product_info)

        if not issue_description or not issue_description.strip():
            return Issue(
                product=known_product or "Unknown",
                symptoms=["No issue description provided"],
                issue_type="unknown",
                severity="low",
                raw_description=""
            )

        # Include known product context in the LLM prompt when available
        if known_product and product_info:
            user_message = f"""Parse the following customer issue:

{issue_description}

Known product (from system records — use as the authoritative product):
- Product: {product_info.get('sap_product_name', '')}
- Product Family: {product_info.get('sap_product_family', '')}
- Category Path: {product_info.get('sap_path', '')}
- Product Name: {product_info.get('sap_name', '')}

Extract all relevant information and respond with JSON only."""
        else:
            user_message = f"""Parse the following customer issue:

{issue_description}

Extract all relevant information and respond with JSON only."""

        try:
            response = self._call_llm(self.system_prompt, user_message)

            # Detect LLM refusal (e.g. "Sorry, I can't help with that.")
            if any(p in response.lower() for p in _REFUSAL_PATTERNS):
                _log_refusal("IssueParserAgent", response, self._refusal_context)
                logger.warning(
                    f"[IssueParserAgent] LLM refused to parse issue (using fallback): {response[:150]}"
                )
                raise ValueError("LLM refused to process the request")

            parsed_data = self._parse_json_response(response)

            # Create Issue object with parsed data
            issue = Issue.from_dict(parsed_data)
            issue.raw_description = issue_description

            # Override product with authoritative CSV value
            if known_product:
                issue.product = known_product

            # Ensure we have at least some keywords
            if not issue.keywords:
                issue.keywords = self._extract_fallback_keywords(issue_description)

            return issue

        except Exception as e:
            # Return a basic issue object on parse failure
            return Issue(
                product=known_product or self._guess_product(issue_description),
                symptoms=[issue_description[:200]],
                keywords=self._extract_fallback_keywords(issue_description),
                issue_type="troubleshooting",
                severity="medium",
                raw_description=issue_description
            )

    def _resolve_product(self, product_info: dict | None) -> str | None:
        """Extract the best product name from SAP product info, or return None."""
        if not product_info:
            return None
        # Prefer SapName (most specific), fall back to SapProductName, then family
        return (
            product_info.get('sap_name')
            or product_info.get('sap_product_name')
            or product_info.get('sap_product_family')
            or None
        )

    def _extract_fallback_keywords(self, text: str) -> list[str]:
        """Extract basic keywords when parsing fails."""
        # Common Microsoft product keywords
        products = [
            "microsoft 365", "office 365", "azure", "windows", "teams",
            "outlook", "excel", "word", "sharepoint", "onedrive",
            "entra", "intune", "exchange", "power bi", "dynamics"
        ]

        text_lower = text.lower()
        keywords = []

        # Find product mentions
        for product in products:
            if product in text_lower:
                keywords.append(product)

        # Extract potential error codes (hex or numeric patterns)
        import re
        error_patterns = re.findall(r'0x[0-9a-fA-F]+|\b\d{4,}\b', text)
        keywords.extend(error_patterns[:3])

        # Add some important words from the text
        important_words = [
            word for word in text.split()
            if len(word) > 5 and word.isalpha()
        ][:5]
        keywords.extend(important_words)

        return list(set(keywords))[:10]

    def _guess_product(self, text: str) -> str:
        """Guess the Microsoft product from text."""
        text_lower = text.lower()

        product_map = {
            "azure": "Azure",
            "office": "Microsoft 365",
            "365": "Microsoft 365",
            "teams": "Microsoft Teams",
            "outlook": "Outlook",
            "excel": "Excel",
            "word": "Word",
            "sharepoint": "SharePoint",
            "onedrive": "OneDrive",
            "windows": "Windows",
            "entra": "Microsoft Entra ID",
            "active directory": "Microsoft Entra ID",
            "intune": "Microsoft Intune",
            "exchange": "Exchange Online",
            "power bi": "Power BI",
            "dynamics": "Dynamics 365"
        }

        for keyword, product in product_map.items():
            if keyword in text_lower:
                return product

        return "Microsoft 365"  # Default fallback
