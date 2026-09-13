"""
Feature flags / AI capability packages.

Stores can individually toggle on/off various AI capability packages:
- ai_chat: conversational AI powered by Groq LLM
- image_search: image upload + vision analysis
- knowledge_base: web crawling + semantic search

These are admin-only toggles (PATCH /v1/admin/stores/{id}). Absence of a
key in store.enabled_features means "enabled by default" — so rolling out
new features changes nothing until an admin explicitly opts out or an old
store gets explicitly opted in.

Each route that depends on a feature calls require_feature(store, feature),
which raises HTTPException(403) if the feature is disabled. This ensures
backward compatibility: existing stores see no change in behavior until a
toggle is flipped.
"""

from __future__ import annotations

from typing import NamedTuple

from fastapi import HTTPException

from app.db.models import Store


class Feature(NamedTuple):
    """A toggleable AI capability package."""

    key: str
    label: str
    description: str


# ---------------------------------
# Feature catalog
# ---------------------------------

FEATURE_AI_CHAT = Feature(
    key="ai_chat",
    label="AI Chat",
    description="Conversational AI powered by Groq LLM",
)

FEATURE_IMAGE_SEARCH = Feature(
    key="image_search",
    label="Image Search",
    description="Image upload and vision analysis",
)

FEATURE_KNOWLEDGE_BASE = Feature(
    key="knowledge_base",
    label="Knowledge Base",
    description="Web crawling and semantic search",
)

FEATURE_DATABASE_SYNC = Feature(
    key="database_sync",
    label="Database Sync",
    description="Automatic product synchronization from databases",
)

# All available features (used for validation, catalog endpoints, etc.)
FEATURE_CATALOG = [
    FEATURE_AI_CHAT,
    FEATURE_IMAGE_SEARCH,
    FEATURE_KNOWLEDGE_BASE,
    FEATURE_DATABASE_SYNC,
]


# ---------------------------------
# Feature checking
# ---------------------------------


def is_feature_enabled(store: Store, feature: Feature) -> bool:
    """
    Check whether a store has a feature enabled.

    If the feature key is absent from store.enabled_features, it is
    enabled by default (see module docstring).
    """

    if not store.enabled_features:
        return True

    # If the key is in the dict, use its boolean value.
    # If the key is absent, default to True ("enabled").
    return store.enabled_features.get(feature.key, True)


def require_feature(store: Store, feature: Feature) -> None:
    """
    Enforce that a store has a feature enabled.

    Raises HTTPException(403) if the feature is disabled.
    """

    if not is_feature_enabled(store, feature):
        raise HTTPException(
            status_code=403,
            detail=f"Feature '{feature.label}' is not enabled for this store.",
        )


# ---------------------------------
# API responses
# ---------------------------------


def normalized_features(store: Store) -> dict[str, bool]:
    """
    Return a store's enabled_features dict, normalized for API response.

    All feature keys are included (with defaults), not just the ones
    stored in the DB.
    """

    result = {}
    for feature in FEATURE_CATALOG:
        result[feature.key] = is_feature_enabled(store, feature)

    return result


def catalog_payload() -> list[dict]:
    """
    Return the feature catalog formatted for an API response.

    Used by GET /v1/admin/features to populate admin UI dropdowns.
    """

    return [
        {
            "key": feature.key,
            "label": feature.label,
            "description": feature.description,
        }
        for feature in FEATURE_CATALOG
    ]
