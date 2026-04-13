"""
Product area path definitions for the Agentic Insight Engine.

Each product family maps to a list of area definitions. When new products
(e.g. Exchange) are added, append a new key with their taxonomy.

The AreaClassificationAgent uses these definitions to classify issues.
"""

from typing import TypedDict


class AreaDefinition(TypedDict):
    name: str
    description: str


# ---------------------------------------------------------------------------
# Area taxonomy per product family
# ---------------------------------------------------------------------------

PRODUCT_AREA_DEFINITIONS: dict[str, list[AreaDefinition]] = {
    "Teams": [
        {
            "name": "Teams Admin",
            "description": (
                "Covers reporting, licensing, Teams Admin Center (TAC), "
                "PowerShell (TPM), policies, and preview programs."
            ),
        },
        {
            "name": "Teams and Channels",
            "description": (
                "Focuses on team creation, channel types (standard, private, shared), "
                "threaded conversations, and membership."
            ),
        },
        {
            "name": "Teams and Copilot",
            "description": (
                "Covers Copilot in Teams meetings, chat, and apps; "
                "plugin behavior, licensing, Studio agents, and known issues."
            ),
        },
        {
            "name": "Teams Apps and Connectors",
            "description": (
                "Includes support for Bookings, Avatars, Graph API, Power Platform, "
                "bots, tabs, and third-party connectors."
            ),
        },
        {
            "name": "Teams Calling (PSTN)",
            "description": (
                "Covers core calling, Direct Routing, Operator Connect, "
                "emergency calling, and voice apps."
            ),
        },
        {
            "name": "Teams Chat (Messaging)",
            "description": (
                "Troubleshooting 1:1, group, and meeting chats, "
                "including delivery, UI issues, and retention."
            ),
        },
        {
            "name": "Teams Clients",
            "description": (
                "Troubleshooting Teams desktop, mobile, and web clients, "
                "including installation, updates, and UI behavior."
            ),
        },
        {
            "name": "Teams Devices",
            "description": (
                "Support for Teams-certified phones, panels, displays, "
                "Teams Rooms, and Surface Hub."
            ),
        },
        {
            "name": "Teams EDU",
            "description": (
                "Focused on education-specific features like class teams, "
                "assignments, SDS, and LMS integrations."
            ),
        },
        {
            "name": "Teams External and Guest Access",
            "description": (
                "Covers federation, guest access, tenant switching, "
                "and cross-cloud collaboration."
            ),
        },
        {
            "name": "Teams Files",
            "description": (
                "Support for file sharing, access, sync, storage, and compliance "
                "across OneDrive and SharePoint."
            ),
        },
        {
            "name": "Teams Hybrid and Migration",
            "description": (
                "Support for hybrid Exchange/Skype environments, "
                "client rollout, and migration scenarios."
            ),
        },
        {
            "name": "Teams Identity and Authentication",
            "description": (
                "Includes sign-in, token handling, conditional access, "
                "guest identity, and Entra ID integration."
            ),
        },
        {
            "name": "Teams Meetings",
            "description": (
                "Covers meeting join, chat, recording, scheduling, policies, recap, "
                "and advanced scenarios like webinars and live events."
            ),
        },
        {
            "name": "Teams Media",
            "description": (
                "Focused on media stack architecture, connectivity, quality, "
                "reliability, and diagnostics."
            ),
        },
        {
            "name": "Teams People & Presence",
            "description": (
                "Covers contact cards, org charts, presence sync, and profile data."
            ),
        },
        {
            "name": "Teams Security and Compliance",
            "description": (
                "Includes sensitivity labels, DLP, retention, auditing, "
                "eDiscovery, and Microsoft Purview."
            ),
        },
    ],
    # Future product families — add key + area list here:
    # "Exchange": [...],
}


# Maps product name variants to the canonical key in PRODUCT_AREA_DEFINITIONS.
# Case-insensitive substring matching is applied (see get_area_definitions).
_PRODUCT_ALIASES: dict[str, str] = {
    "teams": "Teams",
    "microsoft teams": "Teams",
    "ms teams": "Teams",
    # Future:
    # "exchange": "Exchange",
    # "exchange online": "Exchange",
}


def get_area_definitions(product: str) -> list[AreaDefinition] | None:
    """Return area definitions for a product, or None if not configured.

    Matching uses case-insensitive substring checks against known aliases.
    Longer aliases are checked first to avoid false matches.

    Args:
        product: Product name from the issue parser (e.g. "Microsoft Teams").

    Returns:
        List of AreaDefinition dicts, or None if the product is not configured.
    """
    product_lower = product.lower().strip()
    # Sort by length descending so more specific aliases win
    for alias in sorted(_PRODUCT_ALIASES, key=len, reverse=True):
        if alias in product_lower or product_lower in alias:
            canonical = _PRODUCT_ALIASES[alias]
            return PRODUCT_AREA_DEFINITIONS.get(canonical)
    return None
