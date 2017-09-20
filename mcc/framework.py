import logging
from mcc.graph import *

class Registry:
    def __init__(self):
        self.by_order = list()
        self.by_name  = dict()

    def add_layer(self, layer):
        self.by_order.append(layer)
        self.by_name[layer.name] = layer

    def reset(self, layer=None):
        # clear all layers from 'layer' and below
        if layer is None:
            start = 0
        else:
            start = self.by_order.index(layer)

        for i in range(start, len(self.by_order)):
            self.by_order[i].clear()

class Layer:
    def __init__(self, name, nodetype=object):
        self.graph = Graph()
        self.name = name
        self.nodetype = nodetype

    def clear(self):
        self.graph = Graph()

    def _get_params(self, obj):
        if isinstance(obj, Edge):
            # obj is an edge
            attributes = self.graph.edge_attributes(obj)
        else:
            # obj is a node
            attributes = self.graph.node_attributes(obj)

        if 'params' not in attributes:
            attributes['params'] = dict()

        return attributes['params']

    def get_param_candidates(self, param, obj):
        params = self._get_params(obj)

        if param in params:
            return params[param]['candidates']
        else:
            return set()

    def set_param_candidates(self, param, obj, candidates):
        params = self._get_params(obj)

        if param not in params:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['candidates'] = candidates

    def get_param_value(self, param, obj):
        params = self._get_params(obj)

        if param in params:
            return params[param]['value']
        else:
            return None

    def set_param_value(self, param, obj, value):
        params = self._get_params(obj)

        if param not in params:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['value'] = value

class AnalysisEngine:
    def __init__(self, layer, param):
        self.layer = layer
        self.param = param

    def map(self, source):
        raise Exception("not implemented")

    def assign(self, source):
        raise Exception("not implemented")

    def transform(self, source):
        raise Exception("not implemented")

    def check(self, obj):
        raise Exception("not implemented")

    def source_types(self):
        return set([object])

    def target_type(self):
        return object

class Operation:
    def __init__(self, ae):
        self.analysis_engines = [ae]
        self.param = ae.param
        self.layer = ae.layer

    def register_ae(self, ae):
        assert(ae.param == self.param)
        self.analysis_engines.append(ae)
        return ae

    def check_source_type(self, obj):
        for ae in self.analysis_engines:
            for t in ae.source_types():
                if not isinstance(obj, t):
                    return False

        return True

    def execute(self, iterable):
        raise Exception("not implemented")

class Map(Operation):
    def __init__(self, ae):
        Operation.__init__(self, ae)

    def execute(self, iterable):

        for obj in iterable:
            assert(self.check_source_type(obj))

            candidates = set()
            first = True
            for ae in self.analysis_engines:

                if first:
                    candidates = ae.map(obj)
                else:
                    # build intersection of candidates for all analyses
                    candidates &= ae.map(obj)

                for c in candidates:
                    assert(isinstance(c, ae.target_type()))

            # TODO (?) check target type
            # TODO (?) we may need to iterate over this multiple times

            # update candidates for this parameter in layer object
            self.layer.set_param_candidates(self.param, obj, candidates)

        return True

class Assign(Operation):
    def __init__(self, ae):
        Operation.__init__(self, ae)

    def register_ae(self, ae):
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable):

        for obj in iterable:
            assert(self.check_source_type(obj))

            candidates = self.layer.get_param_candidates(self.param, obj)
            result = self.analysis_engines[0].assign(obj, candidates)
            assert(result in candidates)
            assert(isinstance(result, self.analysis_engines[0].target_type()))

            self.layer.set_param_value(self.param, obj, result)

        return True

class Transform(Operation):
    def __init__(self, ae):
        Operation.__init__(self, ae)

    def register_ae(self, ae):
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable, layer):
        # TODO implement
        raise Exception("not implemented")

class Check(Operation):
    def __init__(self, ae):
        Operation.__init__(self, ae)

    def execute(self, iterable):
        for ae in self.analysis_engines:
            for obj in iterable:
                assert(self.check_source_type(obj))

                if not ae.check(obj):
                    return False

        return True

class Step:
    def __init__(self, op):
        assert(isinstance(op, Operation))
        self.operations = [op]
        self.layer = op.layer

    def add_operation(self, op):
        assert(isinstance(op, Operation))
        self.operations.append(op)
        return op

class NodeStep(Step):
    def execute(self):
        for op in self.operations:
            if not op.execute(self.layer.graph.nodes()):
                return False

        return True

class EdgeStep(Step):
    def execute(self):
        for op in self.operations:
            if not op.execute(self.layer.graph.edges()):
                return False

        return True
