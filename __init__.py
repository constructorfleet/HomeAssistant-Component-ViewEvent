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

DEFAULT_EVENT_TYPE = 'route_registered'
DEFAULT_ROUTE_ATTR = 'route'

DOMAIN = 'view_event'


def _wrap_function(function, pre, post):
    """Wrap a function with pre and post hooks."""

    def _w(self, *args, **kwargs):
        """Execute wrapped function."""
        try:
            if pre:
                pre(self, *args, **kwargs)
        except Exception as e:
            _LOGGER.error('Failed to execute pre-invocation hook %s' % str(e))

        result = function(self, *args, **kwargs)

        try:
            if post:
                post(self, *args, **kwargs)
        except Exception as e:
            _LOGGER.error('Failed to execute post-invocation hook %s' % str(e))

        return result

    return _w


def _get_fire_event(hass, event_type, route_attr):
    """Get the function that fires the event."""

    def _fire_event(view, *args, **kwargs):
        for route in _get_routes(view):
            hass.bus.async_fire(
                event_type=event_type,
                event_data={
                    route_attr: route[route_attr],
                    ATTR_METHOD: route[ATTR_METHOD],
                    ATTR_AUTH_REQUIRED: view.requires_auth
                },
                origin=EventOrigin.local
            )

    return _fire_event


def _process_existing_views(fire_event):
    for obj in gc.get_objects():
        if isinstance(obj, HomeAssistantView):
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
            routes.append({
                ATTR_URL: url,
                ATTR_METHOD: method
            })

    return routes


async def async_setup(hass, config):
    """Set up the view_event component."""
    conf = config.get(DOMAIN)

    fire_event = _get_fire_event(hass, conf[CONF_EVENT_TYPE], conf[CONF_ROUTE_ATTR])

    HomeAssistantView.register = _wrap_function(
        HomeAssistantView.register,
        None,
        fire_event
    )

    _process_existing_views(fire_event)

    return True
