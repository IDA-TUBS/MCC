import logging
from mcc.graph import *

class Registry:
    def __init__(self):
        self.by_order = list()
        self.by_name  = dict()

    def add_layer(self, layer):
        self.by_order.append(layer)
        self.by_name[layer.name] = layer

class Layer:
    def __init__(self, name):
        self.graph = Graph()
        self.name = name

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

        if param not in params['params']:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['candidates'] = candidates

    def get_param_value(self, param, obj):
        params = self._get_params(obj)

        if param in params:
            return params[param]['value']
        else:
            return set()

    def set_param_value(self, param, obj, value):
        params = self._get_params(obj)

        if param not in params['params']:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['value'] = value

class AnalysisEngine:
    def __init__(self):
        return

    def map(self, source):
        raise Exception("not implemented")

    def assign(self, source):
        raise Exception("not implemented")

    def transform(self, source):
        raise Exception("not implemented")

    def check(self):
        raise Exception("not implemented")

class Operation:
    def __init__(self, source_type=object):
        self.source_type = source_type
        self.analysis_engines = list()

    def register_ae(self, ae):
        self.analysis_engines.append(ae)

    def execute(self, iterable, layer):
        raise Exception("not implemented")

class Map(Operation):
    def __init__(self, param, source_type=object, target_type=object):
        Operation.__init__(self, source_type)
        self.target_type = target_type
        self.param = param

    def execute(self, iteratable, layer):

        for obj in iteratable:
            assert(isinstance(obj, self.source_type))
            candidates = set()
            first = True
            for ae in self.analysis_engines:
                if first:
                    candidates = ae.map(obj)
                else:
                    # build intersection of candidates for all analyses
                    candidates &= ae.map(obj)

            # TODO (?) check target type
            # TODO (?) we may need to iterate over this multiple times

            # update candidates for this parameter in layer object
            layer.set_param_candidates(self.param, obj, candidates)

        return True

class Assign(Operation):
    def __init__(self, param, source_type=object, target_type=object):
        Operation.__init__(self)
        Operation.__init__(self, source_type)
        self.target_type = target_type
        self.param = param

    def register_ae(self, ae):
        # only one analysis engine can be registered
        assert len(self.analysis_engines) == 0
        Operation.register_ae(ae)

    def execute(self, iterable, layer):

        for obj in iteratable:
            assert(isinstance(obj, self.source_type))

            result = self.analysis_engines[0].assign(obj)
            assert(isinstance(result, self.target_type))

            layer.set_param_value(self.param, obj, result)

        return True

class Transform(Operation):
    def __init__(self, source_type=object, target_type=object):
        Operation.__init__(self)
        Operation.__init__(self, source_type)
        self.target_type = target_type

    def register_ae(self, ae):
        # only one analysis engine can be registered
        assert len(self.analysis_engines) == 0
        Operation.register_ae(ae)

    def execute(self, iterable, layer):
        # TODO implement
        raise Exception("not implemented")

class Check(Operation):
    def __init__(self):
        Operation.__init__(self)

    def execute(self, iterable, layer):
        for ae in self.analysis_engines:
            if not ae.check():
                return False

        return True

class Step:
    def __init__(self, layer):
        self.operations = list()
        self.layer = layer

    def add_operation(self, op):
        assert(isinstance(op, Operation))
        self.operations.append(op)

class NodeStep(Step):
    def execute(self):
        for op in self.operations:
            if not op.execute(self.layer.graph.nodes(), self.layer):
                return False

        return True

class EdgeStep(Step):
    def execute(self):
        for op in self.operations:
            if not op.execute(self.layer.graph.edges(), self.layer):
                return False

        return True
