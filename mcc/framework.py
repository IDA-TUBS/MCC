import logging
from mcc.graph import *

class Registry:
    def __init__(self):
        self.by_order  = list()
        self.by_name   = dict()
        self.steps     = list()

    @staticmethod
    def same_layers(step1, step2):
        if step1 == None or step2 == None:
            return False
        return step1.target_layer == step2.target_layer

    def previous_step(self, step):
        idx = self.steps.index(step)
        if idx == 0:
            return None
        else:
            return self.steps[idx-1]

    def add_layer(self, layer):
        self.by_order.append(layer)
        self.by_name[layer.name] = layer

    def next_layer(self, layer):
        current_layer = self.by_name[layer.name]
        idx = self.by_order.index(current_layer)
        if len(self.by_order) > idx+1:
            return self.by_order[idx+1]
        else:
            return None

    def reset(self, layer=None):
        # clear all layers from 'layer' and below
        if layer is None:
            start = 0
        else:
            start = self.by_order.index(layer)

        for i in range(start, len(self.by_order)):
            self.by_order[i].clear()

    def add_step(self, step):
        # perform sanity checks (step's layers are correct, etc.)
        if len(self.steps) > 0:
            if not Registry.same_layers(self.steps[-1], step):
                self.print_steps()
                print(step)
                assert(step.target_layer == self.next_layer(self.steps[-1].target_layer))
        else:
            assert(step.target_layer == self.by_order[0])

        self.steps.append(step)

    def write_dot(self, filename):
        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")
            dotfile.write("  compound=true;\n")

            # create a node for each layer
            i = 1
            layer_node_names = dict()
            dotfile.write('subgraph layers {\n')
            for layer in self.by_order:
                layer_node_names[layer] = 'l%d' % i
                dotfile.write('%s [label="%s",shape=parallelogram,colorscheme=set39,fillcolor=5,style=filled];\n' % 
                        (layer_node_names[layer],layer.name))

                # connect to previous layer
                if i > 1:
                    dotfile.write('%s -> %s [arrowhead=normal,style=solid,colorscheme=set39,color=5];\n' %
                            (layer_node_names[self.by_order[i-2]],layer_node_names[layer]))
                i += 1
            dotfile.write('}\n')

            # aggregate analysis engines
            aengines = set()
            for step in self.steps:
                for op in step.operations:
                    aengines.update(op.analysis_engines)

            # create a node for each analysis engine
            i = 1
            ae_node_names = dict()
            for ae in aengines:
                ae_node_names[ae] = 'ae%d' % i
                htmllabel = '<%s <br />%s>' % (ae, ae.acl_string(newline='<br />'))
                dotfile.write('%s [label=%s,shape=octagon,colorscheme=set39,fillcolor=4,style=filled];\n' % 
                        (ae_node_names[ae],htmllabel))
                i += 1

            # create subgraph for each step
            i = 1
            j = 1
            step_node_names = dict()
            op_node_names = dict()
            for step in self.steps:
                step_node_names[step] = 'cluster%d' % i
                dotfile.write('subgraph %s {\n' % step_node_names[step])
                dotfile.write('label="%d. %s";\n' % (i, type(step).__name__))
                dotfile.write('shape=rectangle;\n')
                dotfile.write('colorscheme=set39;\n')
                dotfile.write('fillcolor=2;\n')
                dotfile.write('style=filled;\n')

                prevop = None
                for op in step.operations:
                    op_node_names[op] = 'op%d' % j
                    dotfile.write('%s [label="%s(%s)",shape=trapezium,colorscheme=set39,fillcolor=6,style=filled];\n' %
                            (op_node_names[op], type(op).__name__, op.name))

                    # connect to previous operation
                    if prevop is not None:
                        dotfile.write('%s -> %s [arrowhead=normal,style=solid,colorscheme=set39,color=6];\n' % 
                                (op_node_names[prevop], op_node_names[op]))
                    prevop = op
                    j += 1

                dotfile.write('}\n')

                # connect to previous step
                if i > 1:
                    prevstep = self.steps[i-2]
                    dotfile.write('%s -> %s [minlen=2,ltail=%s,lhead=%s,arrowhead=normal,style=solid,colorscheme=set39,color=1];\n' % 
                            (op_node_names[prevstep.operations[-1]],
                             op_node_names[step.operations[0]],
                             step_node_names[prevstep],
                             step_node_names[step]))

                # connect to layers
                dotfile.write('%s -> %s [lhead=%s,arrowhead=normal,style=dashed,colorscheme=set39,color=1];\n' %
                        (layer_node_names[step.source_layer],
                         op_node_names[step.operations[0]],
                         step_node_names[step]))
                dotfile.write('%s -> %s [ltail=%s,arrowhead=normal,style=dashed,colorscheme=set39,color=1];\n' %
                        (op_node_names[step.operations[-1]],
                         layer_node_names[step.target_layer],
                         step_node_names[step]))

                i += 1

            for step in self.steps:
                for op in step.operations:
                    # connect to analysis engines
                    k = 1
                    for ae in op.analysis_engines:
                        label = ''
                        if len(op.analysis_engines) > 1:
                            label = 'label="%d",' % k

                        dotfile.write('%s -> %s [%sarrowhead=none,style=dashed,colorscheme=set39,color=4];\n' %
                                (ae_node_names[ae], op_node_names[op], label))
                        k += 1

            dotfile.write("}\n")

    def print_steps(self):
        print()
        for step in self.steps:
            if not Registry.same_layers(self.previous_step(step), step):
                print("[%s]" % step.target_layer)
            print("  %s" % step)

    def print_engines(self):
        aengines = set()
        for step in self.steps:
            for op in step.operations:
                aengines.update(op.analysis_engines)

        print()
        for ae in aengines:
            print('[%s]' % type(ae).__name__)
            print(ae.acl_string())

    def execute(self):
        print()
        for step in self.steps:
            previous_step = self.previous_step(step)
            if not Registry.same_layers(previous_step, step):
                logging.info("Creating layer %s" % step.target_layer)
                if previous_step is not None:
                    self._output_layer(previous_step.target_layer)

            try:
                step.execute()
            except Exception as ex:
                self._output_layer(step.target_layer, suffix='-error')
                raise(ex)

        self._output_layer(self.steps[-1].target_layer)

    def _output_layer(self, layer, suffix):
        raise NotImplementedError()

class Layer:
    def __init__(self, name, nodetype=object):
        self.graph = Graph()
        self.name = name
        self.nodetype = nodetype

    def __str__(self):
        return self.name

    def clear(self):
        self.graph = Graph()

    def _set_params(self, obj, params):
        for name, value in params.items():
            self._set_param_value(name, obj, value)

    def insert_obj(self, obj, nodes_only=False):
        inserted = set()

        if isinstance(obj, Edge):
            if not nodes_only:
                inserted.add(self.graph.add_edge(obj))
        elif isinstance(obj, Graph):
            raise NotImplementedError()
        elif isinstance(obj, set) or isinstance(obj, list):

            # first add all nodes and remember edges
            edges = set()
            for o in obj:
                tmp = self.insert_obj(o, nodes_only=True)
                if len(tmp) == 0:
                    edges.add(o)
                else:
                    inserted.update(tmp)

            # now we add the remaining edges
            for o in edges:
                inserted.update(self.insert_obj(o, nodes_only=False))

            assert(len(obj) == len(inserted))
        elif isinstance(obj, GraphObj):
            if obj.is_edge():
                if not nodes_only:
                    o = self.graph.add_edge(obj.obj)
                    self._set_params(o, obj.params())
                    inserted.add(o)
            else:
                o = self.graph.add_node(obj.obj)
                self._set_params(o, obj.params())
                inserted.add(o)
        else:
            inserted.add(self.graph.add_node(obj))

        return inserted

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

    def get_param_candidates(self, ae, param, obj):
        assert(ae.check_acl(self, param, 'reads'))

        params = self._get_params(obj)

        if param in params:
            return params[param]['candidates']
        else:
            return set()

    def set_param_candidates(self, ae, param, obj, candidates):
        assert(ae.check_acl(self, param, 'writes'))
        self._set_param_candidates(param, obj, candidates)

    def _set_param_candidates(self, param, obj, candidates):
        params = self._get_params(obj)

        if param not in params:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['candidates'] = candidates

    def get_param_value(self, ae, param, obj):
        assert(ae.check_acl(self, param, 'reads'))
        return self._get_param_value(param, obj)

    def _get_param_value(self, param, obj):
        params = self._get_params(obj)

        if param in params:
            return params[param]['value']
        else:
            return None

    def set_param_value(self, ae, param, obj, value):
        assert(ae.check_acl(self, param, 'writes'))
        self._set_param_value(param, obj, value)

    def _set_param_value(self, param, obj, value):
        params = self._get_params(obj)

        if param not in params:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['value'] = value

class AnalysisEngine:
    # TODO implement check of supported layers, node types, edge types, etc.

    def __init__(self, layer, param, name=None, acl=None):
        self.layer = layer
        self.param = param
        self.name = name
        if self.name is None:
            self.name = type(self).__name__

        if acl is None:
            acl = dict()

        if layer not in acl:
            acl[layer] = dict()

        if 'writes' not in acl[layer]:
            acl[layer]['writes'] = set()

        if 'reads' not in acl[layer]:
            acl[layer]['reads'] = set()

        acl[layer]['writes'].add(param)
        acl[layer]['reads'].add(param)

        self.acl = acl

    def __str__(self):
        return '%s(%s.%s)' % (self.name, self.layer, self.param)

    def acl_string(self, newline='\n'):
        result = ''
        for layer in self.acl:
            result += '[%s]%s' % (layer, newline)
            for access, params in self.acl[layer].items():
                result += '  %s: %s%s' % (access, ','.join([str(p) for p in params]), newline)
        return result

    def check_acl(self, layer, param, access):
        if layer not in self.acl:
            logging.critical('%s has no access to layer "%s".' % (type(self).__name__, layer))
            logging.info('Requested: %s(%s.%s)' % (access, layer, param))
            logging.info('ACL is:\n%s' % self.acl_string())
            return False

        if access not in self.acl[layer]:
            logging.critical('%s has no read access to layer "%s".' % (type(self).__name__, layer))
            logging.info('Requested: %s(%s.%s)' % (access, layer, param))
            logging.info('ACL is:\n%s' % self.acl_string())
            return False

        if param in self.acl[layer][access]:
            return True

        logging.critical('%s has no read access to "%s" of layer "%s".' % (type(self).__name__, param, layer))
        logging.info('ACL is:\n%s' % self.acl_string())
        return False

    def map(self, source, candidates=None):
        raise NotImplementedError()

    def assign(self, source, candidates):
        raise NotImplementedError()

    def transform(self, source, target_layer):
        raise NotImplementedError()

    def check(self, obj):
        raise NotImplementedError()

    def source_types(self):
        return set([object])

    def target_type(self):
        return object

class DummyEngine(AnalysisEngine):
    """ Can be used for identity-tranformation.
    """
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, None)

    def transform(self, obj, target_layer):
        if isinstance(obj, Edge):
            assert(obj.source in target_layer.graph.nodes())
            assert(obj.target in target_layer.graph.nodes())

        return obj

    def check(self, obj):
        return True

    def target_type(self):
        return self.layer.nodetype

class CopyEngine(AnalysisEngine):
    """ Copies 'source_param' from 'source_layer' to 'param' of 'layer'.
    """
    def __init__(self, layer, param, source_layer, source_param=None):
        if source_param is None:
            source_param = param
        acl = { layer        : {'reads' : set([source_layer.name])},
                source_layer : {'reads' : set([layer.name, source_param])}}

        AnalysisEngine.__init__(self, layer, param, acl=acl)
        self.source_layer = source_layer
        self.source_param = source_param

    def map(self, obj, candidates):
        src_obj = self.layer.get_param_value(self, self.source_layer.name, obj)
        return set([self.source_layer.get_param_value(self, self.source_param, src_obj)])

    def assign(self, obj, candidates):
        return list(candidates)[0]

class InheritEngine(AnalysisEngine):
    """ Inherits 'param' from source nodes (out=False) or target nodes (out=True).
    """
    def __init__(self, layer, param, out=False):
        AnalysisEngine.__init__(self, layer, param)
        self.out=out

    def map(self, obj, candidates):
        if self.out:
            edges = self.layer.graph.out_edges(obj)
        else:
            edges = self.layer.graph.in_edges(obj)

        if len(edges) == 0:
            return candidates

        candidates = set()

        for e in edges:
            candidates.add(self.layer.get_param_value(self, self.param, e.target if self.out else e.source))

        if len(candidates) > 1:
            logging.error("Cannot inherit '%s' from %s node unambiguously" 
                    % (self.param, 'target' if self.out else 'source'))
            return set([None])
        elif len(candidates) == 0:
            logging.warning("No value for param '%s' for node %s\'s %s nodes." % 
                    (self.param, obj, 'target' if self.out else 'source'))

        return candidates

    def assign(self, obj, candidates):
        return list(candidates)[0]

class Operation:
    def __init__(self, ae, name=''):
        self.param = ae.param
        self.source_layer = ae.layer
        self.target_layer = ae.layer
        if hasattr(ae, 'target_layer'):
            self.target_layer = ae.target_layer

        self.name = name

        self._check_ae_compatible(ae)
        self.analysis_engines = [ae]

    def _check_ae_compatible(self, ae):
        if ae.param != self.param:
            raise Exception("Cannot register analysis engines because of incompatible parameters (%s != %s)" %
                    (ae.param, self.param))
        if ae.layer != self.source_layer:
            raise Exception("Cannot register analysis engines because of incompatible source layer (%s != %s)" %
                    (ae.layer, self.source_layer))

        # check types
        found = False
        for t in ae.source_types():
            if issubclass(self.source_layer.nodetype, t):
                found = True
                break

        if not found:
            raise Exception("Analysis engine %s does not support nodetype %s of source layer" % (ae,
                self.source_layer.nodetype))

    def register_ae(self, ae):
        self._check_ae_compatible(ae)
        self.analysis_engines.append(ae)
        return ae

    def check_source_type(self, obj):
        for ae in self.analysis_engines:
            for t in ae.source_types():
                if isinstance(obj, t):
                    return True

        return False

    def execute(self, iterable):
        raise NotImplementedError()

    def __repr__(self):
        return "%s(%s) [%s]" % (type(self).__name__, self.name, ','.join([str(ae) for ae in self.analysis_engines]))

class Map(Operation):
    def __init__(self, ae, name=''):
        Operation.__init__(self, ae, name)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        for obj in iterable:
            assert(self.check_source_type(obj))

            candidates = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)
            if len(candidates) == 0:
                candidates = None

            for ae in self.analysis_engines:

                if candidates is None:
                    candidates = ae.map(obj, None)
                else:
                    # build intersection of candidates for all analyses
                    new_candidates = ae.map(obj, set(candidates))
                    if new_candidates is not None:
                        candidates &= new_candidates

            # update candidates for this parameter in layer object
            assert(candidates is not None)
            self.source_layer.set_param_candidates(self.analysis_engines[0], self.param, obj, candidates)

        return True

class Assign(Operation):
    def __init__(self, ae, name=''):
        Operation.__init__(self, ae, name)

    def register_ae(self, ae):
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        for obj in iterable:
            assert(self.check_source_type(obj))

            candidates = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)
            if len(candidates) == 0:
                logging.error("No candidates left for param '%s'." % self.param)

            result = self.analysis_engines[0].assign(obj, candidates)
            if isinstance(result, list) or isinstance(result, set):
                for r in result:
                    assert(r in candidates)
            else:
                assert(result in candidates)

            self.source_layer.set_param_value(self.analysis_engines[0], self.param, obj, result)

        return True

class Transform(Operation):
    def __init__(self, ae, target_layer, name=''):
        Operation.__init__(self, ae, name)
        self.target_layer = target_layer
        self.source_layer = ae.layer

    def _check_ae_compatible(self, ae):
        Operation._check_ae_compatible(self, ae)

        if not issubclass(ae.target_type(), self.target_layer.nodetype):
            raise Exception("Analysis engine %s does not have nodetype %s of target layer" % (ae,
                self.target_layer.nodetype))

    def register_ae(self, ae):
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        for obj in iterable:
            # TODO shall we also return the existing objects (for comp_inst)?
            new_objs = self.analysis_engines[0].transform(obj, self.target_layer)
            assert new_objs, "transform() did not return any object"
            inserted = self.target_layer.insert_obj(new_objs)
            assert len(inserted) > 0
            self.source_layer._set_param_value(self.target_layer.name, obj, inserted)
            for o in inserted:
                self.target_layer._set_param_value(self.source_layer.name, o, obj)

        return True

class Check(Operation):
    def __init__(self, ae, name=''):
        Operation.__init__(self, ae, name)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

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
        self.source_layer = op.source_layer
        self.target_layer = op.target_layer

    def add_operation(self, op):
        assert(isinstance(op, Operation))
        assert(op.source_layer == self.source_layer)
        if self.source_layer == self.target_layer:
            self.target_layer = op.target_layer
        else:
            assert(op.target_layer == self.target_layer)
        self.operations.append(op)
        return op

    def __repr__(self):
        return type(self).__name__ + ': \n    ' + '\n    '.join([str(op) for op in self.operations])

class NodeStep(Step):
    def execute(self):
        for op in self.operations:
            if not op.execute(self.source_layer.graph.nodes()):
                raise Exception("NodeStep failed during '%s' on layer '%s'" % (op, self.source_layer.name))
                return False

        return True

class EdgeStep(Step):
    def execute(self):
        for op in self.operations:
            if not op.execute(self.source_layer.graph.edges()):
                raise Exception("EdgeStep failed during %s on layer '%s'" % (op, self.source_layer.name))
                return False

        return True

class CopyNodeTransform(Transform):
    def __init__(self, layer, target_layer):
        Transform.__init__(self, DummyEngine(layer), target_layer)

class CopyEdgeTransform(Transform):
    def __init__(self, layer, target_layer):
        Transform.__init__(self, DummyEngine(layer), target_layer)

class CopyNodeStep(NodeStep):
    def __init__(self, layer, target_layer):
        NodeStep.__init__(self, CopyNodeTransform(layer, target_layer))

class CopyEdgeStep(EdgeStep):
    def __init__(self, layer, target_layer):
        EdgeStep.__init__(self, CopyEdgeTransform(layer, target_layer))

class CopyMappingStep(NodeStep):
    def __init__(self, layer, target_layer):
        ce = CopyEngine(target_layer, 'mapping', layer)
        NodeStep.__init__(self, Map(ce))
        self.add_operation(Assign(ce))

class CopyServiceStep(EdgeStep):
    def __init__(self, layer, target_layer):
        ce = CopyEngine(target_layer, 'service', layer)
        EdgeStep.__init__(self, Map(ce))
        self.add_operation(Assign(ce))

class InheritFromSourceStep(NodeStep):
    def __init__(self, layer, param):
        ie = InheritEngine(layer, param, out=False)
        NodeStep.__init__(self, Map(ie))
        self.add_operation(Assign(ie))

class InheritFromTargetStep(NodeStep):
    def __init__(self, layer, param):
        ie = InheritEngine(layer, param, out=True)
        NodeStep.__init__(self, Map(ie))
        self.add_operation(Assign(ie))
