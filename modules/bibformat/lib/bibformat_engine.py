# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) 2006, 2007, 2008, 2009, 2010, 2011 CERN.
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
Formats a single XML Marc record using specified format.
There is no API for the engine. Instead use bibformat.py.

SEE: bibformat.py, bibformat_utils.py
"""

__revision__ = "$Id$"

import re
import sys
import os
import inspect
import traceback
import zlib
import cgi

from invenio.config import \
     CFG_PATH_PHP, \
     CFG_BINDIR, \
     CFG_SITE_LANG
from invenio.errorlib import \
     register_errors, \
     get_msgs_for_code_list
from invenio.bibrecord import \
     create_record, \
     record_get_field_instances, \
     record_get_field_value, \
     record_get_field_values, \
     record_xml_output
from invenio.bibformat_xslt_engine import format
from invenio.dbquery import run_sql
from invenio.messages import \
     language_list_long, \
     wash_language, \
     gettext_set_language
from invenio import bibformat_dblayer
from invenio.bibformat_config import \
     CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION, \
     CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION, \
     CFG_BIBFORMAT_TEMPLATES_PATH, \
     CFG_BIBFORMAT_ELEMENTS_PATH, \
     CFG_BIBFORMAT_OUTPUTS_PATH, \
     CFG_BIBFORMAT_ELEMENTS_IMPORT_PATH
from invenio.bibformat_utils import \
     record_get_xml, \
     parse_tag
from invenio.htmlutils import \
     HTMLWasher, \
     cfg_html_buffer_allowed_tag_whitelist, \
     cfg_html_buffer_allowed_attribute_whitelist
from invenio.webuser import collect_user_info
from invenio.bibknowledge import get_kbr_values
from HTMLParser import HTMLParseError

if CFG_PATH_PHP: #Remove when call_old_bibformat is removed
    from xml.dom import minidom
    import tempfile

# Cache for data we have already read and parsed
format_templates_cache = {}
format_elements_cache = {}
format_outputs_cache = {}

html_field = '<!--HTML-->' # String indicating that field should be
                           # treated as HTML (and therefore no escaping of
                           # HTML tags should occur.
                           # Appears in some field values.

washer = HTMLWasher()      # Used to remove dangerous tags from HTML
                           # sources

# Regular expression for finding <lang>...</lang> tag in format templates
pattern_lang = re.compile(r'''
    <lang              #<lang tag (no matter case)
    \s*                #any number of white spaces
    >                  #closing <lang> start tag
    (?P<langs>.*?)     #anything but the next group (greedy)
    (</lang\s*>)       #end tag
    ''', re.IGNORECASE | re.DOTALL | re.VERBOSE)

# Builds regular expression for finding each known language in <lang> tags
ln_pattern_text = r"<("
for lang in language_list_long(enabled_langs_only=False):
    ln_pattern_text += lang[0] +r"|"

ln_pattern_text = ln_pattern_text.rstrip(r"|")
ln_pattern_text += r")>(.*?)</\1>"

ln_pattern =  re.compile(ln_pattern_text, re.IGNORECASE | re.DOTALL)

# Regular expression for finding text to be translated
translation_pattern = re.compile(r'_\((?P<word>.*?)\)_', \
                                 re.IGNORECASE | re.DOTALL | re.VERBOSE)

# Regular expression for finding <name> tag in format templates
pattern_format_template_name = re.compile(r'''
    <name              #<name tag (no matter case)
    \s*                #any number of white spaces
    >                  #closing <name> start tag
    (?P<name>.*?)      #name value. any char that is not end tag
    (</name\s*>)(\n)?  #end tag
    ''', re.IGNORECASE | re.DOTALL | re.VERBOSE)

# Regular expression for finding <description> tag in format templates
pattern_format_template_desc = re.compile(r'''
    <description           #<decription tag (no matter case)
    \s*                    #any number of white spaces
    >                      #closing <description> start tag
    (?P<desc>.*?)          #description value. any char that is not end tag
    </description\s*>(\n)? #end tag
    ''', re.IGNORECASE | re.DOTALL | re.VERBOSE)

# Regular expression for finding <BFE_ > tags in format templates
pattern_tag = re.compile(r'''
    <BFE_                        #every special tag starts with <BFE_ (no matter case)
    (?P<function_name>[^/\s]+)   #any char but a space or slash
    \s*                          #any number of spaces
    (?P<params>(\s*              #params here
     (?P<param>([^=\s])*)\s*     #param name: any chars that is not a white space or equality. Followed by space(s)
     =\s*                        #equality: = followed by any number of spaces
     (?P<sep>[\'"])              #one of the separators
     (?P<value>.*?)              #param value: any chars that is not a separator like previous one
     (?P=sep)                    #same separator as starting one
    )*)                          #many params
    \s*                          #any number of spaces
    (/)?>                        #end of the tag
    ''', re.IGNORECASE | re.DOTALL | re.VERBOSE)

# Regular expression for finding params inside <BFE_ > tags in format templates
pattern_function_params = re.compile('''
    (?P<param>([^=\s])*)\s*  # Param name: any chars that is not a white space or equality. Followed by space(s)
    =\s*                     # Equality: = followed by any number of spaces
    (?P<sep>[\'"])           # One of the separators
    (?P<value>.*?)           # Param value: any chars that is not a separator like previous one
    (?P=sep)                 # Same separator as starting one
    ''', re.VERBOSE | re.DOTALL )

# Regular expression for finding format elements "params" attributes
# (defined by @param)
pattern_format_element_params = re.compile('''
    @param\s*                          # Begins with AT param keyword followed by space(s)
    (?P<name>[^\s=]*):\s*              # A single keyword and comma, then space(s)
    #(=\s*(?P<sep>[\'"])               # Equality, space(s) and then one of the separators
    #(?P<default>.*?)                  # Default value: any chars that is not a separator like previous one
    #(?P=sep)                          # Same separator as starting one
    #)?\s*                             # Default value for param is optional. Followed by space(s)
    (?P<desc>.*)                       # Any text that is not end of line (thanks to MULTILINE parameter)
    ''', re.VERBOSE | re.MULTILINE)

# Regular expression for finding format elements "see also" attribute
# (defined by @see)
pattern_format_element_seealso = re.compile('''@see:\s*(?P<see>.*)''',
                                            re.VERBOSE | re.MULTILINE)

#Regular expression for finding 2 expressions in quotes, separated by
#comma (as in template("1st","2nd") )
#Used when parsing output formats
## pattern_parse_tuple_in_quotes = re.compile('''
##      (?P<sep1>[\'"])
##      (?P<val1>.*)
##      (?P=sep1)
##      \s*,\s*
##      (?P<sep2>[\'"])
##      (?P<val2>.*)
##      (?P=sep2)
##      ''', re.VERBOSE | re.MULTILINE)

def call_old_bibformat(recID, of="HD", on_the_fly=False, verbose=0):
    """
    FIXME: REMOVE FUNCTION WHEN MIGRATION IS DONE
    Calls BibFormat for the record RECID in the desired output format 'of'.

    @param recID: record ID to format
    @param of: output format to be used for formatting
    @param on_the_fly: if False, try to return an already preformatted version of the record in the database
    @param verbose: verbosity

    Note: this functions always try to return HTML, so when
    bibformat returns XML with embedded HTML format inside the tag
    FMT $g, as is suitable for prestoring output formats, we
    perform un-XML-izing here in order to return HTML body only.
    """

    out = ""
    res = []
    if not on_the_fly:
        # look for formatted record existence:
        query = "SELECT value, last_updated FROM bibfmt WHERE "\
                "id_bibrec='%s' AND format='%s'" % (recID, of)
        res = run_sql(query, None, 1)
    if res:
        # record 'recID' is formatted in 'of', so print it
        if verbose == 9:
            last_updated = res[0][1]
            out += """\n<br/><span class="quicknote">
            Found preformatted output for record %i (cache updated on %s).
            </span>""" % (recID, last_updated)
        decompress = zlib.decompress
        return "%s" % decompress(res[0][0])
    else:
        # record 'recID' is not formatted in 'of',
        # so try to call BibFormat on the fly or use default format:
        if verbose == 9:
            out += """\n<br/><span class="quicknote">
            Formatting record %i on-the-fly with old BibFormat.
            </span><br/>""" % recID

        # Retrieve MARCXML
        # Build it on-the-fly only if 'call_old_bibformat' was called
        # with format=xm and on_the_fly=True
        xm_record = record_get_xml(recID, 'xm',
                                   on_the_fly=(on_the_fly and of == 'xm'))

##         import platform
##         # Some problem have been found using either popen() or os.system().
##         # Here is a temporary workaround until the issue is solved.
##         if platform.python_compiler().find('Red Hat') > -1:
##             # use os.system
        (result_code, result_path) = tempfile.mkstemp()
        command = "( %s/bibformat otype=%s )  > %s" % \
                                     (CFG_BINDIR, of, result_path)
        (xm_code, xm_path) = tempfile.mkstemp()
        xm_file = open(xm_path, "w")
        xm_file.write(xm_record)
        xm_file.close()
        command = command + " <" + xm_path
        os.system(command)
        result_file = open(result_path,"r")
        bibformat_output = result_file.read()
        result_file.close()
        os.close(result_code)
        os.remove(result_path)
        os.close(xm_code)
        os.remove(xm_path)
##         else:
##             # use popen
##         pipe_input, pipe_output, pipe_error = os.popen3(["%s/bibformat" % CFG_BINDIR,
##                                                         "otype=%s" % format],
##                                                         'rw')
##         pipe_input.write(xm_record)
##         pipe_input.flush()
##         pipe_input.close()
##         bibformat_output = pipe_output.read()
##         pipe_output.close()
##         pipe_error.close()

        if bibformat_output.startswith("<record>"):
            dom = minidom.parseString(bibformat_output)
            for e in dom.getElementsByTagName('subfield'):
                if e.getAttribute('code') == 'g':
                    for t in e.childNodes:
                        out += t.data.encode('utf-8')
        else:
            out += bibformat_output
        return out

def format_record(recID, of, ln=CFG_SITE_LANG, verbose=0,
                  search_pattern=None, xml_record=None, user_info=None):
    """
    Formats a record given output format. Main entry function of
    bibformat engine.

    Returns a formatted version of the record in the specified
    language, search pattern, and with the specified output format.
    The function will define which format template must be applied.

    You can either specify an record ID to format, or give its xml
    representation.  if 'xml_record' is not None, then use it instead
    of recID.

    'user_info' allows to grant access to some functionalities on a
    page depending on the user's priviledges. 'user_info' is the same
    object as the one returned by 'webuser.collect_user_info(req)'

    @param recID: the ID of record to format
    @param of: an output format code (or short identifier for the output format)
    @param ln: the language to use to format the record
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings, stop if error in format elements
                                                       9: errors and warnings, stop if error (debug mode ))
    @param search_pattern: list of strings representing the user request in web interface
    @param xml_record: an xml string representing the record to format
    @param user_info: the information of the user who will view the formatted page
    @return: formatted record
    """
    if search_pattern is None:
        search_pattern = []

    out = ""
    errors_ = []
    # Temporary workflow (during migration of formats):
    # Call new BibFormat
    # But if format not found for new BibFormat, then call old BibFormat

    #Create a BibFormat Object to pass that contain record and context
    bfo = BibFormatObject(recID, ln, search_pattern, xml_record, user_info, of)

    if of.lower() != 'xm' and \
           (not bfo.get_record() or len(bfo.get_record()) <= 1):
        # Record only has recid: do not format, excepted
        # for xm format
        return ""

    #Find out which format template to use based on record and output format.
    template = decide_format_template(bfo, of)
    if verbose == 9 and template is not None:
        out += """\n<br/><span class="quicknote">
        Using %s template for record %i.
        </span>""" % (template, recID)

    ############### FIXME: REMOVE WHEN MIGRATION IS DONE ###############
    path = "%s%s%s" % (CFG_BIBFORMAT_TEMPLATES_PATH, os.sep, template)
    if template is None or not os.access(path, os.R_OK):
        # template not found in new BibFormat. Call old one
        if verbose == 9:
            if template is None:
                out += """\n<br/><span class="quicknote">
                No template found for output format %s and record %i.
                (Check invenio.err log file for more details)
                </span>""" % (of, recID)
            else:
                out += """\n<br/><span class="quicknote">
                Template %s could not be read.
                </span>""" % (template)
        if CFG_PATH_PHP:
            if verbose == 9:
                out += """\n<br/><span class="quicknote">
                Using old BibFormat for record %s.
                </span>""" % recID
            return out + call_old_bibformat(recID, of=of, on_the_fly=True,
                                            verbose=verbose)
    ############################# END ##################################

        error = get_msgs_for_code_list([("ERR_BIBFORMAT_NO_TEMPLATE_FOUND", of)],
                                       stream='error', ln=CFG_SITE_LANG)
        errors_.append(error)
        if verbose == 0:
            register_errors(error, 'error')
        elif verbose > 5:
            return out + error[0][1]
        return out

    # Format with template
    (out_, errors) = format_with_format_template(template, bfo, verbose)
    errors_.extend(errors)

    out += out_

    return out

def decide_format_template(bfo, of):
    """
    Returns the format template name that should be used for formatting
    given output format and BibFormatObject.

    Look at of rules, and take the first matching one.
    If no rule matches, returns None

    To match we ignore lettercase and spaces before and after value of
    rule and value of record

    @param bfo: a BibFormatObject
    @param of: the code of the output format to use
    """

    output_format = get_output_format(of)

    for rule in output_format['rules']:
        if rule['field'].startswith('00'):
            # Rule uses controlfield
            value = bfo.control_field(rule['field']).strip() #Remove spaces
        else:
            # Rule uses datafield
            value = bfo.field(rule['field']).strip() #Remove spaces
        pattern = rule['value'].strip() #Remove spaces
        match_obj = re.match(pattern, value, re.IGNORECASE)
        if match_obj is not None and \
               match_obj.start() == 0 and match_obj.end() == len(value):
            return rule['template']

    template = output_format['default']
    if template != '':
        return template
    else:
        return None

def format_with_format_template(format_template_filename, bfo,
                                verbose=0, format_template_code=None):
    """ Format a record given a
    format template. Also returns errors

    Returns a formatted version of the record represented by bfo,
    in the language specified in bfo, and with the specified format template.

    If format_template_code is provided, the template will not be loaded from
    format_template_filename (but format_template_filename will still be used to
    determine if bft or xsl transformation applies). This allows to preview format
    code without having to save file on disk.

    @param format_template_filename: the dilename of a format template
    @param bfo: the object containing parameters for the current formatting
    @param format_template_code: if not empty, use code as template instead of reading format_template_filename (used for previews)
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings,
                                                       9: errors and warnings, stop if error (debug mode ))
    @return: tuple (formatted text, errors)
    """
    _ = gettext_set_language(bfo.lang)

    def translate(match):
        """
        Translate matching values
        """
        word = match.group("word")
        translated_word = _(word)
        return translated_word

    errors_ = []
    if format_template_code is not None:
        format_content = str(format_template_code)
    else:
        format_content = get_format_template(format_template_filename)['code']

    if format_template_filename is None or \
           format_template_filename.endswith("."+CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION):
        # .bft
        filtered_format = filter_languages(format_content, bfo.lang)
        localized_format = translation_pattern.sub(translate, filtered_format)

        (evaluated_format, errors) = eval_format_template_elements(localized_format,
                                                                   bfo,
                                                                   verbose)
        errors_ = errors
    else:
        #.xsl
        if bfo.xml_record:
            # bfo was initialized with a custom MARCXML
            xml_record = '<?xml version="1.0" encoding="UTF-8"?>\n' + \
                         record_xml_output(bfo.record)
        else:
            # Fetch MARCXML. On-the-fly xm if we are now formatting in xm
            xml_record = '<?xml version="1.0" encoding="UTF-8"?>\n' + \
                         record_get_xml(bfo.recID, 'xm', on_the_fly=False)

        # Transform MARCXML using stylesheet
        evaluated_format = format(xml_record, template_source=format_content)

    return (evaluated_format, errors_)


def eval_format_template_elements(format_template, bfo, verbose=0):
    """
    Evalutes the format elements of the given template and replace each element with its value.
    Also returns errors.

    Prepare the format template content so that we can directly replace the marc code by their value.
    This implies: 1) Look for special tags
                  2) replace special tags by their evaluation

    @param format_template: the format template code
    @param bfo: the object containing parameters for the current formatting
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings,
                                                       9: errors and warnings, stop if error (debug mode ))
    @return: tuple (result, errors)
    """
    errors_ = []

    # First define insert_element_code(match), used in re.sub() function
    def insert_element_code(match):
        """
        Analyses 'match', interpret the corresponding code, and return the result of the evaluation.

        Called by substitution in 'eval_format_template_elements(...)'

        @param match: a match object corresponding to the special tag that must be interpreted
        """

        function_name = match.group("function_name")
        try:
            format_element = get_format_element(function_name, verbose)
        except Exception, e:
            if verbose >= 5:
                return '<b><span style="color: rgb(255, 0, 0);">' + \
                       cgi.escape(str(e)).replace('\n', '<br/>') + \
                       '</span>'
        if format_element is None:
            error = get_msgs_for_code_list([("ERR_BIBFORMAT_CANNOT_RESOLVE_ELEMENT_NAME", function_name)],
                                           stream='error', ln=CFG_SITE_LANG)
            errors_.append(error)
            if verbose >= 5:
                return '<b><span style="color: rgb(255, 0, 0);">' + \
                       error[0][1]+'</span></b>'
        else:
            params = {}
            # Look for function parameters given in format template code
            all_params = match.group('params')
            if all_params is not None:
                function_params_iterator = pattern_function_params.finditer(all_params)
                for param_match in function_params_iterator:
                    name = param_match.group('param')
                    value = param_match.group('value')
                    params[name] = value

            # Evaluate element with params and return (Do not return errors)
            (result, errors) = eval_format_element(format_element,
                                                   bfo,
                                                   params,
                                                   verbose)
            errors_.append(errors)
            return result


    # Substitute special tags in the format by our own text.
    # Special tags have the form <BNE_format_element_name [param="value"]* />
    format = pattern_tag.sub(insert_element_code, format_template)

    return (format, errors_)


def eval_format_element(format_element, bfo, parameters=None, verbose=0):
    """
    Returns the result of the evaluation of the given format element
    name, with given BibFormatObject and parameters. Also returns
    the errors of the evaluation.

    @param format_element: a format element structure as returned by get_format_element
    @param bfo: a BibFormatObject used for formatting
    @param parameters: a dict of parameters to be used for formatting. Key is parameter and value is value of parameter
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings,
                                                       9: errors and warnings, stop if error (debug mode ))

    @return: tuple (result, errors)
    """
    if parameters is None:
        parameters = {}

    errors = []
    #Load special values given as parameters
    prefix = parameters.get('prefix', "")
    suffix = parameters.get('suffix', "")
    default_value = parameters.get('default', "")
    escape = parameters.get('escape', "")
    output_text = ''

    # 3 possible cases:
    # a) format element file is found: we execute it
    # b) format element file is not found, but exist in tag table (e.g. bfe_isbn)
    # c) format element is totally unknown. Do nothing or report error

    if format_element is not None and format_element['type'] == "python":
        # a) We found an element with the tag name, of type "python"
        # Prepare a dict 'params' to pass as parameter to 'format'
        # function of element
        params = {}

        # Look for parameters defined in format element
        # Fill them with specified default values and values
        # given as parameters.
        # Also remember if the element overrides the 'escape'
        # parameter
        format_element_overrides_escape = False
        for param in format_element['attrs']['params']:
            name = param['name']
            default = param['default']
            params[name] = parameters.get(name, default)
            if name == 'escape':
                format_element_overrides_escape = True

        # Add BibFormatObject
        params['bfo'] = bfo

        # Execute function with given parameters and return result.
        function = format_element['code']

        try:
            output_text = apply(function, (), params)
        except Exception, e:
            name = format_element['attrs']['name']
            error = ("ERR_BIBFORMAT_EVALUATING_ELEMENT", name, str(params))
            errors.append(error)
            if verbose == 0:
                register_errors(errors, 'error')
            elif verbose >= 5:
                tb = sys.exc_info()[2]
                error_string = get_msgs_for_code_list(error,
                                                      stream='error',
                                                      ln=CFG_SITE_LANG)
                stack = traceback.format_exception(Exception, e, tb, limit=None)
                output_text = '<b><span style="color: rgb(255, 0, 0);">'+ \
                              str(error_string[0][1]) + "".join(stack) +'</span></b> '

        # None can be returned when evaluating function
        if output_text is None:
            output_text = ""
        else:
            output_text = str(output_text)

        # Escaping:
        # (1) By default, everything is escaped in mode 1
        # (2) If evaluated element has 'escape_values()' function, use
        #     its returned value as escape mode, and override (1)
        # (3) If template has a defined parameter 'escape' (in allowed
        #     values), use it, and override (1) and (2). If this
        #     'escape' parameter is overriden by the format element
        #     (defined in the 'format' function of the element), leave
        #     the escaping job to this element

        # (1)
        escape_mode = 1

        # (2)
        escape_function = format_element['escape_function']
        if escape_function is not None:
            try:
                escape_mode = apply(escape_function, (), {'bfo': bfo})
            except Exception, e:
                error = ("ERR_BIBFORMAT_EVALUATING_ELEMENT_ESCAPE", name)
                errors.append(error)
                if verbose == 0:
                    register_errors(errors, 'error')
                elif verbose >= 5:
                    tb = sys.exc_info()[2]
                    error_string = get_msgs_for_code_list(error,
                                                          stream='error',
                                                          ln=CFG_SITE_LANG)
                    output_text += '<b><span style="color: rgb(255, 0, 0);">'+ \
                                   str(error_string[0][1]) +'</span></b> '
        # (3)
        if escape in ['0', '1', '2', '3', '4', '5', '6', '7']:
            escape_mode = int(escape)

        # If escape is equal to 1, then escape all
        # HTML reserved chars.
        if escape_mode > 0 and not format_element_overrides_escape:
            output_text = escape_field(output_text, mode=escape_mode)

        # Add prefix and suffix if they have been given as parameters and if
        # the evaluation of element is not empty
        if output_text.strip() != "":
            output_text = prefix + output_text + suffix

        # Add the default value if output_text is empty
        if output_text == "":
            output_text = default_value

        return (output_text, errors)

    elif format_element is not None and format_element['type'] == "field":
        # b) We have not found an element in files that has the tag
        # name. Then look for it in the table "tag"
        #
        # <BFE_LABEL_IN_TAG prefix = "" suffix = "" separator = ""
        #                   nbMax="" escape="0"/>
        #

        # Load special values given as parameters
        separator = parameters.get('separator ', "")
        nbMax = parameters.get('nbMax', "")
        escape = parameters.get('escape', "1") # By default, escape here

        # Get the fields tags that have to be printed
        tags = format_element['attrs']['tags']

        output_text = []

        # Get values corresponding to tags
        for tag in tags:
            p_tag = parse_tag(tag)
            values = record_get_field_values(bfo.get_record(),
                                             p_tag[0],
                                             p_tag[1],
                                             p_tag[2],
                                             p_tag[3])
            if len(values)>0 and isinstance(values[0], dict):
                #flatten dict to its values only
                values_list = map(lambda x: x.values(), values)
                #output_text.extend(values)
                for values in values_list:
                    output_text.extend(values)
            else:
                output_text.extend(values)

        if nbMax != "":
            try:
                nbMax = int(nbMax)
                output_text = output_text[:nbMax]
            except:
                name = format_element['attrs']['name']
                error = ("ERR_BIBFORMAT_NBMAX_NOT_INT", name)
                errors.append(error)
                if verbose < 5:
                    register_errors(error, 'error')
                elif verbose >= 5:
                    error_string = get_msgs_for_code_list(error,
                                                          stream='error',
                                                          ln=CFG_SITE_LANG)
                    output_text = output_text.append(error_string[0][1])



        # Add prefix and suffix if they have been given as parameters and if
        # the evaluation of element is not empty.
        # If evaluation is empty string, return default value if it exists.
        # Else return empty string
        if ("".join(output_text)).strip() != "":
            # If escape is equal to 1, then escape all
            # HTML reserved chars.
            if escape == '1':
                output_text = cgi.escape(separator.join(output_text))
            else:
                output_text = separator.join(output_text)

            output_text = prefix + output_text + suffix
        else:
            #Return default value
            output_text = default_value

        return (output_text, errors)
    else:
        # c) Element is unknown
        error = get_msgs_for_code_list([("ERR_BIBFORMAT_CANNOT_RESOLVE_ELEMENT_NAME", format_element)],
                                       stream='error', ln=CFG_SITE_LANG)
        errors.append(error)
        if verbose < 5:
            register_errors(error, 'error')
            return ("", errors)
        elif verbose >= 5:
            if verbose >= 9:
                sys.exit(error[0][1])
            return ('<b><span style="color: rgb(255, 0, 0);">' + \
                    error[0][1]+'</span></b>', errors)


def filter_languages(format_template, ln='en'):
    """
    Filters the language tags that do not correspond to the specified language.

    @param format_template: the format template code
    @param ln: the language that is NOT filtered out from the template
    @return: the format template with unnecessary languages filtered out
    """
    # First define search_lang_tag(match) and clean_language_tag(match), used
    # in re.sub() function
    def search_lang_tag(match):
        """
        Searches for the <lang>...</lang> tag and remove inner localized tags
        such as <en>, <fr>, that are not current_lang.

        If current_lang cannot be found inside <lang> ... </lang>, try to use 'CFG_SITE_LANG'

        @param match: a match object corresponding to the special tag that must be interpreted
        """
        current_lang = ln
        def clean_language_tag(match):
            """
            Return tag text content if tag language of match is output language.

            Called by substitution in 'filter_languages(...)'

            @param match: a match object corresponding to the special tag that must be interpreted
            """
            if match.group(1) == current_lang:
                return match.group(2)
            else:
                return ""
            # End of clean_language_tag


        lang_tag_content = match.group("langs")
        # Try to find tag with current lang. If it does not exists,
        # then current_lang becomes CFG_SITE_LANG until the end of this
        # replace
        pattern_current_lang = re.compile(r"<("+current_lang+ \
                                          r")\s*>(.*?)(</"+current_lang+r"\s*>)", re.IGNORECASE | re.DOTALL)
        if re.search(pattern_current_lang, lang_tag_content) is None:
            current_lang = CFG_SITE_LANG

        cleaned_lang_tag = ln_pattern.sub(clean_language_tag, lang_tag_content)
        return cleaned_lang_tag
        # End of search_lang_tag


    filtered_format_template = pattern_lang.sub(search_lang_tag, format_template)
    return filtered_format_template

def get_format_template(filename, with_attributes=False):
    """
    Returns the structured content of the given formate template.

    if 'with_attributes' is true, returns the name and description. Else 'attrs' is not
    returned as key in dictionary (it might, if it has already been loaded previously)

    {'code':"<b>Some template code</b>"
     'attrs': {'name': "a name", 'description': "a description"}
    }

    @param filename: the filename of an format template
    @param with_attributes: if True, fetch the attributes (names and description) for format'
    @return: strucured content of format template
    """

    # Get from cache whenever possible
    global format_templates_cache

    if not filename.endswith("."+CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION) and \
           not filename.endswith(".xsl"):
        return None

    if format_templates_cache.has_key(filename):
        # If we must return with attributes and template exist in
        # cache with attributes then return cache.
        # Else reload with attributes
        if with_attributes and \
               format_templates_cache[filename].has_key('attrs'):
            return format_templates_cache[filename]

    format_template = {'code':""}
    try:

        path = "%s%s%s" % (CFG_BIBFORMAT_TEMPLATES_PATH, os.sep, filename)

        format_file = open(path)
        format_content = format_file.read()
        format_file.close()

        # Load format template code
        # Remove name and description
        if filename.endswith("."+CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION):
            code_and_description = pattern_format_template_name.sub("",
                                                                    format_content, 1)
            code = pattern_format_template_desc.sub("", code_and_description, 1)
        else:
            code = format_content

        format_template['code'] = code

    except Exception, e:
        errors = get_msgs_for_code_list([("ERR_BIBFORMAT_CANNOT_READ_TEMPLATE_FILE", filename, str(e))],
                                        stream='error', ln=CFG_SITE_LANG)
        register_errors(errors, 'error')

    # Save attributes if necessary
    if with_attributes:
        format_template['attrs'] = get_format_template_attrs(filename)

    # Cache and return
    format_templates_cache[filename] = format_template
    return format_template


def get_format_templates(with_attributes=False):
    """
    Returns the list of all format templates, as dictionary with filenames as keys

    if 'with_attributes' is true, returns the name and description. Else 'attrs' is not
    returned as key in each dictionary (it might, if it has already been loaded previously)

    [{'code':"<b>Some template code</b>"
      'attrs': {'name': "a name", 'description': "a description"}
     },
    ...
    }
    @param with_attributes: if True, fetch the attributes (names and description) for formats
    """
    format_templates = {}
    files = os.listdir(CFG_BIBFORMAT_TEMPLATES_PATH)

    for filename in files:
        if filename.endswith("."+CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION) or \
               filename.endswith(".xsl"):
            format_templates[filename] = get_format_template(filename,
                                                             with_attributes)

    return format_templates

def get_format_template_attrs(filename):
    """
    Returns the attributes of the format template with given filename

    The attributes are {'name', 'description'}
    Caution: the function does not check that path exists or
    that the format element is valid.
    @param the: path to a format element
    """
    attrs = {}
    attrs['name'] = ""
    attrs['description'] = ""
    try:
        template_file = open("%s%s%s" % (CFG_BIBFORMAT_TEMPLATES_PATH,
                                         os.sep,
                                         filename))
        code = template_file.read()
        template_file.close()

        match = None
        if filename.endswith(".xsl"):
            # .xsl
            attrs['name'] = filename[:-4]
        else:
            # .bft
            match = pattern_format_template_name.search(code)
            if match is not None:
                attrs['name'] = match.group('name')
            else:
                attrs['name'] = filename


            match = pattern_format_template_desc.search(code)
            if match is not None:
                attrs['description'] = match.group('desc').rstrip('.')
    except Exception, e:
        errors = get_msgs_for_code_list([("ERR_BIBFORMAT_CANNOT_READ_TEMPLATE_FILE",
                                          filename, str(e))],
                                        stream='error', ln=CFG_SITE_LANG)
        register_errors(errors, 'error')
        attrs['name'] = filename

    return attrs


def get_format_element(element_name, verbose=0, with_built_in_params=False):
    """
    Returns the format element structured content.

    Return None if element cannot be loaded (file not found, not readable or
    invalid)

    The returned structure is {'attrs': {some attributes in dict. See get_format_element_attrs_from_*}
                               'code': the_function_code,
                               'type':"field" or "python" depending if element is defined in file or table,
                               'escape_function': the function to call to know if element output must be escaped}

    @param element_name: the name of the format element to load
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings,
                                                       9: errors and warnings, stop if error (debug mode ))
    @param with_built_in_params: if True, load the parameters built in all elements
    @return: a dictionary with format element attributes
    """
    # Get from cache whenever possible
    global format_elements_cache

    errors = []

    # Resolve filename and prepare 'name' as key for the cache
    filename = resolve_format_element_filename(element_name)
    if filename is not None:
        name = filename.upper()
    else:
        name = element_name.upper()

    if format_elements_cache.has_key(name):
        element = format_elements_cache[name]
        if not with_built_in_params or \
               (with_built_in_params and \
                element['attrs'].has_key('builtin_params')):
            return element

    if filename is None:
        # Element is maybe in tag table
        if bibformat_dblayer.tag_exists_for_name(element_name):
            format_element = {'attrs': get_format_element_attrs_from_table( \
                element_name,
                with_built_in_params),
                              'code':None,
                              'escape_function':None,
                              'type':"field"}
            # Cache and returns
            format_elements_cache[name] = format_element
            return format_element

        else:
            errors = get_msgs_for_code_list([("ERR_BIBFORMAT_FORMAT_ELEMENT_NOT_FOUND",
                                              element_name)],
                                            stream='error', ln=CFG_SITE_LANG)
            if verbose == 0:
                register_errors(errors, 'error')
            elif verbose >= 5:
                sys.stderr.write(errors[0][1])
            return None

    else:
        format_element = {}

        module_name = filename
        if module_name.endswith(".py"):
            module_name = module_name[:-3]

        # Load element
        try:
            module = __import__(CFG_BIBFORMAT_ELEMENTS_IMPORT_PATH + \
                                "." + module_name)
            # Load last module in import path
            # For eg. load bfe_name in
            # invenio.bibformat_elements.bfe_name
            # Used to keep flexibility regarding where elements
            # directory is (for eg. test cases)
            components = CFG_BIBFORMAT_ELEMENTS_IMPORT_PATH.split(".")
            for comp in components[1:]:
                module = getattr(module, comp)

        except Exception, e:
            # We catch all exceptions here, as we just want to print
            # traceback in all cases
            tb = sys.exc_info()[2]
            stack = traceback.format_exception(Exception, e, tb, limit=None)
            errors = get_msgs_for_code_list([("ERR_BIBFORMAT_IN_FORMAT_ELEMENT",
                                              element_name,"\n" + "\n".join(stack[-2:-1]))],
                                            stream='error', ln=CFG_SITE_LANG)
            if verbose == 0:
                register_errors(errors, 'error')
            elif verbose >= 5:
                sys.stderr.write(errors[0][1])

        if errors:
            if verbose >= 7:
                raise Exception, errors[0][1]
            return None

        # Load function 'format_element()' inside element
        try:
            function_format  = module.__dict__[module_name].format_element
            format_element['code'] = function_format
        except AttributeError, e:
            # Try to load 'format()' function
            try:
                function_format  = module.__dict__[module_name].format
                format_element['code'] = function_format
            except AttributeError, e:
                errors = get_msgs_for_code_list([("ERR_BIBFORMAT_FORMAT_ELEMENT_FORMAT_FUNCTION",
                                                  element_name)],
                                                stream='error', ln=CFG_SITE_LANG)
                if verbose == 0:
                    register_errors(errors, 'error')
                elif verbose >= 5:
                    sys.stderr.write(errors[0][1])

        if errors:
            if verbose >= 7:
                raise Exception, errors[0][1]
            return None

        # Load function 'escape_values()' inside element
        function_escape  = getattr(module.__dict__[module_name],
                                   'escape_values',
                                   None)
        format_element['escape_function'] = function_escape

        # Prepare, cache and return
        format_element['attrs'] = get_format_element_attrs_from_function( \
                function_format,
                element_name,
                with_built_in_params)
        format_element['type'] = "python"
        format_elements_cache[name] = format_element
        return format_element

def get_format_elements(with_built_in_params=False):
    """
    Returns the list of format elements attributes as dictionary structure

    Elements declared in files have priority over element declared in 'tag' table
    The returned object has this format:
    {element_name1: {'attrs': {'description':..., 'seealso':...
                               'params':[{'name':..., 'default':..., 'description':...}, ...]
                               'builtin_params':[{'name':..., 'default':..., 'description':...}, ...]
                              },
                     'code': code_of_the_element
                    },
     element_name2: {...},
     ...}

     Returns only elements that could be loaded (not error in code)

    @return: a dict of format elements with name as key, and a dict as attributes
    @param with_built_in_params: if True, load the parameters built in all elements
    """
    format_elements = {}

    mappings = bibformat_dblayer.get_all_name_tag_mappings()

    for name in mappings:
        format_elements[name.upper().replace(" ", "_").strip()] = get_format_element(name, with_built_in_params=with_built_in_params)

    files = os.listdir(CFG_BIBFORMAT_ELEMENTS_PATH)
    for filename in files:
        filename_test = filename.upper().replace(" ", "_")
        if filename_test.endswith(".PY") and filename.upper() != "__INIT__.PY":
            if filename_test.startswith("BFE_"):
                filename_test = filename_test[4:]
            element_name = filename_test[:-3]
            element = get_format_element(element_name,
                                         with_built_in_params=with_built_in_params)
            if element is not None:
                format_elements[element_name] = element

    return format_elements

def get_format_element_attrs_from_function(function, element_name,
                                           with_built_in_params=False):
    """ Returns the attributes of the
    function given as parameter.

    It looks for standard parameters of the function, default
    values and comments in the docstring.
    The attributes are {'description', 'seealso':['element.py', ...],
    'params':{name:{'name', 'default', 'description'}, ...], name2:{}}

    The attributes are {'name' : "name of element" #basically the name of 'name' parameter
                        'description': "a string description of the element",
                        'seealso' : ["element_1.py", "element_2.py", ...] #a list of related elements
                        'params': [{'name':"param_name",   #a list of parameters for this element (except 'bfo')
                                    'default':"default value",
                                    'description': "a description"}, ...],
                        'builtin_params': {name: {'name':"param_name",#the parameters builtin for all elem of this kind
                                            'default':"default value",
                                            'description': "a description"}, ...},
                       }
    @param function: the formatting function of a format element
    @param element_name: the name of the element
    @param with_built_in_params: if True, load the parameters built in all elements
    """

    attrs = {}
    attrs['description'] = ""
    attrs['name'] = element_name.replace(" ", "_").upper()
    attrs['seealso'] = []

    docstring = function.__doc__
    if isinstance(docstring, str):
        # Look for function description in docstring
        #match = pattern_format_element_desc.search(docstring)
        description = docstring.split("@param")[0]
        description = description.split("@see:")[0]
        attrs['description'] = description.strip().rstrip('.')

        # Look for @see: in docstring
        match = pattern_format_element_seealso.search(docstring)
        if match is not None:
            elements = match.group('see').rstrip('.').split(",")
            for element in elements:
                attrs['seealso'].append(element.strip())

    params = {}
    # Look for parameters in function definition
    (args, varargs, varkw, defaults) = inspect.getargspec(function)

    # Prepare args and defaults_list such that we can have a mapping
    # from args to defaults
    args.reverse()
    if defaults is not None:
        defaults_list = list(defaults)
        defaults_list.reverse()
    else:
        defaults_list = []

    for arg, default in map(None, args, defaults_list):
        if arg == "bfo":
            #Don't keep this as parameter. It is hidden to users, and
            #exists in all elements of this kind
            continue
        param = {}
        param['name'] = arg
        if default is None:
            #In case no check is made inside element, we prefer to
            #print "" (nothing) than None in output
            param['default'] = ""
        else:
            param['default'] = default
        param['description'] = "(no description provided)"

        params[arg] = param

    if isinstance(docstring, str):
        # Look for AT param descriptions in docstring.
        # Add description to existing parameters in params dict
        params_iterator = pattern_format_element_params.finditer(docstring)
        for match in params_iterator:
            name = match.group('name')
            if params.has_key(name):
                params[name]['description'] = match.group('desc').rstrip('.')

    attrs['params'] = params.values()

    # Load built-in parameters if necessary
    if with_built_in_params:

        builtin_params = []
        # Add 'prefix' parameter
        param_prefix = {}
        param_prefix['name'] = "prefix"
        param_prefix['default'] = ""
        param_prefix['description'] = """A prefix printed only if the
                                         record has a value for this element"""
        builtin_params.append(param_prefix)

        # Add 'suffix' parameter
        param_suffix = {}
        param_suffix['name'] = "suffix"
        param_suffix['default'] = ""
        param_suffix['description'] = """A suffix printed only if the
                                         record has a value for this element"""
        builtin_params.append(param_suffix)

        # Add 'default' parameter
        param_default = {}
        param_default['name'] = "default"
        param_default['default'] = ""
        param_default['description'] = """A default value printed if the
                                          record has no value for this element"""
        builtin_params.append(param_default)

        # Add 'escape' parameter
        param_escape = {}
        param_escape['name'] = "escape"
        param_escape['default'] = ""
        param_escape['description'] = """0 keeps value as it is. Refer to main
                                         documentation for escaping modes
                                         1 to 7"""
        builtin_params.append(param_escape)

        attrs['builtin_params'] = builtin_params

    return attrs

def get_format_element_attrs_from_table(element_name,
                                        with_built_in_params=False):
    """
    Returns the attributes of the format element with given name in 'tag' table.

    Returns None if element_name does not exist in tag table.

    The attributes are {'name' : "name of element" #basically the name of 'element_name' parameter
                        'description': "a string description of the element",
                        'seealso' : [] #a list of related elements. Always empty in this case
                        'params': [],  #a list of parameters for this element. Always empty in this case
                        'builtin_params': [{'name':"param_name", #the parameters builtin for all elem of this kind
                                            'default':"default value",
                                            'description': "a description"}, ...],
                        'tags':["950.1", 203.a] #the list of tags printed by this element
                       }

    @param element_name: an element name in database
    @param element_name: the name of the element
    @param with_built_in_params: if True, load the parameters built in all elements
    """

    attrs = {}
    tags = bibformat_dblayer.get_tags_from_name(element_name)
    field_label = "field"
    if len(tags)>1:
        field_label = "fields"

    attrs['description'] = "Prints %s %s of the record" % (field_label,
                                                           ", ".join(tags))
    attrs['name'] = element_name.replace(" ", "_").upper()
    attrs['seealso'] = []
    attrs['params'] = []
    attrs['tags'] = tags

    # Load built-in parameters if necessary
    if with_built_in_params:
        builtin_params = []

        # Add 'prefix' parameter
        param_prefix = {}
        param_prefix['name'] = "prefix"
        param_prefix['default'] = ""
        param_prefix['description'] = """A prefix printed only if the
                                       record has a value for this element"""
        builtin_params.append(param_prefix)

        # Add 'suffix' parameter
        param_suffix = {}
        param_suffix['name'] = "suffix"
        param_suffix['default'] = ""
        param_suffix['description'] = """A suffix printed only if the
                                         record has a value for this element"""
        builtin_params.append(param_suffix)

        # Add 'separator' parameter
        param_separator = {}
        param_separator['name'] = "separator"
        param_separator['default'] = " "
        param_separator['description'] = """A separator between elements of
                                            the field"""
        builtin_params.append(param_separator)

        # Add 'nbMax' parameter
        param_nbMax = {}
        param_nbMax['name'] = "nbMax"
        param_nbMax['default'] = ""
        param_nbMax['description'] = """The maximum number of values to
                                      print for this element. No limit if not
                                      specified"""
        builtin_params.append(param_nbMax)

        # Add 'default' parameter
        param_default = {}
        param_default['name'] = "default"
        param_default['default'] = ""
        param_default['description'] = """A default value printed if the
                                          record has no value for this element"""
        builtin_params.append(param_default)

        # Add 'escape' parameter
        param_escape = {}
        param_escape['name'] = "escape"
        param_escape['default'] = ""
        param_escape['description'] = """If set to 1, replaces special
                                         characters '&', '<' and '>' of this
                                         element by SGML entities"""
        builtin_params.append(param_escape)

        attrs['builtin_params'] = builtin_params

    return attrs

def get_output_format(code, with_attributes=False, verbose=0):
    """
    Returns the structured content of the given output format

    If 'with_attributes' is true, also returns the names and description of the output formats,
    else 'attrs' is not returned in dict (it might, if it has already been loaded previously).

    if output format corresponding to 'code' is not found return an empty structure.

    See get_output_format_attrs() to learn more on the attributes


    {'rules': [ {'field': "980__a",
                 'value': "PREPRINT",
                 'template': "filename_a.bft",
                },
                {...}
              ],
     'attrs': {'names': {'generic':"a name", 'sn':{'en': "a name", 'fr':"un nom"}, 'ln':{'en':"a long name"}}
               'description': "a description"
               'code': "fnm1",
               'content_type': "application/ms-excel",
               'visibility': 1
              }
     'default':"filename_b.bft"
    }

    @param code: the code of an output_format
    @param with_attributes: if True, fetch the attributes (names and description) for format
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings,
                                                       9: errors and warnings, stop if error (debug mode ))
    @return: strucured content of output format
    """

    output_format = {'rules':[], 'default':""}
    filename = resolve_output_format_filename(code, verbose)

    if filename is None:
        errors = get_msgs_for_code_list([("ERR_BIBFORMAT_OUTPUT_FORMAT_CODE_UNKNOWN", code)],
                                        stream='error', ln=CFG_SITE_LANG)
        register_errors(errors, 'error')
        if with_attributes: #Create empty attrs if asked for attributes
            output_format['attrs'] = get_output_format_attrs(code, verbose)
        return output_format

    # Get from cache whenever possible
    global format_outputs_cache
    if format_outputs_cache.has_key(filename):
        # If was must return with attributes but cache has not
        # attributes, then load attributes
        if with_attributes and not \
               format_outputs_cache[filename].has_key('attrs'):
            format_outputs_cache[filename]['attrs'] = get_output_format_attrs(code, verbose)

        return format_outputs_cache[filename]

    try:
        if with_attributes:
            output_format['attrs'] = get_output_format_attrs(code, verbose)

        path = "%s%s%s" % (CFG_BIBFORMAT_OUTPUTS_PATH, os.sep, filename )
        format_file = open(path)

        current_tag = ''
        for line in format_file:
            line = line.strip()
            if line == "":
                # Ignore blank lines
                continue
            if line.endswith(":"):
                # Retrieve tag

                # Remove : spaces and eol at the end of line
                clean_line = line.rstrip(": \n\r")
                # The tag starts at second position
                current_tag = "".join(clean_line.split()[1:]).strip()
            elif line.find('---') != -1:
                words = line.split('---')
                template = words[-1].strip()
                condition = ''.join(words[:-1])
                value = ""

                output_format['rules'].append({'field': current_tag,
                                               'value': condition,
                                               'template': template,
                                               })

            elif line.find(':') != -1:
                # Default case
                default = line.split(':')[1].strip()
                output_format['default'] = default

    except Exception, e:
        errors = get_msgs_for_code_list([("ERR_BIBFORMAT_CANNOT_READ_OUTPUT_FILE", filename, str(e))],
                                        stream='error', ln=CFG_SITE_LANG)
        register_errors(errors, 'error')

    # Cache and return
    format_outputs_cache[filename] = output_format
    return output_format

def get_output_format_attrs(code, verbose=0):
    """
    Returns the attributes of an output format.

    The attributes contain 'code', which is the short identifier of the output format
    (to be given as parameter in format_record function to specify the output format),
    'description', a description of the output format, 'visibility' the visibility of
    the format in the output format list on public pages and 'names', the localized names
    of the output format. If 'content_type' is specified then the search_engine will
    send a file with this content type and with result of formatting as content to the user.
    The 'names' dict always contais 'generic', 'ln' (for long name) and 'sn' (for short names)
    keys. 'generic' is the default name for output format. 'ln' and 'sn' contain long and short
    localized names of the output format. Only the languages for which a localization exist
    are used.

    {'names': {'generic':"a name", 'sn':{'en': "a name", 'fr':"un nom"}, 'ln':{'en':"a long name"}}
     'description': "a description"
     'code': "fnm1",
     'content_type': "application/ms-excel",
     'visibility': 1
    }

    @param code: the short identifier of the format
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings,
                                                       9: errors and warnings, stop if error (debug mode ))
    @return: strucured content of output format attributes
    """
    if code.endswith("."+CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION):
        code = code[:-(len(CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION) + 1)]
    attrs = {'names':{'generic':"",
                      'ln':{},
                      'sn':{}},
             'description':'',
             'code':code.upper(),
             'content_type':"",
             'visibility':1}

    filename = resolve_output_format_filename(code, verbose)
    if filename is None:
        return attrs

    attrs['names'] = bibformat_dblayer.get_output_format_names(code)
    attrs['description'] = bibformat_dblayer.get_output_format_description(code)
    attrs['content_type'] = bibformat_dblayer.get_output_format_content_type(code)
    attrs['visibility'] = bibformat_dblayer.get_output_format_visibility(code)

    return attrs

def get_output_formats(with_attributes=False):
    """
    Returns the list of all output format, as a dictionary with their filename as key

    If 'with_attributes' is true, also returns the names and description of the output formats,
    else 'attrs' is not returned in dicts (it might, if it has already been loaded previously).

    See get_output_format_attrs() to learn more on the attributes

    {'filename_1.bfo': {'rules': [ {'field': "980__a",
                                    'value': "PREPRINT",
                                    'template': "filename_a.bft",
                                   },
                                   {...}
                                 ],
                        'attrs': {'names': {'generic':"a name", 'sn':{'en': "a name", 'fr':"un nom"}, 'ln':{'en':"a long name"}}
                                  'description': "a description"
                                  'code': "fnm1"
                                 }
                        'default':"filename_b.bft"
                       },

     'filename_2.bfo': {...},
      ...
    }
    @return: the list of output formats
    """
    output_formats = {}
    files = os.listdir(CFG_BIBFORMAT_OUTPUTS_PATH)

    for filename in files:
        if filename.endswith("."+CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION):
            code = "".join(filename.split(".")[:-1])
            output_formats[filename] = get_output_format(code, with_attributes)

    return output_formats

def resolve_format_element_filename(string):
    """
    Returns the filename of element corresponding to string

    This is necessary since format templates code call
    elements by ignoring case, for eg. <BFE_AUTHOR> is the
    same as <BFE_author>.
    It is also recommended that format elements filenames are
    prefixed with bfe_ . We need to look for these too.

    The name of the element has to start with "BFE_".

    @param name: a name for a format element
    @return: the corresponding filename, with right case
    """

    if not string.endswith(".py"):
        name = string.replace(" ", "_").upper() +".PY"
    else:
        name = string.replace(" ", "_").upper()

    files = os.listdir(CFG_BIBFORMAT_ELEMENTS_PATH)
    for filename in files:
        test_filename = filename.replace(" ", "_").upper()

        if test_filename == name or \
        test_filename == "BFE_" + name or \
        "BFE_" + test_filename == name:
            return filename

    # No element with that name found
    # Do not log error, as it might be a normal execution case:
    # element can be in database
    return None

def resolve_output_format_filename(code, verbose=0):
    """
    Returns the filename of output corresponding to code

    This is necessary since output formats names are not case sensitive
    but most file systems are.

    @param code: the code for an output format
    @param verbose: the level of verbosity from 0 to 9 (O: silent,
                                                       5: errors,
                                                       7: errors and warnings,
                                                       9: errors and warnings, stop if error (debug mode ))
    @return: the corresponding filename, with right case, or None if not found
    """
    #Remove non alphanumeric chars (except . and _)
    code = re.sub(r"[^.0-9a-zA-Z_]", "", code)
    if not code.endswith("."+CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION):
        code = re.sub(r"\W", "", code)
        code += "."+CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION

    files = os.listdir(CFG_BIBFORMAT_OUTPUTS_PATH)
    for filename in files:
        if filename.upper() == code.upper():
            return filename

    # No output format with that name found
    errors = get_msgs_for_code_list([("ERR_BIBFORMAT_CANNOT_RESOLVE_OUTPUT_NAME", code)],
                                    stream='error', ln=CFG_SITE_LANG)
    if verbose == 0:
        register_errors(errors, 'error')
    elif verbose >= 5:
        sys.stderr.write(errors[0][1])
        if verbose >= 9:
            sys.exit(errors[0][1])
    return None

def get_fresh_format_template_filename(name):
    """
    Returns a new filename and name for template with given name.

    Used when writing a new template to a file, so that the name
    has no space, is unique in template directory

    Returns (unique_filename, modified_name)

    @param a: name for a format template
    @return: the corresponding filename, and modified name if necessary
    """
    #name = re.sub(r"\W", "", name) #Remove non alphanumeric chars
    name = name.replace(" ", "_")
    filename = name
    # Remove non alphanumeric chars (except .)
    filename = re.sub(r"[^.0-9a-zA-Z]", "", filename)
    path = CFG_BIBFORMAT_TEMPLATES_PATH + os.sep + filename \
           + "." + CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION
    index = 1
    while os.path.exists(path):
        index += 1
        filename = name + str(index)
        path = CFG_BIBFORMAT_TEMPLATES_PATH + os.sep + filename \
               + "." + CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION

    if index > 1:
        returned_name = (name + str(index)).replace("_", " ")
    else:
        returned_name = name.replace("_", " ")

    return (filename + "." + CFG_BIBFORMAT_FORMAT_TEMPLATE_EXTENSION,
            returned_name) #filename.replace("_", " "))

def get_fresh_output_format_filename(code):
    """
    Returns a new filename for output format with given code.

    Used when writing a new output format to a file, so that the code
    has no space, is unique in output format directory. The filename
    also need to be at most 6 chars long, as the convention is that
    filename == output format code (+ .extension)
    We return an uppercase code
    Returns (unique_filename, modified_code)

    @param code: the code of an output format
    @return: the corresponding filename, and modified code if necessary
    """
    #code = re.sub(r"\W", "", code) #Remove non alphanumeric chars
    code = code.upper().replace(" ", "_")
    # Remove non alphanumeric chars (except . and _)
    code = re.sub(r"[^.0-9a-zA-Z_]", "", code)
    if len(code) > 6:
        code = code[:6]

    filename = code
    path = CFG_BIBFORMAT_OUTPUTS_PATH + os.sep + filename \
           + "." + CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION
    index = 2
    while os.path.exists(path):
        filename = code + str(index)
        if len(filename) > 6:
            filename = code[:-(len(str(index)))]+str(index)
        index += 1
        path = CFG_BIBFORMAT_OUTPUTS_PATH + os.sep + filename \
               + "." + CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION
        # We should not try more than 99999... Well I don't see how we
        # could get there.. Sanity check.
        if index >= 99999:
            errors = get_msgs_for_code_list([("ERR_BIBFORMAT_NB_OUTPUTS_LIMIT_REACHED", code)],
                                            stream='error', ln=CFG_SITE_LANG)
            register_errors(errors, 'error')
            sys.exit("Output format cannot be named as %s"%code)

    return (filename + "." + CFG_BIBFORMAT_FORMAT_OUTPUT_EXTENSION, filename)

def clear_caches():
    """
    Clear the caches (Output Format, Format Templates and Format Elements)

    """
    global format_templates_cache, format_elements_cache, format_outputs_cache
    format_templates_cache = {}
    format_elements_cache = {}
    format_outputs_cache = {}

class BibFormatObject:
    """
    An object that encapsulates a record and associated methods, and that is given
    as parameter to all format elements 'format' function.
    The object is made specifically for a given formatting, i.e. it includes
    for example the language for the formatting.

    The object provides basic accessors to the record. For full access, one can get
    the record with get_record() and then use BibRecord methods on the returned object.
    """
    # The record
    record = None

    # The language in which the formatting has to be done
    lang = CFG_SITE_LANG

    # A list of string describing the context in which the record has
    # to be formatted.
    # It represents the words of the user request in web interface search
    search_pattern = []

    # The id of the record
    recID = 0

    # The information about the user, as returned by
    # 'webuser.collect_user_info(req)'
    user_info = None

    # The format in which the record is being formatted
    output_format = ''

    req = None # DEPRECATED: use bfo.user_info instead. Used by WebJournal.

    def __init__(self, recID, ln=CFG_SITE_LANG, search_pattern=None,
                 xml_record=None, user_info=None, output_format=''):
        """
        Creates a new bibformat object, with given record.

        You can either specify an record ID to format, or give its xml representation.
        if 'xml_record' is not None, use 'xml_record' instead of recID for the record.

        'user_info' allows to grant access to some functionalities on
        a page depending on the user's priviledges. It is a dictionary
        in the following form:
        user_info = {
            'remote_ip' : '',
            'remote_host' : '',
            'referer' : '',
            'uri' : '',
            'agent' : '',
            'uid' : -1,
            'nickname' : '',
            'email' : '',
            'group' : [],
            'guest' : '1'
        }

        @param recID: the id of a record
        @param ln: the language in which the record has to be formatted
        @param search_pattern: list of string representing the request used by the user in web interface
        @param xml_record: a xml string of the record to format
        @param user_info: the information of the user who will view the formatted page
        @param output_format: the output_format used for formatting this record
        """
        self.xml_record = None # *Must* remain empty if recid is given
        if xml_record is not None:
            # If record is given as parameter
            self.xml_record = xml_record
            self.record = create_record(xml_record)[0]
            recID = record_get_field_value(self.record, "001")

        self.lang = wash_language(ln)
        if search_pattern is None:
            search_pattern = []
        self.search_pattern = search_pattern
        self.recID = recID
        self.output_format = output_format
        self.user_info = user_info
        if self.user_info is None:
            self.user_info = collect_user_info(None)

    def get_record(self):
        """
        Returns the record structure of this BibFormatObject instance

        @return: the record structure as defined by BibRecord library
        """
        from invenio.search_engine import get_record

        # Create record if necessary
        if self.record is None:
            # on-the-fly creation if current output is xm
            self.record = get_record(self.recID)

        return self.record

    def control_field(self, tag, escape=0):
        """
        Returns the value of control field given by tag in record

        @param tag: the marc code of a field
        @param escape: 1 if returned value should be escaped. Else 0.
        @return: value of field tag in record
        """
        if self.get_record() is None:
            #Case where BibRecord could not parse object
            return ''

        p_tag = parse_tag(tag)
        field_value = record_get_field_value(self.get_record(),
                                             p_tag[0],
                                             p_tag[1],
                                             p_tag[2],
                                             p_tag[3])
        if escape == 0:
            return field_value
        else:
            return escape_field(field_value, escape)

    def field(self, tag, escape=0):
        """
        Returns the value of the field corresponding to tag in the
        current record.

        If the value does not exist, return empty string.  Else
        returns the same as bfo.fields(..)[0] (see docstring below).

        'escape' parameter allows to escape special characters
        of the field. The value of escape can be:
                      0 - no escaping
                      1 - escape all HTML characters
                      2 - remove unsafe HTML tags (Eg. keep <br />)
                      3 - Mix of mode 1 and 2. If value of field starts with
                          <!-- HTML -->, then use mode 2. Else use mode 1.
                      4 - Remove all HTML tags
                      5 - Same as 2, with more tags allowed (like <img>)
                      6 - Same as 3, with more tags allowed (like <img>)
                      7 - Mix of mode 0 and mode 1. If field_value
                          starts with <!--HTML-->, then use mode
                          0. Else use mode 1.

        @param tag: the marc code of a field
        @param escape: 1 if returned value should be escaped. Else 0. (see above for other modes)
        @return: value of field tag in record
        """
        list_of_fields = self.fields(tag)
        if len(list_of_fields) > 0:
            # Escaping below
            if escape == 0:
                return list_of_fields[0]
            else:
                return escape_field(list_of_fields[0], escape)
        else:
            return ""

    def fields(self, tag, escape=0, repeatable_subfields_p=False):
        """
        Returns the list of values corresonding to "tag".

        If tag has an undefined subcode (such as 999C5),
        the function returns a list of dictionaries, whoose keys
        are the subcodes and the values are the values of tag.subcode.
        If the tag has a subcode, simply returns list of values
        corresponding to tag.
        Eg. for given MARC:
            999C5 $a value_1a $b value_1b
            999C5 $b value_2b
            999C5 $b value_3b $b value_3b_bis

            >> bfo.fields('999C5b')
            >> ['value_1b', 'value_2b', 'value_3b', 'value_3b_bis']
            >> bfo.fields('999C5')
            >> [{'a':'value_1a', 'b':'value_1b'},
                {'b':'value_2b'},
                {'b':'value_3b'}]

        By default the function returns only one value for each
        subfield (that is it considers that repeatable subfields are
        not allowed). It is why in the above example 'value3b_bis' is
        not shown for bfo.fields('999C5').  (Note that it is not
        defined which of value_3b or value_3b_bis is returned).  This
        is to simplify the use of the function, as most of the time
        subfields are not repeatable (in that way we get a string
        instead of a list).  You can allow repeatable subfields by
        setting 'repeatable_subfields_p' parameter to True. In
        this mode, the above example would return:
            >> bfo.fields('999C5b', repeatable_subfields_p=True)
            >> ['value_1b', 'value_2b', 'value_3b']
            >> bfo.fields('999C5', repeatable_subfields_p=True)
            >> [{'a':['value_1a'], 'b':['value_1b']},
                {'b':['value_2b']},
                {'b':['value_3b', 'value3b_bis']}]
        NOTICE THAT THE RETURNED STRUCTURE IS DIFFERENT.  Also note
        that whatever the value of 'repeatable_subfields_p' is,
        bfo.fields('999C5b') always show all fields, even repeatable
        ones. This is because the parameter has no impact on the
        returned structure (it is always a list).

        'escape' parameter allows to escape special characters
        of the fields. The value of escape can be:
                      0 - no escaping
                      1 - escape all HTML characters
                      2 - remove unsafe HTML tags (Eg. keep <br />)
                      3 - Mix of mode 1 and 2. If value of field starts with
                          <!-- HTML -->, then use mode 2. Else use mode 1.
                      4 - Remove all HTML tags
                      5 - Same as 2, with more tags allowed (like <img>)
                      6 - Same as 3, with more tags allowed (like <img>)
                      7 - Mix of mode 0 and mode 1. If field_value
                          starts with <!--HTML-->, then use mode 0.
                          Else use mode 1.

        @param tag: the marc code of a field
        @param escape: 1 if returned values should be escaped. Else 0.
        @repeatable_subfields_p if True, returns the list of subfields in the dictionary
        @return: values of field tag in record
        """

        if self.get_record() is None:
            # Case where BibRecord could not parse object
            return []

        p_tag = parse_tag(tag)
        if p_tag[3] != "":
            # Subcode has been defined. Simply returns list of values
            values = record_get_field_values(self.get_record(),
                                             p_tag[0],
                                             p_tag[1],
                                             p_tag[2],
                                             p_tag[3])
            if escape == 0:
                return values
            else:
                return [escape_field(value, escape) for value in values]

        else:
            # Subcode is undefined. Returns list of dicts.
            # However it might be the case of a control field.

            instances = record_get_field_instances(self.get_record(),
                                                   p_tag[0],
                                                   p_tag[1],
                                                   p_tag[2])
            if repeatable_subfields_p:
                list_of_instances = []
                for instance in instances:
                    instance_dict = {}
                    for subfield in instance[0]:
                        if not instance_dict.has_key(subfield[0]):
                            instance_dict[subfield[0]] = []
                        if escape == 0:
                            instance_dict[subfield[0]].append(subfield[1])
                        else:
                            instance_dict[subfield[0]].append(escape_field(subfield[1], escape))
                    list_of_instances.append(instance_dict)
                return list_of_instances
            else:
                if escape == 0:
                    return [dict(instance[0]) for instance in instances]
                else:
                    return [dict([ (subfield[0], escape_field(subfield[1], escape)) \
                                   for subfield in instance[0] ]) \
                            for instance in instances]

    def kb(self, kb, string, default=""):
        """
        Returns the value of the "string" in the knowledge base "kb".

        If kb does not exist or string does not exist in kb,
        returns 'default' string or empty string if not specified.

        @param kb: a knowledge base name
        @param string: the string we want to translate
        @param default: a default value returned if 'string' not found in 'kb'
        """
        if string is None:
            return default

        val = get_kbr_values(kb, searchkey=string, searchtype='e')

        try:
            return val[0][0]
        except:
            return default

def escape_field(value, mode=0):
    """
    Utility function used to escape the value of a field in given mode.

    - mode 0: no escaping
    - mode 1: escaping all HTML/XML characters (escaped chars are shown as escaped)
    - mode 2: escaping unsafe HTML tags to avoid XSS, but
              keep basic one (such as <br />)
              Escaped tags are removed.
    - mode 3: mix of mode 1 and mode 2. If field_value starts with <!--HTML-->,
              then use mode 2. Else use mode 1.
    - mode 4: escaping all HTML/XML tags (escaped tags are removed)
    - mode 5: same as 2, but allows more tags, like <img>
    - mode 6: same as 3, but allows more tags, like <img>
    - mode 7: mix of mode 0 and mode 1. If field_value starts with <!--HTML-->,
              then use mode 0. Else use mode 1.
    """
    if mode == 1:
        return cgi.escape(value)
    elif mode in [2, 5]:
        allowed_attribute_whitelist = cfg_html_buffer_allowed_attribute_whitelist
        allowed_tag_whitelist = cfg_html_buffer_allowed_tag_whitelist + \
                                ('class',)
        if mode == 5:
            allowed_attribute_whitelist += ('src', 'alt',
                                            'width', 'height',
                                            'style', 'summary',
                                            'border', 'cellspacing',
                                            'cellpadding')
            allowed_tag_whitelist += ('img', 'table', 'td',
                                      'tr', 'th', 'span', 'caption')
        try:
            return washer.wash(value,
                               allowed_attribute_whitelist=\
                               allowed_attribute_whitelist,
                               allowed_tag_whitelist= \
                               allowed_tag_whitelist
                               )
        except HTMLParseError:
            # Parsing failed
            return cgi.escape(value)
    elif mode in [3, 6]:
        if value.lstrip(' \n').startswith(html_field):
            allowed_attribute_whitelist = cfg_html_buffer_allowed_attribute_whitelist
            allowed_tag_whitelist = cfg_html_buffer_allowed_tag_whitelist + \
                                    ('class',)
            if mode == 6:
                allowed_attribute_whitelist += ('src', 'alt',
                                                'width', 'height',
                                                'style', 'summary',
                                                'border', 'cellspacing',
                                                'cellpadding')
                allowed_tag_whitelist += ('img', 'table', 'td',
                                          'tr', 'th', 'span', 'caption')
            try:
                return washer.wash(value,
                                   allowed_attribute_whitelist=\
                                   allowed_attribute_whitelist,
                                   allowed_tag_whitelist=\
                                   allowed_tag_whitelist
                                   )
            except HTMLParseError:
                # Parsing failed
                return cgi.escape(value)
        else:
            return cgi.escape(value)
    elif mode == 4:
        try:
            return washer.wash(value,
                               allowed_attribute_whitelist=[],
                               allowed_tag_whitelist=[]
                               )
        except HTMLParseError:
            # Parsing failed
            return cgi.escape(value)
    elif mode == 7:
        if value.lstrip(' \n').startswith(html_field):
            return value
        else:
            return cgi.escape(value)
    else:
        return value

def bf_profile():
    """
    Runs a benchmark
    """
    for i in range(1, 51):
        format_record(i, "HD", ln=CFG_SITE_LANG, verbose=9, search_pattern=[])
    return

if __name__ == "__main__":
    import profile
    import pstats
    #bf_profile()
    profile.run('bf_profile()', "bibformat_profile")
    p = pstats.Stats("bibformat_profile")
    p.strip_dirs().sort_stats("cumulative").print_stats()

