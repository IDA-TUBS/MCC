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
               expect == 'client' or \
               expect == 'interrupt' or \
               expect is None

        self.expect_in      = expect
        self.expect_in_args = kwargs

    def set_placeholder_out(self, expect, **kwargs):
        assert expect == 'junction' or \
               expect == 'receiver' or \
               expect == 'server' or expect is None

        self.expect_out      = expect
        self.expect_out_args = kwargs

    def label(self):
        return self.name

    def __repr__(self):
        ttype = "Task"
        if self.junctiontype is not None:
            ttype = "%s-Junction" % self.junctiontype

        return "%s '%s'" % (ttype, self.name)

    def viewer_properties(self):
        props =  { 'name' : self.name,
                 'WCET' : self.wcet,
                 'BCET' : self.bcet }

        if self.junctiontype is not None:
            props['Thread'] = self.thread

        if self.activation_period > 0:
            props['P'] = self.activation_period

        if self.activation_jitter > 0:
            props['P'] = self.activation_jitter

        if self.expect_in is not None:
            props['Input'] = '%s %s' % (self.expect_in, self.expect_in_args)

        if self.expect_out is not None:
            props['Output'] = '%s %s' % (self.expect_out, self.expect_out_args)

        return props


class Tasklink(Edge):
    def __init__(self, source, target, linktype='signal'):
        assert linktype == 'signal' or linktype == 'call'
        self.linktype = linktype
        Edge.__init__(source, target)

    def __repr__(self):
        if self.linktype == 'call':
            return "%s calls %s" % (self.source, self.target)
        else:
            return "%s -> %s" % (self.source, self.target)
