"""
Fire an event when an API route is registered.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/remote_homeassistant/
"""
import logging
import jwt

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import DATA_SIGN_SECRET
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

ATTR_METHOD = 'method'
ATTR_ROUTE = 'route'
ATTR_AUTH_REQUIRED = 'auth_required'
ATTR_INSTANCE_NAME = 'instance_name'
ATTR_INSTANCE_IP = 'instance_ip'
ATTR_INSTANCE_PORT = 'instance_port'
ATTR_SIGNATURE = 'signature'
EVENT_TYPE_REQUEST_ROUTES = 'request_routes'
EVENT_TYPE_ROUTE_REGISTERED = 'route_registered'

CONF_COMPONENTS = 'components'

DOMAIN = 'view_event'

SCHEMA_REQUEST_ROUTES = \
    websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
        'type': EVENT_TYPE_REQUEST_ROUTES
    })

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_COMPONENTS): vol.All(cv.ensure_list,
                                               [cv.slugify])
    }),
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Set up the view_event component."""

    view_event = ViewEvent(hass, config)

    await view_event.get_already_registered_routes()

    return True


class ViewEvent:
    """Send route registered event to websocket."""
    registered_routes = []

    def __init__(self, hass, conf):
        self._hass = hass
        self._signature = self._hass.data[DATA_SIGN_SECRET]
        self._components = conf[DOMAIN][CONF_COMPONENTS]
        self._name = hass.config.location_name
        self._host = hass.http.server_host
        self._port = hass.http.server_port
        hass.bus.async_listen(
            EVENT_TYPE_REQUEST_ROUTES,
            self.routes_requested_bus_handler
        )
        hass.components.websocket_api.async_register_command(
            EVENT_TYPE_REQUEST_ROUTES,
            self.routes_requested_ws_handler,
            SCHEMA_REQUEST_ROUTES
        )
        HomeAssistantView.register = self._wrap_function(
            HomeAssistantView.register
        )

    def _get_routes(self, view):
        urls = [view.url] + view.extra_urls
        routes = []

        for method in ["get", "post", "delete", "put", "patch", "head", "options"]:
            _LOGGER.debug("Checking for handler for %s", method)
            handler = getattr(view, method, None)

            if not handler:
                continue
            for url in urls:
                routes.append({
                    ATTR_ROUTE: url,
                    ATTR_METHOD: method,
                    ATTR_AUTH_REQUIRED: False,
                    ATTR_INSTANCE_NAME: self._name,
                    ATTR_INSTANCE_IP: self._host,
                    ATTR_INSTANCE_PORT: self._port,
                    ATTR_SIGNATURE: self._signature
                })

        return routes

    def _handle_view_registration(self, view):
        routes = self._get_routes(view)
        for route in routes:
            self._handle_route_registration(route)

    def _handle_route_registration(self, route):
        url = route[ATTR_ROUTE]
        _LOGGER.debug("Checking if should register %s", url)
        _LOGGER.debug(
            "URL in components?? %s",
            str(any(component in url for component in self._components))
        )
        if not str(url).startswith('/api/services') and \
                not any(component in url for component in self._components):
            return
        self.registered_routes.append(route)
        self._fire_event(route)

    def _fire_event(self, route):
        self._hass.bus.async_fire(
            event_type=EVENT_TYPE_ROUTE_REGISTERED,
            event_data=route
        )

    def _wrap_function(self, function):
        """Wrap a function with pre and post hooks."""

        def _w(view, app, router):
            """Execute wrapped function."""
            result = function(view, app, router)

            try:
                self._handle_view_registration(view)
            except Exception as err:
                _LOGGER.error(
                    'Failed to execute post-invocation hook %s',
                    str(err)
                )

            return result

        return _w

    async def get_already_registered_routes(self):
        """Retrieve registered routes and send to websocket."""
        for route in self._hass.http.app.router.routes():
            self._handle_route_registration({
                ATTR_ROUTE: route.resource.canonical,
                ATTR_METHOD: route.method,
                ATTR_AUTH_REQUIRED: False,
                ATTR_INSTANCE_NAME: self._name,
                ATTR_INSTANCE_IP: self._host,
                ATTR_INSTANCE_PORT: self._port,
                ATTR_SIGNATURE: self._signature
            })

    @callback
    def routes_requested_ws_handler(self, hass, connection, msg):
        """Handle websocket command requesting existing routes."""
        self._send_routes()

    @callback
    def routes_requested_bus_handler(self, event):
        """Handle event bus event for requesting existing routes."""
        self._send_routes()

    def _send_routes(self):
        for route in self.registered_routes:
            self._fire_event(route)
