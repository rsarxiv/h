# -*- coding: utf-8 -*-

"""The main h application."""

from __future__ import unicode_literals

from h._compat import urlparse
import logging

import transaction
from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW

from h.config import configure
from h.views.client import DEFAULT_CLIENT_URL

log = logging.getLogger(__name__)


def configure_jinja2_assets(config):
    jinja2_env = config.get_jinja2_environment()
    jinja2_env.globals['asset_url'] = config.registry['assets_env'].url
    jinja2_env.globals['asset_urls'] = config.registry['assets_env'].urls


def in_debug_mode(request):
    return asbool(request.registry.settings.get('pyramid.debug_all'))


def create_app(global_config, **settings):
    """
    Create the h WSGI application.

    This function serves as a paste app factory.
    """
    config = configure(settings=settings)
    config.include(__name__)
    return config.make_wsgi_app()


def includeme(config):
    # We need to include `h.models` before pretty much everything else to
    # avoid the possibility that one of the imports below directly or
    # indirectly imports `memex.models`. See the comment at the top of
    # `h.models` for details.
    #
    # FIXME: h modules should not access `memex.models`, even indirectly,
    # except through `h.models`.
    config.include('h.models')

    config.set_root_factory('h.resources:Root')

    config.add_subscriber('h.subscribers.add_renderer_globals',
                          'pyramid.events.BeforeRender')
    config.add_subscriber('h.subscribers.publish_annotation_event',
                          'memex.events.AnnotationEvent')
    config.add_subscriber('h.subscribers.send_reply_notifications',
                          'memex.events.AnnotationEvent')

    config.add_tween('h.tweens.conditional_http_tween_factory', under=EXCVIEW)
    config.add_tween('h.tweens.redirect_tween_factory')
    config.add_tween('h.tweens.csrf_tween_factory')
    config.add_tween('h.tweens.auth_token')
    config.add_tween('h.tweens.content_security_policy_tween_factory')

    config.add_renderer('csv', 'h.renderers.CSV')
    config.add_request_method(in_debug_mode, 'debug', reify=True)

    config.include('pyramid_jinja2')
    config.add_jinja2_extension('h.jinja_extensions.Filters')
    config.add_jinja2_extension('h.jinja_extensions.SvgIcon')
    # Register a deferred action to setup the assets environment
    # when the configuration is committed.
    config.action(None, configure_jinja2_assets, args=(config,))

    # Pyramid layouts: provides support for reusable components ('panels')
    # that are used across multiple pages
    config.include('pyramid_layout')

    config.registry.settings.setdefault('mail.default_sender',
                                        '"Annotation Daemon" <no-reply@localhost>')
    config.include('pyramid_mailer')

    # Pyramid service layer: provides infrastructure for registering and
    # retrieving services bound to the request.
    config.include('pyramid_services')

    # Configure the transaction manager to support retrying retryable
    # exceptions, and generate a new transaction manager for each request.
    config.add_settings({
        "tm.attempts": 3,
        "tm.manager_hook": lambda request: transaction.TransactionManager(),
        "tm.annotate_user": False,
    })
    config.include('pyramid_tm')

    # Enable a Content Security Policy
    # This is initially copied from:
    # https://github.com/pypa/warehouse/blob/e1cf03faf9bbaa15d67d0de2c70f9a9f732596aa/warehouse/config.py#L327
    client_url = config.registry.settings.get('h.client_url', DEFAULT_CLIENT_URL)
    client_host = urlparse.urlparse(client_url).netloc

    config.add_settings({
        "csp": {
            "font-src": ["'self'", "fonts.gstatic.com", client_host],
            "report-uri": [config.registry.settings.get("csp.report_uri")],
            "script-src": ["'self'", client_host, "www.google-analytics.com"],
            "style-src": ["'self'", "fonts.googleapis.com", client_host],
        },
    })

    # API module
    #
    # We include this first so that:
    # - configuration directives provided by modules in `memex` are available
    #   to the rest of the application at startup.
    # - we can override behaviour from `memex` if necessary.
    config.include('memex', route_prefix='/api')

    # Override memex group service
    config.register_service_factory('h.services.groupfinder.groupfinder_service_factory',
                                    iface='memex.interfaces.IGroupService')

    # Core site modules
    config.include('h.assets')
    config.include('h.auth')
    config.include('h.authz')
    config.include('h.db')
    config.include('h.features')
    config.include('h.form')
    config.include('h.indexer')
    config.include('h.panels')
    config.include('h.realtime')
    config.include('h.routes')
    config.include('h.sentry')
    config.include('h.services')
    config.include('h.session')
    config.include('h.stats')
    config.include('h.views')

    # Site modules
    config.include('h.accounts')
    config.include('h.admin')
    config.include('h.groups')
    config.include('h.links')
    config.include('h.nipsa')
    config.include('h.notification')

    # Debugging assistance
    if asbool(config.registry.settings.get('h.debug')):
        config.include('pyramid_debugtoolbar')
        config.include('h.debug')
