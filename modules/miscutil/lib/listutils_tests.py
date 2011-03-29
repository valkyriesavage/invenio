# -*- coding: utf-8 -*-
##
## This file is part of Invenio.
## Copyright (C) 2008, 2009, 2010, 2011 CERN.
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

"""Unit tests for the listutils library."""

__revision__ = "$Id$"

import unittest

from invenio.listutils import ziplist

from invenio.testutils import make_test_suite, run_test_suite

class ZiplistTest(unittest.TestCase):
    """Test functions related to ziplist"""
    def test_ziplist(self):
        """listutils - ziplist"""
        self.assertEqual(ziplist(['f1', 'f2', 'f3'], ['p1', 'p2', 'p3'], ['op1', 'op2', '']),\
                         [['f1', 'p1', 'op1'], ['f2', 'p2', 'op2'], ['f3', 'p3', '']])

TEST_SUITE = make_test_suite(ZiplistTest)

if __name__ == "__main__":
    run_test_suite(TEST_SUITE)
