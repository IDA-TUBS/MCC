"""
Description
-----------

Implements dummy classes from parser with parser functionality stripped off

:Authors:
    - Johannes Schlatow

"""

import logging

class PlatformParser:
    class PfComponent:
        def name(self):
            return self._name

        def __setstate__(self, state):
            self._name = state

class ChildQuery:
    def identifier(self):
        return self._identifier

    def label(self):
        if self._identifier is not None:
            return self._identifier
        else:
            return self._queryname

    def query(self):
        return self._queryname

    def type(self):
        return self._type

    def __repr__(self):
        return self.label()

    def __setstate__(self, state):
        self._type, self._identifier, self._queryname = state
