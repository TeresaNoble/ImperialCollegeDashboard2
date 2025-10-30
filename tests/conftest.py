from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, Tuple


class _StubRequest:
    """Minimal stand-in for :mod:`flask`'s ``request`` proxy used in tests."""

    def __init__(self) -> None:
        self._json_payload: Dict[str, Any] | None = None

    def set_json(self, payload: Dict[str, Any] | None) -> None:
        self._json_payload = payload

    def get_json(self, force: bool = False) -> Dict[str, Any] | None:  # noqa: D401
        return self._json_payload


class _StubFlask:
    def __init__(self, import_name: str) -> None:  # noqa: D401
        self.import_name = import_name
        self.config: Dict[str, Any] = {}
        self._routes: Dict[Tuple[str, Tuple[str, ...]], Callable[..., Any]] = {}

    def route(self, rule: str, methods: Tuple[str, ...] | None = None):  # noqa: D401
        methods = methods or ("GET",)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._routes[(rule, tuple(methods))] = func
            return func

        return decorator


_stub_module = types.ModuleType("flask")
_stub_request = _StubRequest()
_stub_module.Flask = _StubFlask
_stub_module.jsonify = lambda payload: payload
_stub_module.request = _stub_request
_stub_module.send_from_directory = lambda directory, filename: (directory, filename)
_stub_module.__dict__["request_context"] = None

sys.modules.setdefault("flask", _stub_module)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
