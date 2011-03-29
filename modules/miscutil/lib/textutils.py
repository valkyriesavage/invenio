# -*- coding: utf-8 -*-

## This file is part of Invenio.
## Copyright (C) 2005, 2006, 2007, 2008, 2009, 2010, 2011 CERN.
##
## Invenio is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 2 of the
## License, or (at your option) any later version.
##
## Invenio is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Invenio; if not, write to the Free Software Foundation, Inc.,
## 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""
Functions useful for text wrapping (in a box) and indenting.
"""

__revision__ = "$Id$"

import re
import sys
import textwrap

import invenio.template

CFG_WRAP_TEXT_IN_A_BOX_STYLES = {
    '__DEFAULT' : {
        'horiz_sep' : '*',
        'max_col' : 72,
        'min_col' : 40,
        'tab_str' : '    ',
        'tab_num' : 0,
        'border' : ('**', '*', '**', '** ', ' **', '**', '*', '**'),
        'prefix' : '\n',
        'suffix' : '\n',
        'break_long' : False,
        'force_horiz' : False,
    },
    'squared' : {
        'horiz_sep' : '-',
        'border' : ('+', '-', '+', '| ', ' |', '+', '-', '+')
    },
    'double_sharp' : {
        'horiz_sep' : '#',
        'border' : ('##', '#', '##', '## ', ' ##', '##', '#', '##')
    },
    'single_sharp' : {
        'horiz_sep' : '#',
        'border' : ('#', '#', '#', '# ', ' #', '#', '#', '#')
    },
    'single_star' : {
        'border' : ('*', '*', '*', '* ', ' *', '*', '*', '*',)
    },
    'double_star' : {
    },
    'no_border' : {
        'horiz_sep' : '',
        'border' : ('', '', '', '', '', '', '', ''),
        'prefix' : '',
        'suffix' : ''
    },
    'conclusion' : {
        'border' : ('', '', '', '', '', '', '', ''),
        'prefix' : '',
        'horiz_sep' : '-',
        'force_horiz' : True,
    },
    'important' : {
        'tab_num' : 1,
    },
}

def indent_text(text,
                nb_tabs=0,
                tab_str="  ",
                linebreak_input="\n",
                linebreak_output="\n",
                wrap=False):
    """
    add tabs to each line of text
    @param text: the text to indent
    @param nb_tabs: number of tabs to add
    @param tab_str: type of tab (could be, for example "\t", default: 2 spaces
    @param linebreak_input: linebreak on input
    @param linebreak_output: linebreak on output
    @param wrap: wethever to apply smart text wrapping.
        (by means of wrap_text_in_a_box)
    @return: indented text as string
    """
    if not wrap:
        lines = text.split(linebreak_input)
        tabs = nb_tabs*tab_str
        output = ""
        for line in lines:
            output += tabs + line + linebreak_output
        return output
    else:
        return wrap_text_in_a_box(body=text, style='no_border',
            tab_str=tab_str, tab_num=nb_tabs)

_RE_BEGINNING_SPACES = re.compile(r'^\s*')
_RE_NEWLINES_CLEANER = re.compile(r'\n+')
_RE_LONELY_NEWLINES = re.compile(r'\b\n\b')
def wrap_text_in_a_box(body='', title='', style='double_star', **args):
    """Return a nicely formatted text box:
        e.g.
       ******************
       **  title       **
       **--------------**
       **  body        **
       ******************

    Indentation and newline are respected.
    @param body: the main text
    @param title: an optional title
    @param style: the name of one of the style in CFG_WRAP_STYLES. By default
        the double_star style is used.

    You can further tune the desired style by setting various optional
    parameters:
        @param horiz_sep: a string that is repeated in order to produce a
            separator row between the title and the body (if needed)
        @param max_col: the maximum number of coulmns used by the box
            (including indentation)
        @param min_col: the symmetrical minimum number of columns
        @param tab_str: a string to represent indentation
        @param tab_num: the number of leveles of indentations
        @param border: a tuple of 8 element in the form
            (tl, t, tr, l, r, bl, b, br) of strings that represent the
            different corners and sides of the box
        @param prefix: a prefix string added before the box
        @param suffix: a suffix string added after the box
        @param break_long: wethever to break long words in order to respect
            max_col
        @param force_horiz: True in order to print the horizontal line even when
            there is no title

    e.g.:
    print wrap_text_in_a_box(title='prova',
        body='  123 prova.\n    Vediamo come si indenta',
        horiz_sep='-', style='no_border', max_col=20, tab_num=1)

        prova
        ----------------
        123 prova.
            Vediamo come
            si indenta

    """

    def _wrap_row(row, max_col, break_long):
        """Wrap a single row"""
        spaces = _RE_BEGINNING_SPACES.match(row).group()
        row = row[len(spaces):]
        spaces = spaces.expandtabs()
        return textwrap.wrap(row, initial_indent=spaces,
            subsequent_indent=spaces, width=max_col,
            break_long_words=break_long)

    def _clean_newlines(text):
        text = _RE_LONELY_NEWLINES.sub(' \n', text)
        return _RE_NEWLINES_CLEANER.sub(lambda x: x.group()[:-1], text)

    body = unicode(body, 'utf-8')
    title = unicode(title, 'utf-8')

    astyle = dict(CFG_WRAP_TEXT_IN_A_BOX_STYLES['__DEFAULT'])
    if CFG_WRAP_TEXT_IN_A_BOX_STYLES.has_key(style):
        astyle.update(CFG_WRAP_TEXT_IN_A_BOX_STYLES[style])
    astyle.update(args)

    horiz_sep = astyle['horiz_sep']
    border = astyle['border']
    tab_str = astyle['tab_str'] * astyle['tab_num']
    max_col = max(astyle['max_col'] \
        - len(border[3]) - len(border[4]) - len(tab_str), 1)
    min_col = astyle['min_col']
    prefix = astyle['prefix']
    suffix = astyle['suffix']
    force_horiz = astyle['force_horiz']
    break_long = astyle['break_long']

    body = _clean_newlines(body)
    tmp_rows = [_wrap_row(row, max_col, break_long)
                        for row in body.split('\n')]
    body_rows = []
    for rows in tmp_rows:
        if rows:
            body_rows += rows
        else:
            body_rows.append('')
    if not ''.join(body_rows).strip():
        # Concrete empty body
        body_rows = []

    title = _clean_newlines(title)
    tmp_rows = [_wrap_row(row, max_col, break_long)
                        for row in title.split('\n')]
    title_rows = []
    for rows in tmp_rows:
        if rows:
            title_rows += rows
        else:
            title_rows.append('')
    if not ''.join(title_rows).strip():
        # Concrete empty title
        title_rows = []

    max_col = max([len(row) for row in body_rows + title_rows] + [min_col])

    mid_top_border_len = max_col \
        + len(border[3]) + len(border[4]) - len(border[0]) - len(border[2])
    mid_bottom_border_len = max_col \
        + len(border[3]) + len(border[4]) - len(border[5]) - len(border[7])
    top_border = border[0] \
        + (border[1] * mid_top_border_len)[:mid_top_border_len] + border[2]
    bottom_border = border[5] \
        + (border[6] * mid_bottom_border_len)[:mid_bottom_border_len] \
        + border[7]
    horiz_line = border[3] + (horiz_sep * max_col)[:max_col] + border[4]

    title_rows = [tab_str + border[3] + row
        + ' ' * (max_col - len(row)) + border[4] for row in title_rows]
    body_rows = [tab_str + border[3] + row
        + ' ' * (max_col - len(row)) + border[4] for row in body_rows]

    ret = []
    if top_border:
        ret += [tab_str + top_border]
    ret += title_rows
    if title_rows or force_horiz:
        ret += [tab_str + horiz_line]
    ret += body_rows
    if bottom_border:
        ret += [tab_str + bottom_border]
    return (prefix + '\n'.join(ret) + suffix).encode('utf-8')

def wait_for_user(msg=""):
    """
    Print MSG and a confirmation prompt, waiting for user's
    confirmation, unless silent '--yes-i-know' command line option was
    used, in which case the function returns immediately without
    printing anything.
    """
    if '--yes-i-know' in sys.argv:
        return
    print msg
    try:
        answer = raw_input("Please confirm by typing 'Yes, I know!': ")
    except KeyboardInterrupt:
        print
        answer = ''
    if answer != 'Yes, I know!':
        sys.stderr.write("ERROR: Aborted.\n")
        sys.exit(1)
    return

def guess_minimum_encoding(text, charsets=('ascii', 'latin1', 'utf8')):
    """Try to guess the minimum charset that is able to represent the given
    text using the provided charsets. text is supposed to be encoded in utf8.
    Returns (encoded_text, charset) where charset is the first charset
    in the sequence being able to encode text.
    Returns (text_in_utf8, 'utf8') in case no charset is able to encode text.

    @note: If the input text is not in strict UTF-8, then replace any
        non-UTF-8 chars inside it.
    """
    text_in_unicode = text.decode('utf8', 'replace')
    for charset in charsets:
        try:
            return (text_in_unicode.encode(charset), charset)
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return (text_in_unicode.encode('utf8'), 'utf8')

def encode_for_xml(text, wash=False, xml_version='1.0'):
    """Encodes special characters in a text so that it would be
    XML-compliant.
    @param text: text to encode
    @return: an encoded text"""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    if wash:
        text = wash_for_xml(text, xml_version='1.0')
    return text

try:
    unichr(0x100000)
    RE_ALLOWED_XML_1_0_CHARS = re.compile(u'[^\U00000009\U0000000A\U0000000D\U00000020-\U0000D7FF\U0000E000-\U0000FFFD\U00010000-\U0010FFFF]')
    RE_ALLOWED_XML_1_1_CHARS = re.compile(u'[^\U00000001-\U0000D7FF\U0000E000-\U0000FFFD\U00010000-\U0010FFFF]')
except ValueError:
    # oops, we are running on a narrow UTF/UCS Python build,
    # so we have to limit the UTF/UCS char range:
    RE_ALLOWED_XML_1_0_CHARS = re.compile(u'[^\U00000009\U0000000A\U0000000D\U00000020-\U0000D7FF\U0000E000-\U0000FFFD]')
    RE_ALLOWED_XML_1_1_CHARS = re.compile(u'[^\U00000001-\U0000D7FF\U0000E000-\U0000FFFD]')

def wash_for_xml(text, xml_version='1.0'):
    """
    Removes any character which is not in the range of allowed
    characters for XML. The allowed characters depends on the version
    of XML.

        - XML 1.0:
            <http://www.w3.org/TR/REC-xml/#charsets>
        - XML 1.1:
            <http://www.w3.org/TR/xml11/#charsets>

    @param text: input string to wash.
    @param xml_version: version of the XML for which we wash the
        input. Value for this parameter can be '1.0' or '1.1'
    """
    if xml_version == '1.0':
        return RE_ALLOWED_XML_1_0_CHARS.sub('', unicode(text, 'utf-8')).encode('utf-8')
    else:
        return RE_ALLOWED_XML_1_1_CHARS.sub('', unicode(text, 'utf-8')).encode('utf-8')

def wash_for_utf8(text, correct=True):
    """
    Removes all characters incorrect from the unicode point of view
    @param text: input string to wash
    """
    cont = True
    while cont:
        try:
            text.decode("utf-8")
        except UnicodeDecodeError, e:
            if correct:
                text = text[:e.start] + text[e.end:]
            else:
                raise e
        except Exception, e:
            raise e
        else:
            cont = False
    return text

def nice_size(size):
    """
    @param size: the size.
    @type size: int
    @return: a nicely printed size.
    @rtype: string
    """
    websearch_templates = invenio.template.load('websearch')
    unit = 'B'
    if size > 1024:
        size /= 1024.0
        unit = 'KB'
        if size > 1024:
            size /= 1024.0
            unit = 'MB'
            if size > 1024:
                size /= 1024.0
                unit = 'GB'
    return '%s %s' % (websearch_templates.tmpl_nice_number(size, max_ndigits_after_dot=2), unit)

def remove_line_breaks(text):
    """
    Remove line breaks from input, including unicode 'line
    separator', 'paragraph separator', and 'next line' characters.
    """
    return unicode(text, 'utf-8').replace('\f', '').replace('\n', '').replace('\r', '').replace(u'\xe2\x80\xa8', '').replace(u'\xe2\x80\xa9', '').replace(u'\xc2\x85', '').encode('utf-8')

# pre-compile a bunch of regexps for strip_accents
# unicode
_re_unicode_lowercase_a = re.compile(unicode(r"(?u)[áàäâãå]", "utf-8"))
_re_unicode_lowercase_ae = re.compile(unicode(r"(?u)[æ]", "utf-8"))
_re_unicode_lowercase_e = re.compile(unicode(r"(?u)[éèëê]", "utf-8"))
_re_unicode_lowercase_i = re.compile(unicode(r"(?u)[íìïî]", "utf-8"))
_re_unicode_lowercase_o = re.compile(unicode(r"(?u)[óòöôõø]", "utf-8"))
_re_unicode_lowercase_u = re.compile(unicode(r"(?u)[úùüû]", "utf-8"))
_re_unicode_lowercase_y = re.compile(unicode(r"(?u)[ýÿ]", "utf-8"))
_re_unicode_lowercase_c = re.compile(unicode(r"(?u)[çć]", "utf-8"))
_re_unicode_lowercase_n = re.compile(unicode(r"(?u)[ñ]", "utf-8"))
_re_unicode_uppercase_a = re.compile(unicode(r"(?u)[ÁÀÄÂÃÅ]", "utf-8"))
_re_unicode_uppercase_ae = re.compile(unicode(r"(?u)[Æ]", "utf-8"))
_re_unicode_uppercase_e = re.compile(unicode(r"(?u)[ÉÈËÊ]", "utf-8"))
_re_unicode_uppercase_i = re.compile(unicode(r"(?u)[ÍÌÏÎ]", "utf-8"))
_re_unicode_uppercase_o = re.compile(unicode(r"(?u)[ÓÒÖÔÕØ]", "utf-8"))
_re_unicode_uppercase_u = re.compile(unicode(r"(?u)[ÚÙÜÛ]", "utf-8"))
_re_unicode_uppercase_y = re.compile(unicode(r"(?u)[Ý]", "utf-8"))
_re_unicode_uppercase_c = re.compile(unicode(r"(?u)[ÇĆ]", "utf-8"))
_re_unicode_uppercase_n = re.compile(unicode(r"(?u)[Ñ]", "utf-8"))

# latex
_re_latex_lowercase_a = re.compile("\\\\[\"H'`~^vu=k]\{?a\}?")
_re_latex_lowercase_ae = re.compile("\\\\ae\\{\\}?")
_re_latex_lowercase_e = re.compile("\\\\[\"H'`~^vu=k]\\{?e\\}?")
_re_latex_lowercase_i = re.compile("\\\\[\"H'`~^vu=k]\\{?i\\}?")
_re_latex_lowercase_o = re.compile("\\\\[\"H'`~^vu=k]\\{?o\\}?")
_re_latex_lowercase_u = re.compile("\\\\[\"H'`~^vu=k]\\{?u\\}?")
_re_latex_lowercase_y = re.compile("\\\\[\"']\\{?y\\}?")
_re_latex_lowercase_c = re.compile("\\\\['uc]\\{?c\\}?")
_re_latex_lowercase_n = re.compile("\\\\[c'~^vu]\\{?n\\}?")
_re_latex_uppercase_a = re.compile("\\\\[\"H'`~^vu=k]\\{?A\\}?")
_re_latex_uppercase_ae = re.compile("\\\\AE\\{?\\}?")
_re_latex_uppercase_e = re.compile("\\\\[\"H'`~^vu=k]\\{?E\\}?")
_re_latex_uppercase_i = re.compile("\\\\[\"H'`~^vu=k]\\{?I\\}?")
_re_latex_uppercase_o = re.compile("\\\\[\"H'`~^vu=k]\\{?O\\}?")
_re_latex_uppercase_u = re.compile("\\\\[\"H'`~^vu=k]\\{?U\\}?")
_re_latex_uppercase_y = re.compile("\\\\[\"']\\{?Y\\}?")
_re_latex_uppercase_c = re.compile("\\\\['uc]\\{?C\\}?")
_re_latex_uppercase_n = re.compile("\\\\[c'~^vu]\\{?N\\}?")

def strip_accents(x):
    """Strip accents in the input phrase X (assumed in UTF-8) by replacing
    accented characters with their unaccented cousins (e.g. é by e).
    Return such a stripped X."""
    x = _re_latex_lowercase_a.sub("a", x)
    x = _re_latex_lowercase_ae.sub("ae", x)
    x = _re_latex_lowercase_e.sub("e", x)
    x = _re_latex_lowercase_i.sub("i", x)
    x = _re_latex_lowercase_o.sub("o", x)
    x = _re_latex_lowercase_u.sub("u", x)
    x = _re_latex_lowercase_y.sub("x", x)
    x = _re_latex_lowercase_c.sub("c", x)
    x = _re_latex_lowercase_n.sub("n", x)
    x = _re_latex_uppercase_a.sub("A", x)
    x = _re_latex_uppercase_ae.sub("AE", x)
    x = _re_latex_uppercase_e.sub("E", x)
    x = _re_latex_uppercase_i.sub("I", x)
    x = _re_latex_uppercase_o.sub("O", x)
    x = _re_latex_uppercase_u.sub("U", x)
    x = _re_latex_uppercase_y.sub("Y", x)
    x = _re_latex_uppercase_c.sub("C", x)
    x = _re_latex_uppercase_n.sub("N", x)

    # convert input into Unicode string:
    try:
        y = unicode(x, "utf-8")
    except UnicodeDecodeError:
        return x # something went wrong, probably the input wasn't UTF-8
    # asciify Latin-1 lowercase characters:
    y = _re_unicode_lowercase_a.sub("a", y)
    y = _re_unicode_lowercase_ae.sub("ae", y)
    y = _re_unicode_lowercase_e.sub("e", y)
    y = _re_unicode_lowercase_i.sub("i", y)
    y = _re_unicode_lowercase_o.sub("o", y)
    y = _re_unicode_lowercase_u.sub("u", y)
    y = _re_unicode_lowercase_y.sub("y", y)
    y = _re_unicode_lowercase_c.sub("c", y)
    y = _re_unicode_lowercase_n.sub("n", y)
    # asciify Latin-1 uppercase characters:
    y = _re_unicode_uppercase_a.sub("A", y)
    y = _re_unicode_uppercase_ae.sub("AE", y)
    y = _re_unicode_uppercase_e.sub("E", y)
    y = _re_unicode_uppercase_i.sub("I", y)
    y = _re_unicode_uppercase_o.sub("O", y)
    y = _re_unicode_uppercase_u.sub("U", y)
    y = _re_unicode_uppercase_y.sub("Y", y)
    y = _re_unicode_uppercase_c.sub("C", y)
    y = _re_unicode_uppercase_n.sub("N", y)
    # return UTF-8 representation of the Unicode string:
    return y.encode("utf-8")
