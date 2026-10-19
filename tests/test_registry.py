import pytest

from feature_store.definitions import Entity, Feature, FeatureType, FeatureView
from feature_store.errors import EntityNotFoundError, FeatureViewNotFoundError, RegistryError
from feature_store.registry import FeatureRegistry


def test_demo_registry_contents(registry):
    assert [e.name for e in registry.list_entities()] == ["customer", "product"]
    names = [v.name for v in registry.list_views()]
    assert names == ["customer_activity", "customer_profile", "product_popularity"]
    view = registry.get_view("customer_activity")
    assert view.entity == "customer"
    assert view.ttl_seconds == 30 * 24 * 3600
    assert registry.get_view("customer_profile").ttl_seconds is None


def test_views_for_entity(registry):
    assert [v.name for v in registry.views_for_entity("customer")] == [
        "customer_activity",
        "customer_profile",
    ]


def test_duplicate_entity_rejected():
    reg = FeatureRegistry()
    reg.register_entity(Entity("customer"))
    with pytest.raises(RegistryError):
        reg.register_entity(Entity("customer"))


def test_duplicate_view_rejected(registry):
    with pytest.raises(RegistryError):
        registry.register_view(registry.get_view("customer_activity"))


def test_view_with_unknown_entity_rejected():
    reg = FeatureRegistry()
    view = FeatureView("v", "ghost", (Feature("x", FeatureType.INT),))
    with pytest.raises(RegistryError):
        reg.register_view(view)


def test_view_without_features_rejected():
    reg = FeatureRegistry()
    reg.register_entity(Entity("customer"))
    with pytest.raises(RegistryError):
        reg.register_view(FeatureView("v", "customer", ()))


def test_view_with_duplicate_feature_rejected():
    reg = FeatureRegistry()
    reg.register_entity(Entity("customer"))
    view = FeatureView(
        "v",
        "customer",
        (Feature("x", FeatureType.INT), Feature("x", FeatureType.FLOAT)),
    )
    with pytest.raises(RegistryError):
        reg.register_view(view)


def test_view_with_negative_ttl_rejected():
    reg = FeatureRegistry()
    reg.register_entity(Entity("customer"))
    view = FeatureView("v", "customer", (Feature("x", FeatureType.INT),), ttl_seconds=-1)
    with pytest.raises(RegistryError):
        reg.register_view(view)


def test_missing_lookups_raise_typed_errors(registry):
    with pytest.raises(FeatureViewNotFoundError):
        registry.get_view("nope")
    with pytest.raises(EntityNotFoundError):
        registry.get_entity("nope")
