# coding=utf-8
#
# Copyright (C) 2010 Nick Drobchenko, nick@cnc-club.ru
# Copyright (C) 2005 Aaron Spike, aaron@ekips.org
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
"""
Allow extensions to translate messages.
"""

import gettext
import os, sys

# Get gettext domain and matching locale directory for translation of extensions strings
# (both environment variables are set by Inkscape)
GETTEXT_DOMAIN = os.environ.get("INKEX_GETTEXT_DOMAIN")
GETTEXT_DIRECTORY = os.environ.get("INKEX_GETTEXT_DIRECTORY")

# INKSCAPE_LOCALEDIR can be used to override the default locale directory Inkscape uses
INKSCAPE_LOCALEDIR = os.environ.get("INKSCAPE_LOCALEDIR")


def localize(domain=GETTEXT_DOMAIN, localedir=GETTEXT_DIRECTORY):
    """Configure gettext and install _() function into builtins namespace for easy
    access"""

    # Do not enable translation if GETTEXT_DOMAIN is unset.
    # This is the case when translationdomain="none", but also when no catalog was
    # found.
    # Install a NullTranslation just to be sure
    # (so we do not get errors about undefined '_')
    if domain is None:
        gettext.NullTranslations().install()
        return

    # Use the default system locale by default,
    # but prefer LANGUAGE environment variable
    # (which is set by Inkscape according to UI language)
    languages = None

    trans = gettext.translation(domain, localedir, languages, fallback=True)
    trans.install()


def inkex_localize():
    """
    Return internal Translations instance for translation of the inkex module itself
    Those will always use the 'inkscape' domain and attempt to lookup the same catalog
    Inkscape uses
    """

    domain = "inkscape"
    localedir = INKSCAPE_LOCALEDIR
    languages = None

    return gettext.translation(domain, localedir, languages, fallback=True)


inkex_gettext = inkex_localize().gettext  # pylint: disable=invalid-name
"""
Shortcut for gettext. Import as::

    from inkex.localize import inkex_gettext as _

"""

inkex_ngettext = inkex_localize().ngettext
"""
Shortcut for ngettext

    .. versionadded:: 1.2
"""


def inkex_fgettext(message, *args, **kwargs):
    """
    Shortcut for gettext and subsequent formatting. Import as::

        from inkex.localize import inkex_fgettext as _f

    The positionals and keyword arguments are passed to ``str.format()``.

    The call to xgettext must contain::

        --keyword=_f
    """
    return inkex_gettext(message).format(*args, **kwargs)


if sys.version_info >= (3, 8):
    inkex_pgettext = inkex_localize().pgettext
    """
    Gettext with context. Import as::

        from inkex.localize import inkex_pgettext as pgettext

    Both parameters **must** be string literals. The call to xgettext must contain::

        --keyword=pgettext:1c,2

    .. versionadded:: 1.2
    """
else:
    inkex_pgettext = lambda context, message: message
