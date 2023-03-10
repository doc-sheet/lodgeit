#!/usr/bin/env python
"""
    LodgeIt!
    ~~~~~~~~

    A script that pastes stuff into the lodgeit pastebin.

    .lodgeitrc / _lodgeitrc
    -----------------------

    Under UNIX create a file called ``~/.lodgeitrc``, under Windows
    create a file ``%APPDATA%/_lodgeitrc`` to override defaults::

        language=default_language
        clipboard=true/false
        open_browser=true/false
        encoding=fallback_charset

    :authors: 2007-2010 Georg Brandl <georg@python.org>,
              2006 Armin Ronacher <armin.ronacher@active-4.com>,
              2006 Matt Good <matt@matt-good.net>,
              2005 Raphael Slinckx <raphael@slinckx.net>
"""
from __future__ import print_function
import os
import sys
from six import text_type
from optparse import OptionParser


SCRIPT_NAME = os.path.basename(sys.argv[0])
VERSION = '0.3'
SETTING_KEYS = ['author', 'title', 'language', 'private', 'clipboard',
                'open_browser']

# global server proxy
_xmlrpc_service = None
_server_name = None


def fail(msg, code):
    """Bail out with an error message."""
    print('ERROR: %s' % msg, file=sys.stderr)
    sys.exit(code)


def load_default_settings():
    """Load the defaults from the lodgeitrc file."""
    settings = {
        'language':     None,
        'clipboard':    True,
        'open_browser': False,
        'encoding':     'iso-8859-15',
        'server_name':  'http://paste.openstack.org',
    }
    rcfile = None
    if os.name == 'posix':
        rcfile = os.path.expanduser('~/.lodgeitrc')
    elif os.name == 'nt' and 'APPDATA' in os.environ:
        rcfile = os.path.expandvars(r'$APPDATA\_lodgeitrc')
    if rcfile:
        try:
            f = open(rcfile)
            for line in f:
                if line.strip()[:1] in '#;':
                    continue
                p = line.split('=', 1)
                if len(p) == 2:
                    key = p[0].strip().lower()
                    if key in settings:
                        if key in ('clipboard', 'open_browser'):
                            settings[key] = p[1].strip().lower() in \
                                ('true', '1', 'on', 'yes')
                        else:
                            settings[key] = p[1].strip()
            f.close()
        except IOError:
            pass
    settings['tags'] = []
    settings['title'] = None
    return settings


def make_utf8(text, encoding):
    """Convert a text to UTF-8, brute-force."""
    try:
        u = text_type(text, 'utf-8')
        uenc = 'utf-8'
    except UnicodeError:
        try:
            u = text_type(text, encoding)
            uenc = 'utf-8'
        except UnicodeError:
            u = text_type(text, 'iso-8859-15', 'ignore')
            uenc = 'iso-8859-15'
    try:
        import chardet
    except ImportError:
        return u.encode('utf-8')
    d = chardet.detect(text)
    if d['encoding'] == uenc:
        return u.encode('utf-8')
    return text_type(text, d['encoding'], 'ignore').encode('utf-8')


def get_xmlrpc_service():
    """Create the XMLRPC server proxy and cache it."""
    global _xmlrpc_service
    import xmlrpclib
    if _xmlrpc_service is None:
        try:
            _xmlrpc_service = xmlrpclib.ServerProxy(_server_name + 'xmlrpc/',
                                                    allow_none=True)
        except Exception as err:
            fail('Could not connect to Pastebin: %s' % err, -1)
    return _xmlrpc_service


def copy_url(url):
    """Copy the url into the clipboard."""
    # try windows first
    try:
        import win32clipboard
    except ImportError:
        # then give pbcopy a try.  do that before gtk because
        # gtk might be installed on os x but nobody is interested
        # in the X11 clipboard there.
        from subprocess import Popen, PIPE
        for prog in 'pbcopy', 'xclip':
            try:
                client = Popen([prog], stdin=PIPE)
            except OSError:
                continue
            else:
                client.stdin.write(url)
                client.stdin.close()
                client.wait()
                break
        else:
            try:
                import pygtk
                pygtk.require('2.0')
                import gtk
                import gobject
            except ImportError:
                return
            gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD).set_text(url)
            gobject.idle_add(gtk.main_quit)
            gtk.main()
    else:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(url)
        win32clipboard.CloseClipboard()


def open_webbrowser(url):
    """Open a new browser window."""
    import webbrowser
    webbrowser.open(url)


def language_exists(language):
    """Check if a language alias exists."""
    xmlrpc = get_xmlrpc_service()
    langs = xmlrpc.pastes.getLanguages()
    return language in langs


def get_mimetype(data, filename):
    """Try to get MIME type from data."""
    try:
        import gnomevfs
    except ImportError:
        from mimetypes import guess_type
        if filename:
            return guess_type(filename)[0]
    else:
        if filename:
            return gnomevfs.get_mime_type(os.path.abspath(filename))
        return gnomevfs.get_mime_type_for_data(data)


def print_languages():
    """Print a list of all supported languages, with description."""
    xmlrpc = get_xmlrpc_service()
    languages = xmlrpc.pastes.getLanguages().items()
    languages.sort(key=lambda a: a[1].lower())
    print('Supported Languages:')
    for alias, name in languages:
        print('    %-30s%s' % (alias, name))


def download_paste(uid):
    """Download a paste given by ID."""
    xmlrpc = get_xmlrpc_service()
    paste = xmlrpc.pastes.getPaste(uid)
    if not paste:
        fail('Paste "%s" does not exist.' % uid, 5)
    print(paste['code'].encode('utf-8'))


def create_paste(code, language, filename, mimetype, private):
    """Create a new paste."""
    xmlrpc = get_xmlrpc_service()
    rv = xmlrpc.pastes.newPaste(language, code, None, filename, mimetype,
                                private)
    if not rv:
        fail('Could not create paste. Something went wrong '
             'on the server side.', 4)
    return rv


def compile_paste(filenames, langopt):
    """Create a single paste out of zero, one or multiple files."""
    def read_file(f):
        try:
            return f.read()
        finally:
            f.close()
    mime = ''
    lang = langopt or ''
    if not filenames:
        data = read_file(sys.stdin)
        print('Pasting...')
        if not langopt:
            mime = get_mimetype(data, '') or ''
        fname = ''
    elif len(filenames) == 1:
        fname = filenames[0]
        data = read_file(open(filenames[0], 'rb'))
        if not langopt:
            mime = get_mimetype(data, filenames[0]) or ''
    else:
        result = []
        for fname in filenames:
            data = read_file(open(fname, 'rb'))
            if langopt:
                result.append('### %s [%s]\n\n' % (fname, langopt))
            else:
                result.append('### %s\n\n' % fname)
            result.append(data)
            result.append('\n\n')
        data = ''.join(result)
        lang = 'multi'
        fname = ''
    return data, lang, fname, mime


def main():
    """Main script entry point."""
    global _server_name

    usage = ('Usage: %%prog [options] [FILE ...]\n\n'
             'Read the files and paste their contents to LodgeIt pastebin.\n'
             'If no file is given, read from standard input.\n'
             'If multiple files are given, they are put into a single paste.')
    parser = OptionParser(usage=usage)

    settings = load_default_settings()

    parser.add_option('-v', '--version', action='store_true',
                      help='Print script version')
    parser.add_option('-L', '--languages', action='store_true', default=False,
                      help='Retrieve a list of supported languages')
    parser.add_option('-l', '--language', default=settings['language'],
                      help='Used syntax highlighter for the file')
    parser.add_option('-e', '--encoding', default=settings['encoding'],
                      help='Specify the encoding of a file (default is '
                           'utf-8 or guessing if available)')
    parser.add_option('-b', '--open-browser', dest='open_browser',
                      action='store_true',
                      default=settings['open_browser'],
                      help='Open the paste in a web browser')
    parser.add_option('-p', '--private', action='store_true', default=False,
                      help='Paste as private')
    parser.add_option('--no-clipboard', dest='clipboard',
                      action='store_false',
                      default=settings['clipboard'],
                      help="Don't copy the url into the clipboard")
    parser.add_option('--download', metavar='UID',
                      help='Download a given paste')
    parser.add_option('-s', '--server', default=settings['server_name'],
                      dest='server_name',
                      help="Specify the pastebin to send data")
    opts, args = parser.parse_args()

    # The global available server name
    _server_name = opts.server_name
    if not _server_name.endswith('/'):
        _server_name += '/'

    # special modes of operation:
    # - paste script version
    if opts.version:
        print('%s: version %s' % (SCRIPT_NAME, VERSION))
        sys.exit()
    # - print list of languages
    elif opts.languages:
        print_languages()
        sys.exit()
    # - download Paste
    elif opts.download:
        download_paste(opts.download)
        sys.exit()

    # check language if given
    if opts.language and not language_exists(opts.language):
        fail('Language %s is not supported.' % opts.language, 3)

    # load file(s)
    try:
        data, language, filename, mimetype = compile_paste(args, opts.language)
    except Exception as err:
        fail('Error while reading the file(s): %s' % err, 2)
    if not data:
        fail('Aborted, no content to paste.', 4)

    # create paste
    code = make_utf8(data, opts.encoding)
    pid = create_paste(code, language, filename, mimetype, opts.private)
    url = '%sshow/%s/' % (_server_name, pid)
    print(url)
    if opts.open_browser:
        open_webbrowser(url)
    if opts.clipboard:
        copy_url(url)


if __name__ == '__main__':
    sys.exit(main())
