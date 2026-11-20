"""Path-scoped license declarations in module metadata."""

from pathlib import PurePosixPath, PureWindowsPath

from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression


def parse_module_licenses(data: object, source: str) -> dict[str, str | None]:
    if not isinstance(data, dict):
        raise ValueError(
            f"{source}.licenses must be a mapping of paths to SPDX expressions or null"
        )

    licenses: dict[str, str | None] = {}
    for path, expression in data.items():
        if (
            not isinstance(path, str)
            or not path
            or PurePosixPath(path).is_absolute()
            or PureWindowsPath(path).drive
            or "\\" in path
            or ".." in PurePosixPath(path).parts
            or PurePosixPath(path).as_posix() != path
            or any(not character.isprintable() for character in path)
        ):
            raise ValueError(f"{source}.licenses has an invalid module-relative path: {path!r}")
        if expression is None:
            licenses[path] = None
            continue
        if not isinstance(expression, str):
            raise ValueError(f"{source}.licenses[{path!r}] must be an SPDX expression or null")
        try:
            licenses[path] = canonicalize_license_expression(expression)
        except InvalidLicenseExpression as exc:
            raise ValueError(f"{source}.licenses[{path!r}]: {exc}") from exc
    return licenses
