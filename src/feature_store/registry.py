"""The feature registry: validated, discoverable definitions.

The registry is the single source of truth for what features exist. The
offline store, online store, materializer, and serving layer all resolve
views through it, so a definition change is visible everywhere at once —
that shared contract is what keeps training and serving in agreement.
"""

from __future__ import annotations

from .definitions import Entity, FeatureView
from .errors import EntityNotFoundError, FeatureViewNotFoundError, RegistryError


class FeatureRegistry:
    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._views: dict[str, FeatureView] = {}

    # -- entities ---------------------------------------------------------

    def register_entity(self, entity: Entity) -> Entity:
        if not entity.name:
            raise RegistryError("entity name must be non-empty")
        if entity.name in self._entities:
            raise RegistryError(f"entity already registered: {entity.name!r}")
        self._entities[entity.name] = entity
        return entity

    def get_entity(self, name: str) -> Entity:
        try:
            return self._entities[name]
        except KeyError:
            raise EntityNotFoundError(name) from None

    def list_entities(self) -> list[Entity]:
        return [self._entities[n] for n in sorted(self._entities)]

    # -- feature views ------------------------------------------------------

    def register_view(self, view: FeatureView) -> FeatureView:
        if not view.name:
            raise RegistryError("feature view name must be non-empty")
        if view.name in self._views:
            raise RegistryError(f"feature view already registered: {view.name!r}")
        if view.entity not in self._entities:
            raise RegistryError(
                f"feature view {view.name!r} references unknown entity {view.entity!r}; "
                "register the entity first"
            )
        if not view.features:
            raise RegistryError(f"feature view {view.name!r} declares no features")
        seen: set[str] = set()
        for feat in view.features:
            if feat.name in seen:
                raise RegistryError(
                    f"feature view {view.name!r} declares feature {feat.name!r} twice"
                )
            seen.add(feat.name)
        if view.ttl_seconds is not None and view.ttl_seconds < 0:
            raise RegistryError(
                f"feature view {view.name!r} has negative ttl_seconds: {view.ttl_seconds}"
            )
        self._views[view.name] = view
        return view

    def get_view(self, name: str) -> FeatureView:
        try:
            return self._views[name]
        except KeyError:
            raise FeatureViewNotFoundError(name) from None

    def list_views(self) -> list[FeatureView]:
        return [self._views[n] for n in sorted(self._views)]

    def views_for_entity(self, entity: str) -> list[FeatureView]:
        return [v for v in self.list_views() if v.entity == entity]
