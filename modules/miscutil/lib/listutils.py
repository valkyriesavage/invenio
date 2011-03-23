# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) 2010, 2011 CERN.
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

""" This function provides utilites for working with lists. """

def ziplist(*lists):
    """Just like zip(), but returns lists of lists instead of lists of tuples

    Example:
    zip([f1, f2, f3], [p1, p2, p3], [op1, op2, '']) =>
       [(f1, p1, op1), (f2, p2, op2), (f3, p3, '')]
    ziplist([f1, f2, f3], [p1, p2, p3], [op1, op2, '']) =>
       [[f1, p1, op1], [f2, p2, op2], [f3, p3, '']]
    """
    def l(*items):
        return list(items)
    return map(l, *lists)
