"""
Fire an event when an API route is registered.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/remote_homeassistant/
"""
import gc
import logging

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import EventOrigin

_LOGGER = logging.getLogger(__name__)

ATTR_METHOD = 'method'
ATTR_AUTH_REQUIRED = 'auth_required'
EVENT_TYPE_REQUEST_ROUTES = 'request_routes'
EVENT_TYPE_ROUTE_REGISTERED = 'route_registered'
ATTR_ROUTE = 'route'

DOMAIN = 'view_event'

SEND_ROUTES = False
REGISTERED_ROUTES = []


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


def _get_fire_event(hass):
    """Get the function that fires the event."""
    _LOGGER.warning("Retrieving fire event method")

    def _fire_event(view, *args, **kwargs):
        _LOGGER.warning("Trying to fire event")
        for route in _get_routes(view):
            if not SEND_ROUTES:
                REGISTERED_ROUTES.append(route)
            else:
                hass.bus.async_fire(
                    event_type=EVENT_TYPE_ROUTE_REGISTERED,
                    event_data=route
                )

    return _fire_event


def _process_existing_views(fire_event):
    for obj in gc.get_objects():
        if isinstance(obj, HomeAssistantView):
            _LOGGER.warning("Found existing view, processing")
            fire_event(obj)


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


def _get_routes_requested_handler(fire_event):
    def _routes_requested_handler(message):
        global SEND_ROUTES
        SEND_ROUTES = True
        for route in REGISTERED_ROUTES:
            fire_event(
                event_type=EVENT_TYPE_ROUTE_REGISTERED,
                event_data=route
            )

    return _routes_requested_handler


async def async_setup(hass, config):
    """Set up the view_event component."""
    _LOGGER.warning("SETTING UP")
    fire_event = _get_fire_event(hass)
    hass.bus.listen(EVENT_TYPE_REQUEST_ROUTES, _get_routes_requested_handler(fire_event))

    HomeAssistantView.register = _wrap_function(
        HomeAssistantView.register,
        None,
        fire_event
    )

    _process_existing_views(fire_event)

    return True
