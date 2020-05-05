"""
:Authors:
    - Edgard Schmidt

"""

from collections import namedtuple
import re

Clause = namedtuple('ParamClause', 'name type value')

class SyntaxError(Exception): pass

_delimiter = ' '
_part_delimiter = ':'

def has_clause(text):
    return -1 != text.find(_part_delimiter)

def parse(text):
    for clause_string in filter(len, text.split(_delimiter)):
        parts = clause_string.split(_part_delimiter)
        if 3 != len(parts):
            raise SyntaxError
        checkers = [re.compile(p).search for p in parts]
        yield Clause(*checkers)
