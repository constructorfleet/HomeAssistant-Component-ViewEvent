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
        for route in REGISTERED_ROUTES:
            _LOGGER.warning("Firing event for %s %s" % (route[ATTR_ROUTE], route[ATTR_METHOD]))
            route_event = {
                ATTR_ROUTE: route[ATTR_ROUTE],
                ATTR_METHOD: route[ATTR_METHOD],
                ATTR_AUTH_REQUIRED: view.requires_auth
            }
            REGISTERED_ROUTES.append(route_event)
            hass.bus.async_fire(
                event_type=EVENT_TYPE_ROUTE_REGISTERED,
                event_data=route_event,
                origin=EventOrigin.local
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
                ATTR_METHOD: method
            })

    return routes


def _route_requested_handler(hass):

    def send_registered_routes():
        for route in REGISTERED_ROUTES:
            _LOGGER.warning("Firing event for %s %s" % (route[ATTR_ROUTE], route[ATTR_METHOD]))
            hass.bus.async_fire(
                event_type=EVENT_TYPE_ROUTE_REGISTERED,
                event_data=route,
                origin=EventOrigin.local
            )

    return send_registered_routes


async def async_setup(hass, config):
    """Set up the view_event component."""
    _LOGGER.warning("SETTING UP")
    fire_event = _get_fire_event(hass)
    
    HomeAssistantView.register = _wrap_function(
        HomeAssistantView.register,
        None,
        fire_event
    )

    _process_existing_views(fire_event)

    hass.bus.listen(EVENT_TYPE_REQUEST_ROUTES, _route_requested_handler(hass))

    return True
