"""Unit tests for src/registry.py."""
import logging
import pytest
from src.registry import Registry


class TestRegistry:
    def setup_method(self):
        self.reg = Registry("test")

    def test_register_and_create(self):
        @self.reg.register("k")
        class Foo:
            pass
        result = self.reg.create("k")
        assert isinstance(result, Foo)

    def test_create_unknown_key_raises(self):
        @self.reg.register("known")
        class Bar:
            pass
        with pytest.raises(ValueError, match="unknown key 'unknown_key'"):
            self.reg.create("unknown_key")

    def test_create_unknown_key_lists_available(self):
        @self.reg.register("alpha")
        class A:
            pass
        with pytest.raises(ValueError, match="alpha"):
            self.reg.create("missing")

    def test_register_duplicate_key_raises(self):
        @self.reg.register("dup")
        class First:
            pass
        with pytest.raises(ValueError, match="already registered"):
            @self.reg.register("dup")
            class Second:
                pass

    def test_register_force_overwrites(self, caplog):
        @self.reg.register("k")
        class Original:
            pass

        with caplog.at_level(logging.WARNING):
            @self.reg.register("k", force=True)
            class Replacement:
                pass

        assert "overwritten" in caplog.text or "force=True" in caplog.text
        # After force, create returns the new class
        result = self.reg.create("k")
        assert isinstance(result, Replacement)

    def test_keys_returns_registered(self):
        @self.reg.register("a")
        def fa(): pass
        @self.reg.register("b")
        def fb(): pass
        assert set(self.reg.keys()) == {"a", "b"}

    def test_contains(self):
        @self.reg.register("present")
        def fn(): pass
        assert "present" in self.reg
        assert "absent" not in self.reg

    def test_create_passes_args_and_kwargs(self):
        @self.reg.register("adder")
        class Adder:
            def __init__(self, x, y=0):
                self.result = x + y
        obj = self.reg.create("adder", 3, y=4)
        assert obj.result == 7

    def test_empty_registry_create_shows_none_available(self):
        empty = Registry("empty")
        with pytest.raises(ValueError, match=r"\(none\)"):
            empty.create("anything")
