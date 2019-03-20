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

    def set_placeholder_in(self, expect, **kwargs):
        assert expect == 'sender' or \
               expect == 'junction' or \
               expect == 'server' or \
               expect == 'client' or
               expect is None

        self.expect_in      = expect
        self.expect_in_args = kwargs

    def set_placeholder_out(self, expect, **kwargs):
        assert expect == 'junction' or \
               expect == 'receiver' or \
               expect == 'server' or expect is None

        self.expect_out      = expect
        self.expect_out_args = kwargs

class Tasklink(Edge):
    def __init__(self, source, target, linktype='signal'):
        assert linktype == 'signal' or linktype == 'call'
        self.linktype = linktype
        Edge.__init__(source, target)

class Placeholder:
    def __init__(self, expect='server'):
        assert expect == 'junction' or \
               expect == 'receiver' or \
               expect == 'server' or \
               expect == 'client'

        self.expect = expect
