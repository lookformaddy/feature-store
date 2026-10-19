"""Typed errors for the feature store.

Every failure mode callers are expected to handle is a subclass of
``FeatureStoreError`` so API layers can map them uniformly (registry and
validation problems -> 4xx, missing views/entities -> 404).
"""

from __future__ import annotations


class FeatureStoreError(Exception):
    """Base class for all feature-store errors."""


class RegistryError(FeatureStoreError):
    """A definition failed registry validation."""


class FeatureViewNotFoundError(FeatureStoreError):
    def __init__(self, name: str):
        super().__init__(f"feature view not found: {name!r}")
        self.name = name


class EntityNotFoundError(FeatureStoreError):
    def __init__(self, name: str):
        super().__init__(f"entity not found: {name!r}")
        self.name = name


class FeatureValidationError(FeatureStoreError):
    """A record's values do not match the view's typed feature schema."""
