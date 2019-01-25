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

class Repository:
    class ElementWrapper:
        def xml(self):
            return self._xml

        def __setstate__(self, state):
            self._xml = state

    class Service:
        def max_clients(self):
            return self._max_clients

        def label(self):
            return self._label

        def function(self):
            return self._function

        def name(self):
            return self._name

        def ref(self):
            return self._ref

        def __setstate__(self, state):
            self._function, self._name, self._label, self._ref, self._max_clients =  state

    class Component:
        def label(self):
            return self._label

        def unique_label(self):
            return self._unique_label

        def __setstate__(self, state):
            self._label, self._unique_label = state

    class ComponentPattern:
        def label(self):
            return self._label

        def __setstate__(self, state):
            self._label = state


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
