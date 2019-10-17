"""
Fire an event when an API route is registered.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/remote_homeassistant/
"""
import asyncio
import gc
import logging

from homeassistant.components.http import HomeAssistantView

_LOGGER = logging.getLogger(__name__)

ATTR_METHOD = 'method'
ATTR_AUTH_REQUIRED = 'auth_required'
EVENT_TYPE_REQUEST_ROUTES = 'request_routes'
EVENT_TYPE_ROUTE_REGISTERED = 'route_registered'
ATTR_ROUTE = 'route'

DOMAIN = 'view_event'


def _wrap_function(function, pre, post):
    """Wrap a function with pre and post hooks."""

    def _w(self, *args, **kwargs):
        """Execute wrapped function."""
        _LOGGER.warning("Entering wrapper")
        try:
            if pre:
                _LOGGER.warning("Processing pre")
                pre(self, *args, **kwargs)
        except Exception as e:
            _LOGGER.error('Failed to execute pre-invocation hook %s' % str(e))

        _LOGGER.warning("Invoking original")
        result = function(self, *args, **kwargs)

        try:
            if post:
                _LOGGER.warning("Processing post")
                post(self, *args, **kwargs)
        except Exception as e:
            _LOGGER.error('Failed to execute post-invocation hook %s' % str(e))

        return result

    return _w


def _get_routes(view):
    if not view.cors_allowed:
        return []

    urls = [view.url] + view.extra_urls
    routes = []

    for method in ("get", "post", "delete", "put", "patch", "head", "options"):
        handler = getattr(view, method, None)

        if not handler:
            continue

        for url in urls:
            if "api/" not in url:
                continue
            routes.append({
                ATTR_ROUTE: url,
                ATTR_METHOD: method,
                ATTR_AUTH_REQUIRED: view.requires_auth
            })

    return routes


async def async_setup(hass, config):
    """Set up the view_event component."""

    ViewEvent(hass)

    return True


class ViewEvent(object):
    registered_routes = []
    send_routes = False

    def __init__(self, hass):
        self._hass = hass
        HomeAssistantView.register = _wrap_function(
            HomeAssistantView.register,
            None,
            self._handle_view_registration
        )
        asyncio.ensure_future(self._get_already_registered_routes())
        hass.bus.listen(EVENT_TYPE_REQUEST_ROUTES, self._routes_requested_handler)

    def _routes_requested_handler(self, message):
        self.send_routes = True
        for route in self.registered_routes:
            self._fire_event(route)

    def _handle_view_registration(self, view):
        for route in _get_routes(view):
            if not self.send_routes:
                _LOGGER.warning("ADDING TO LIST")
                self.registered_routes.append(route)
            else:
                self._fire_event(route)

    def _fire_event(self, route):
        _LOGGER.warning("SENDING")
        self._hass.bus.async_fire(
            event_type=EVENT_TYPE_ROUTE_REGISTERED,
            event_data=route
        )

    async def _get_already_registered_routes(self):
        for obj in gc.get_objects():
            _LOGGER.warning("Checking %s " % obj.__class__.__name__)
            if isinstance(obj, HomeAssistantView):
                _LOGGER.warning("Found existing view, processing")
                self._handle_view_registration(obj)
