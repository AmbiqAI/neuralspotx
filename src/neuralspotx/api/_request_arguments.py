"""Validate the two calling styles before the facade dispatches an operation."""

from __future__ import annotations

import inspect
import warnings
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from functools import wraps
from typing import ParamSpec, TypeVar

from .._errors import NSXConfigError

_P = ParamSpec("_P")
_R = TypeVar("_R")


def request_arguments(
    request_type: type, *, specializations: tuple[type, ...] = (), legacy_precedence: bool = False
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Check explicit arguments while preserving each facade's typed signature."""

    def decorate(operation: Callable[_P, _R]) -> Callable[_P, _R]:
        assert inspect.isfunction(operation) and is_dataclass(request_type)
        signature = inspect.signature(operation)
        first = next(iter(signature.parameters))
        # Use only the public request types, so subclasses can carry caller metadata.
        unused_by_type = {}
        for kind in (*specializations, request_type):
            assert is_dataclass(kind)
            unused_by_type[kind] = {
                f.name: f.default for f in fields(kind) if f.name not in signature.parameters
            }
        request_fields = {f.name for f in fields(request_type) if f.name != first}

        @wraps(operation)
        def checked(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            request = args[0] if args else kwargs.get(first)
            if isinstance(request, request_type):
                # bind() retains explicit None/False/defaults and positional module names.
                supplied = signature.bind(*args, **kwargs).arguments
                conflicts = [
                    name
                    for name in supplied
                    if name in request_fields and supplied[name] != getattr(request, name)
                ]
                if conflicts:
                    message = (
                        f"{operation.__name__}(): {', '.join(conflicts)} conflicts with "
                        f"{request_type.__name__}. Set the option on the request or use "
                        "dataclasses.replace() to make a modified copy."
                    )
                    if legacy_precedence:
                        warnings.warn(
                            message + " Using the request value in 1.x.",
                            DeprecationWarning,
                            stacklevel=2,
                        )
                    else:
                        raise NSXConfigError(message)
                unused = next(
                    defaults
                    for kind, defaults in unused_by_type.items()
                    if isinstance(request, kind)
                )
                for name, default in unused.items():
                    if getattr(request, name) != default:
                        message = f"{operation.__name__}() does not use the request field {name!r}."
                        if name == "frozen":
                            raise NSXConfigError(message)
                        warnings.warn(message, DeprecationWarning, stacklevel=2)
            return operation(*args, **kwargs)

        return checked

    return decorate
