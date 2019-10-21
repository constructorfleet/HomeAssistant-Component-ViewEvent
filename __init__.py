"""
Fire an event when an API route is registered.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/remote_homeassistant/
"""
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

ATTR_METHOD = 'method'
ATTR_ROUTE = 'route'
ATTR_AUTH_REQUIRED = 'auth_required'
ATTR_INSTANCE_NAME = 'instance_name'
EVENT_TYPE_REQUEST_ROUTES = 'request_routes'
EVENT_TYPE_ROUTE_REGISTERED = 'route_registered'

CONF_COMPONENTS = 'components'
CONF_NAME = 'name'

DOMAIN = 'view_event'

SCHEMA_REQUEST_ROUTES = \
    websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        'type': EVENT_TYPE_REQUEST_ROUTES
    })

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_COMPONENTS): vol.All(cv.ensure_list,
                                               [cv.slugify])
    }),
}, extra=vol.ALLOW_EXTRA)


def _get_routes(instance_name, view, components):
    urls = [view.url] + view.extra_urls
    routes = []

    for method in ["get", "post", "delete", "put", "patch", "head", "options"]:
        _LOGGER.warn("Checking for handler for %s" % method)
        handler = getattr(view, method, None)

        if not handler:
            continue
        _LOGGER.warning("Components %s" % str(components))
        for url in urls:
            _LOGGER.warn("Checking if should register %s" % url)
            _LOGGER.warning("URL in components?? %s" % str(any(component in url for component in components)))
            if not any(component in url for component in components):
                continue
            routes.append({
                ATTR_ROUTE: url,
                ATTR_METHOD: method,
                ATTR_AUTH_REQUIRED: view.requires_auth,
                ATTR_INSTANCE_NAME: instance_name
            })

    return routes


async def async_setup(hass, config):
    """Set up the view_event component."""

    view_event = ViewEvent(hass, config)

    view_event.get_already_registered_routes()

    return True


class ViewEvent(object):
    registered_routes = []
    send_routes = False

    def __init__(self, hass, conf):
        self._hass = hass
        self._components = conf[DOMAIN][CONF_COMPONENTS]
        self._name = conf[DOMAIN][CONF_NAME]
        hass.components.websocket_api.async_register_command(
            EVENT_TYPE_REQUEST_ROUTES,
            self._routes_requested_handler,
            SCHEMA_REQUEST_ROUTES
        )
        HomeAssistantView.register = self._wrap_function(
            HomeAssistantView.register
        )
        # asyncio.ensure_future(self._get_already_registered_routes())

    @callback
    def _routes_requested_handler(self, hass, connection, msg):
        self.send_routes = True
        for route in self.registered_routes:
            self._fire_event(route)

    def _handle_view_registration(self, view):
        routes = _get_routes(self._name, view, self._components)
        for route in routes:
            self._handle_route_registration(route)

    def _handle_route_registration(self, route):
        if not self.send_routes:
            self.registered_routes.append(route)
        else:
            self._fire_event(route)

    def _fire_event(self, route):
        _LOGGER.warning("SENDING")
        self._hass.bus.async_fire(
            event_type=EVENT_TYPE_ROUTE_REGISTERED,
            event_data=route
        )

    def _wrap_function(self, function):
        """Wrap a function with pre and post hooks."""

        def _w(view, app, router):
            """Execute wrapped function."""
            _LOGGER.warning("Entering wrapper")
            _LOGGER.warning("Invoking original")
            result = function(view, app, router)
            _LOGGER.warning("GOT %s" % str(result))

            try:
                self._handle_view_registration(view)
            except Exception as e:
                _LOGGER.error('Failed to execute post-invocation hook %s' % str(e))

            return result

        return _w

    async def get_already_registered_routes(self):
        for route in self._hass.http.app.router.routes():
            self._handle_route_registration({
                ATTR_ROUTE: route.canonical,
                ATTR_METHOD: route.method,
                ATTR_AUTH_REQUIRED: False,
                ATTR_INSTANCE_NAME: self._name
            })
