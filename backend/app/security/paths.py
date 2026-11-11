"""Which requests are API requests. Every security layer asks here, so they cannot disagree."""

from starlette.types import Scope

API_PREFIX = "/api"


def route_path(scope: Scope) -> str:
    """The path the router matches on (the request path minus the ASGI root_path), so a
    layer here and the router never disagree about which route a request is for."""
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if not root_path or not path.startswith(root_path):
        return path
    if path == root_path:
        return ""
    return path[len(root_path) :] if path[len(root_path)] == "/" else path


def is_api(path: str) -> bool:
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")
