"""
Description
-----------

Implements XML parser classes for the component repository.

:Authors:
    - Johannes Schlatow

"""

from mcc.graph import Edge

class Task:
    def __init__(self, name, wcet, bcet, thread=None):
        self.name = name
        self.wcet = wcet
        self.bcet = bcet
        self.thread = thread

        self.junctiontype = None

        self.activation_period = 0
        self.activation_jitter = 0

    def set_placeholder_in(self, expect)
        assert expect == 'junction' or
               expect == 'receiver' or
               expect == 'server' or
               expect == 'client'

        self.expect_in = expect

    def set_placeholder_out(self, expect)
        assert expect == 'junction' or
               expect == 'receiver' or
               expect == 'server'

        self.expect_out = expect

class Tasklink(Edge):
    def __init__(self, source, target, linktype='signal'):
        assert linktype == 'signal' or linktype == 'call'
        self.linktype = linktype
        Edge.__init__(source, target)

class Placeholder:
    def __init__(self, expect='server'):
        assert expect == 'junction' or
               expect == 'receiver' or
               expect == 'server' or
               expect == 'client'

        self.expect = expect
