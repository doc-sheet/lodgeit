"""
    lodgeit.utils
    ~~~~~~~~~~~~~

    Serveral utilities used by LodgeIt.

    :copyright: 2007-2008 by Christopher Grebs.
    :license: BSD
"""
import base64
import os
import re
import time
from os import path
from random import random
from functools import partial

from werkzeug import Request as RequestBase, Response
from werkzeug.contrib.securecookie import SecureCookie

from jinja2 import Environment, FileSystemLoader

from babel import Locale

from lodgeit import local
from lodgeit.i18n import get_translations

try:
    from hashlib import sha1
except ImportError:
    from sha import new as sha1

#: Jinja2 Environment for our template handling
jinja_environment = Environment(loader=FileSystemLoader(
    path.join(path.dirname(__file__), 'views')),
    extensions=['jinja2.ext.i18n'])

#: constants
_word_only = partial(re.compile(r'[^a-zA-Z0-9]').sub, '')
COOKIE_NAME = u'lodgeit_session'


def url_for(endpoint, external=False, **values):
    builder = local.ctx.url_adapter.build
    return builder(endpoint, values, force_external=external)


jinja_environment.globals['url_for'] = url_for
jinja_environment.globals['title'] = \
    os.getenv('LODGEIT_TITLE_OVERRIDE', 'Lodge It')


def generate_user_hash():
    """Generates an more or less unique SHA1 hash."""
    hash_base = '%s|%s' % (random(), time.time())
    return sha1(hash_base.encode()).hexdigest()


def generate_paste_hash():
    """Generates a more or less unique-truncated SHA1 hash."""
    while 1:
        hash_base = '%s|%s' % (random(), time.time())
        digest = sha1(hash_base.encode()).digest()
        val = _word_only(str(base64.b64encode(digest)).strip())[:20]
        # sanity check.  number only not allowed (though unlikely)
        if not val.isdigit():
            return val


class Request(RequestBase):
    """Subclass of the `Request` object. automatically creates a new
    `user_hash` and sets `first_visit` to `True` if it's a new user.
    It also stores the engine and dbsession on it.
    """
    charset = 'utf-8'

    def __init__(self, environ):
        super(Request, self).__init__(environ)
        self.first_visit = False
        session = SecureCookie.load_cookie(self, COOKIE_NAME,
                                           local.application.secret_key)
        user_hash = session.get('user_hash')

        if not user_hash:
            session['user_hash'] = generate_user_hash()
            self.first_visit = True
        self.user_hash = session['user_hash']
        self.session = session

        # language is limited to english until translations are ready
        lang = session.get('locale')
        if lang is None:
            lang = 'en'
        self.locale = Locale.parse(lang)

    def set_language(self, lang):
        self.session['locale'] = lang

    @property
    def translations(self):
        return get_translations(self.locale)

    def bind_to_context(self):
        local.request = self


def render_template(template_name, **context):
    request = local.request
    context.update(
        request=request,
        gettext=request.translations.ugettext,
        ngettext=request.translations.ungettext
    )
    return jinja_environment.get_template(template_name).render(context)


def render_to_response(template_name, mimetype='text/html', **context):
    """Render a template to a response. This automatically fetches
    the list of new replies for the layout template. It also
    adds the current request to the context. This is used for the
    welcome message.
    """
    return Response(render_template(template_name, **context),
                    mimetype=mimetype)
