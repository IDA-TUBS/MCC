"""
Description
-----------

Implements generic MCC framework, i.e. cross-layer model, model operations, and generic analysis engines.

:Authors:
    - Johannes Schlatow

"""

import logging
from mcc.graph import *

class Registry:
    """ Implements/manages a cross-layer model.

    Layers and transformation steps are stored, managed, and executed by this class.
    """

    def __init__(self):
        self.by_order  = list()
        self.by_name   = dict()
        self.steps     = list()

    @staticmethod
    def _same_layers(step1, step2):
        if step1 == None or step2 == None:
            return False
        return step1.target_layer == step2.target_layer

    def _previous_step(self, step):
        idx = self.steps.index(step)
        if idx == 0:
            return None
        else:
            return self.steps[idx-1]

    def _next_layer(self, layer):
        current_layer = self.by_name[layer.name]
        idx = self.by_order.index(current_layer)
        if len(self.by_order) > idx+1:
            return self.by_order[idx+1]
        else:
            return None

    def add_layer(self, layer):
        """ Adds layer.

        Added layers can be accessed either by name or by order using the dict 
        members `Registry.by_name` and `Registry.by_order`.

        Args:
            :type layer: :class:`Layer`
        """
        self.by_order.append(layer)
        self.by_name[layer.name] = layer

    def reset(self, layer=None):
        """ Clears all layers from 'layer' and below.
        """
        if layer is None:
            start = 0
        else:
            start = self.by_order.index(layer)

        for i in range(start, len(self.by_order)):
            self.by_order[i].clear()

    def add_step(self, step):
        """ Adds a step.

        All added steps are executed sequentially by :func:`Registry.execute()`.
        Sanity checks are performed when adding a step, e.g. whether a step operates on the
        same or next layer as the previously added step.

        Args:
            :type step: :class:`Step`
        """
        # perform sanity checks (step's layers are correct, etc.)
        if len(self.steps) > 0:
            if not Registry._same_layers(self.steps[-1], step):
                self.print_steps()
                print(step)
                assert(step.target_layer == self._next_layer(self.steps[-1].target_layer))
        else:
            assert(step.target_layer == self.by_order[0])

        self.steps.append(step)

    def add_step_unsafe(self, step):
        # FIXME how do we deal with branches, i.e. going back in the layer hierarchy to decide on params in upper layers?
        self.steps.append(step)

    def write_dot(self, filename):
        """ Produces a DOT file illustrating the registered steps and layers.
        """
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
        """ Prints details about the registered steps and layers.
        """
        print()
        for step in self.steps:
            if not Registry._same_layers(self._previous_step(step), step):
                print("[%s]" % step.target_layer)
            print("  %s" % step)

    def print_engines(self):
        """ Prints details of the involved analysis engines
        """
        aengines = set()
        for step in self.steps:
            for op in step.operations:
                aengines.update(op.analysis_engines)

        print()
        for ae in aengines:
            print('[%s]' % type(ae).__name__)
            print(ae.acl_string())

    def execute(self):
        """ Executes the registered steps sequentially.
        """

        print()
        for step in self.steps:

            previous_step = self._previous_step(step)
            if not Registry._same_layers(previous_step, step):
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
        """ Must be implemented by derived classes.
        """
        logging.warning("Using default implementation of Registry._output_layer(). No output will be produced.")
        return


class Layer:
    """ Implementation of a single layer in the cross-layer model.
    """
    def __init__(self, name, nodetypes={object}):
        """
        Args:
            :param name: Layer name.
            :type  name: str
            :param nodetypes: (optional) Possible node types (base classes).
            :type  nodetypes: set
        """
        self.graph       = Graph()
        self.name        = name
        self._nodetypes  = nodetypes
        self.used_params = set()
        self.tracking    = False

    def add_node(self, obj):
        return self.graph.add_node(obj, self.node_types())

    def add_edge(self, obj):
        return self.graph.add_edge(obj)

    def create_edge(self, s, t):
        return self.graph.create_edge(s, t)

    def node_types(self):
        """
        Returns:
            tuple of possible node types (allowed base classes)
        """
        return tuple(self._nodetypes)

    def __str__(self):
        return self.name

    def clear(self):
        """ Clears the layer.
        """
        self.graph = Graph()

    def start_tracking(self):
        self.tracking = True

    def stop_tracking(self):
        self.tracking = False
        self.used_params = set()

    def _set_params(self, obj, params):
        for name, value in params.items():
            self._set_param_value(name, obj, value)

    def insert_obj(self, obj, nodes_only=False):
        """ Inserts one or multiple objects into the layer.

        Args:
            :param obj: Object(s) to be inserted.
            :type  obj: :class:`mcc.graph.Edge`, :class:`mcc.graph.GraphObj`, object (used as node), a list or set of these.
            :param nodes_only: Only insert node objects (used internally for two-pass insertion)
            :type  nodes_only: boolean

        Returns:
            set of inserted nodes and edges
        """
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
                    o = self.add_edge(obj.obj)
                    self._set_params(o, obj.params())
                    inserted.add(o)
            else:
                o = self.add_node(obj.obj)
                self._set_params(o, obj.params())
                inserted.add(o)
        else:
            inserted.add(self.add_node(obj))

        return inserted

    def _get_params(self, obj):
        if isinstance(obj, Edge): # obj is an edge
            attributes = self.graph.edge_attributes(obj)
        else:
            # obj is a node
            attributes = self.graph.node_attributes(obj)

        if 'params' not in attributes:
            attributes['params'] = dict()

        return attributes['params']

    def get_param_candidates(self, ae, param, obj):
        """ Get candidate values for the given parameter and object.

        Args:
            :param ae: Analysis engine that accesses this parameter (for acl check).
            :type  ae: :class:`AnalysisEngine`
            :param param: Accessed parameter.
            :type  param: str
            :param obj: Accessed object for which the parameter candidates are returned.
            :type  obj: Valid node or edge object of this layer.

        Returns:
            set of candidate values for the given param and object. Empty set if parameter is not present.
        """
        assert(ae.check_acl(self, param, 'reads'))
        return self._get_param_candidates(param, obj)

    def _get_param_candidates(self, param, obj):
        params = self._get_params(obj)

        if self.tracking and param is not None:
            self.used_params.add(param)

        if param in params:
            return params[param]['candidates']
        else:
            return set()

    def _clear_param_values(self, param):
        for node in self.graph.nodes():
            if param in self._get_params(node):
                self._set_param_value(param, node, None)
        for edge in self.graph.edges():
            if param in self._get_params(edge):
                self._set_param_value(param, edge, None)

    def _clear_param_candidates(self, param):
        for node in self.graph.nodes():
            if param in self._get_params(node):
                self._set_param_candidate(param, node, set())
        for edge in self.graph.edges():
            if param in self._get_params(edge):
                self._set_param_candidate(param, edge, set())

    def set_param_candidates(self, ae, param, obj, candidates):
        """ Set candidate values for the given parameter and object.

        Args:
            :param ae: Analysis engine that accesses this parameter (for acl check).
            :type  ae: :class:`AnalysisEngine`
            :param param: Accessed parameter.
            :type  param: str
            :param obj: Accessed object for which the parameter candidates are set.
            :type  obj: Valid node or edge object of this layer.
            :param candidates: candidate values
            :type  candidate: set
        """
        assert(ae.check_acl(self, param, 'writes'))
        assert(isinstance(candidates, set))
        self._set_param_candidates(param, obj, candidates)

    def _set_param_candidates(self, param, obj, candidates):
        params = self._get_params(obj)

        if param not in params:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['candidates'] = candidates

    def get_param_value(self, ae, param, obj):
        """ Get value for the given parameter and object.

        Args:
            :param ae: Analysis engine that accesses this parameter (for acl check).
            :type  ae: :class:`AnalysisEngine`
            :param param: Accessed parameter.
            :type  param: str
            :param obj: Accessed object for which the parameter value is returned.
            :type  obj: Valid node or edge object of this layer.

        Returns:
            Values for the given param and object. None if parameter is not present.
        """
        assert(ae.check_acl(self, param, 'reads'))
        return self._get_param_value(param, obj)

    def _get_param_value(self, param, obj):
        params = self._get_params(obj)

        if param in params:
            return params[param]['value']
        else:
            return None

    def set_param_value(self, ae, param, obj, value):
        """ Set value for the given parameter and object.

        Args:
            :param ae: Analysis engine that accesses this parameter (for acl check).
            :type  ae: :class:`AnalysisEngine`
            :param param: Accessed parameter.
            :type  param: str
            :param obj: Accessed object for which the parameter value is set.
            :type  obj: Valid node or edge object of this layer.
            :param value: Value to be set.
        """
        assert(ae.check_acl(self, param, 'writes'))
        self._set_param_value(param, obj, value)

    def _set_param_value(self, param, obj, value):
        params = self._get_params(obj)

        if param not in params:
            params[param] = { 'value' : None, 'candidates' : set() }

        params[param]['value'] = value

class AnalysisEngine:
    """ Base class for analysis engines.
    """

    def __init__(self, layer, param, name=None, acl=None):
        """
        Args:
            :param layer: The (source) layer on which the analysis engines operates.
            :type  layer: :class:`Layer`
            :param param: The parameter that is modified by this analysis engine.
            :type  param: str
            :param name:  (optional) Name of the analysis engine.
            :type  name:  str
            :param acl:   Access list for this analysis engine.
            :type  acl:   dict, example (default):

                { layer : { 'reads' : param, 'writes' : param } }

        """
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
        """ Checks whether a certain access is granted by the engines acl.

        Args:
            :param layer:  accessed layer
            :type  layer:  :class:`Layer`
            :param param:  accessed param
            :type  param:  str
            :param access: access type
            :type  access: str ('reads' or 'writes')

        """
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

    def map(self, obj, candidates=None):
        """ Must be implemented by derived classes.

        Args:
            :param obj: The graph object to evalute.
            :param candidates: The existing set of candidate values.
            :type  candidates: set or None

        Returns:
            set of candidate values

        Raises:
            NotImplementedError
        """
        raise NotImplementedError()

    def assign(self, obj, candidates):
        """ Must be implemented by derived classes.

        Args:
            :param obj: The graph object to evalute.
            :param candidates: The existing set of candidates.
            :type  candidates: set

        Returns:
            One value from candidates

        Raises:
            NotImplementedError
        """
        raise NotImplementedError()

    def transform(self, obj, target_layer):
        """ Must be implemented by derived classes.

        Args:
            :param obj: The graph object to evalute.
            :param target_layer: The target layer.
            :type  target_layer: :class:`Layer`

        Returns:
            A node (object), an edge (:class:`mcc.graph.Edge`), a :class:`mcc.graph.GraphObj`, or a set or list of these.

        Raises:
            NotImplementedError
        """
        raise NotImplementedError()

    def check(self, obj, first):
        """ Must be implemented by derived classes.

        Raises:
            NotImplementedError
        """
        raise NotImplementedError()

    def source_types(self):
        """ Returns compatible source types, i.e. nodes of layer must be an instance of this type.
        """
        return tuple({object})

    def target_types(self):
        """ Returns compatible target types, i.e. nodes of target layer expect an instance of this type or a subclass.
        """
        return tuple({object})

class ExternalAnalysisEngine(AnalysisEngine):

    def __init__(self, layer, param, name=None, acl=None):
        AnalysisEngine.__init__(self, layer, param, name, acl)

        self.state = "START" # EXPORTED, WAITING, READY

        self.query = None

    def _export_model(self):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _start_query(self):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _end_query(self):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _query_map(self, obj, candidates):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _query_assign(self, obj, candidates):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _wait_for_result(self):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _parse_map(self, obj):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _parse_assign(self, obj):
        """ to be implemented by derived class
        """
        raise NotImplementedError()

    def _wait_for_file(self, filename):
        import os
        import time
        if not os.path.exists(filename):
            print("Waiting for file %s", filename)
        while not os.path.exists(filename):
            time.sleep(1)

        if os.path.getsize(filename) == 0:
            print("Waiting for file %s not empty" % filename)
        while os.path.getsize(filename) == 0:
            time.sleep(1)

    def _state_check_READY(self):
        if self.state == "EXPORTED":
            self._state_check_WAITING()

        if self.state == "WAITING":
            self.run()

        assert(self.state == "READY")

    def _state_check_EXPORTED(self):
        if self.state == "START" or self.state == "READY":
            self._export_model()
            self.state = "EXPORTED"
            self._start_query()

        assert(self.state == "EXPORTED")

    def _state_check_WAITING(self):
        if self.state == "EXPORTED":
            self._end_query()
            self.state = "WAITING"

        assert(self.state == "WAITING")

    def prepare_map(self, obj, candidates):
        self._state_check_EXPORTED()

        self._query_map(obj, candidates)

    def prepare_assign(self, obj, candidates):
        self._state_check_EXPORTED()

        self._query_assign(obj, candidates)

    def run(self):
        self._state_check_WAITING()

        if self._wait_for_result():
            self.state = "READY"

    def map(self, obj):
        self._state_check_READY()

        return self._parse_map(obj)

    def assign(self, obj):
        self._state_check_READY()

        return self._parse_assign(obj)

    def check(self, obj, first):
        raise NotImplementedError()

    def transform(self, obj, target_layer):
        raise NotImplementedError()


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

    def check(self, obj, first):
        return True

    def target_types(self):
        return self.layer.node_types()

class CopyEngine(AnalysisEngine):
    """ Copies a parameter from one layer to another layer.
    """
    def __init__(self, layer, param, source_layer, source_param=None):
        """ 
        Args:
            :param layer: The target layer.
            :type  layer: :class:`Layer`
            :param param: The target parameter.
            :type  param: str
            :param source_layer: The source layer.
            :type  source_layer: :class:`Layer`
            :param source_param: An optional source parameter (otherwise: same as param).
            :type  source_param: str
        """
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
    """ Inherits a parameter from neighbouring nodes.
    """
    def __init__(self, layer, param, out_edges=True, in_edges=True):
        """ 
        Args:
            :param layer: The layer on which we operate.
            :type  layer: :class:`Layer`
            :param param: The parameter to inherit.
            :type  param: str
            :param out_edges: Whether to evaluate outgoing edges when iterating neighbouring nodes.
            :type  out_edges: boolean
            :param in_edges: Whether to evaluate incoming edges when iterating neighbouring nodes.
            :type  in_edges: boolean
        """
        AnalysisEngine.__init__(self, layer, param)
        self.out_edges=out_edges
        self.in_edges=in_edges

    def map(self, obj, candidates):
        candidates = set()

        if self.out_edges:
            edges = self.layer.graph.out_edges(obj)

            for e in edges:
                candidates.add(self.layer.get_param_value(self, self.param, e.target))

        if self.in_edges:
            edges = self.layer.graph.in_edges(obj)

            for e in edges:
                candidates.add(self.layer.get_param_value(self, self.param, e.source))

        if len(candidates) > 1:
            logging.warning("Cannot inherit '%s' from source/target node unambiguously" % (self.param))
        elif len(candidates) == 0:
            logging.warning("No value for param '%s' for node %s\'s nodes." % (self.param, obj))

        return candidates

    def assign(self, obj, candidates):
        return list(candidates)[0]

class Operation:
    """ Base class for operations on a model.
    """

    def __init__(self, ae, name=''):
        """ Creates a model operation.

        The source layer, param, and (if present) target layer are taken from ae. 

        Args:
            :param ae: The analysis engine used for the operation.
            :type  ae: :class:`AnalysisEngine`
            :param name: An optional name.
            :type  name: str

        Raises:
            Exception: ae is not compatible
        """
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
        checked = True
        for has in self.source_layer.node_types():
            found = False
            for t in ae.source_types():
                if issubclass(has, t):
                    found = True
                    break

            if not found:
                checked = False
                break

        if not checked:
            raise Exception("Analysis engine %s does not support nodetypes %s of source layer" % (ae,
                self.source_layer.node_types()))

    def register_ae(self, ae):
        """ Registers another analysis engine.
        
        The analysis engine is checked for compatibility.

        Args:
            :param ae: The analysis engine.
            :type  ae: :class:`AnalysisEngine`

        Raises:
            Exception: the ae is not compatible

        """

        self._check_ae_compatible(ae)
        self.analysis_engines.append(ae)
        return ae

    def check_source_type(self, obj):
        """ Checks whether obj is of expected source type.

        Args:
            :param obj: node object

        Returns:
            boolean.
        """
        for ae in self.analysis_engines:
            if not isinstance(obj, ae.source_types()):
                logging.error("%s is not an instance of %s" % (type(obj), ae.source_types()))
                return False

        return True

    def execute(self, iterable, dec_graph=None):
        raise NotImplementedError()

    def __repr__(self):
        return "%s(%s) [%s]" % (type(self).__name__, self.name, ','.join([str(ae) for ae in self.analysis_engines]))

class Map(Operation):
    """ Implements the map operation, which return candidates for the associated parameter.
    """
    def __init__(self, ae, name=''):
        """ Creates a map operation.

        Args:
            :param ae: The analysis engine used for the operation.
            :type  ae: :class:`AnalysisEngine`
            :param name: An optional name.
            :type  name: str

        Raises:
            Exception: ae is not compatible
        """
        Operation.__init__(self, ae, name)

    def execute(self, iterable, dec_graph=None):
        logging.info("Executing %s" % self)

        # check if we need to skip elements
        for (index, obj) in enumerate(iterable):
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            param_value = self.source_layer.get_param_value(self.analysis_engines[0], self.param, obj)
            if param_value is not None:
                continue

            # check if we can resue old results
            candidates = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)
            if len(candidates) == 0 or (len(candidates) == 1 and list(candidates)[0] == None):
                candidates = None

            self.source_layer.start_tracking()
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
            if dec_graph is not None:
                dec_graph.add_map_node(self.source_layer, self.param, obj, candidates, index)

                # FIXME we shouldn't need DependNodes if we directly add edges to the corresponding AssignNodes
                # edge = Edge(dep_node, map_node)
                # dec_graph.add_edge(edge)

            self.source_layer.stop_tracking()
            self.source_layer.set_param_candidates(self.analysis_engines[0], self.param, obj, candidates)

        return True

class BatchMap(Map):
    def __init__(self, ae, name=''):
        assert(isinstance(ae, ExternalAnalysisEngine))
        Map.__init__(self, ae, name)

    def register_ae(self, ae):
        """
        Returns:
            False -- only a single analysis engine must be registered (which is given on construction)
        """
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable):
        # FIXME implement backtracking support

        ae = self.analysis_engines[0]

        # prepare
        for obj in iterable:
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            if self.source_layer.get_param_value(ae, self.param, obj) is not None:
                continue

            candidates = self.source_layer.get_param_candidates(ae, self.param, obj)
            if len(candidates) == 0 or (len(candidates) == 1 and list(candidates)[0] == None):
                candidates = None

            if candidates is None:
                ae.prepare_map(obj, None)
            else:
                ae.prepare_map(obj, set(candidates))

        # get results
        for obj in iterable:

            candidates = self.source_layer.get_param_candidates(ae, self.param, obj)
            if len(candidates) == 0 or (len(candidates) == 1 and list(candidates)[0] == None):
                candidates = None

            if candidates is None:
                candidates = ae.map(obj)
            else:
                new_candidates = ae.map(obj)
                if new_candidates is not None:
                    candidates &= new_candidates 

            # update candidates for this parameter in layer object
            assert(candidates is not None)
            self.source_layer.set_param_candidates(ae, self.param, obj, candidates)

        return True

class Assign(Operation):
    """ Implements the assign operation, which selects one of the previously mapped candidates for the associated parameter.
    """
    def __init__(self, ae, name=''):
        """ Creates an assign operation.

        Args:
            :param ae: The analysis engine used for the operation.
            :type  ae: :class:`AnalysisEngine`
            :param name: An optional name.
            :type  name: str

        Raises:
            Exception: ae is not compatible
        """
        Operation.__init__(self, ae, name)

    def register_ae(self, ae):
        """
        Returns:
            False -- only a single analysis engine must be registered (which is given on construction)
        """
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable, dec_graph=None):
        logging.info("Executing %s" % self)

        it = iter(iterable)
        # TODO ideally, we can move the backtracking logic to the DependencyGraph in backtracking.py 
        if dec_graph is not None:
            if dec_graph.current is not None:
                if dec_graph.current.operation == self:
                    skip_n_elements = dec_graph.current.attribute_index
                    skip_n_elements -= 1

                    for i in range(skip_n_elements):
                        next(it)

                    obj = next(it)
                    # obj is the operation that needs to choose a different
                    # candidate

                    used_candidates = set()
                    for edge in self.dec_graph.out_edges(self.dec_graph.current):
                        used_candidates.add(edge.target.value)

                    candidates = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)
                    candidates -= used_candidates

                    result = self.analysis_engines[0].assign(obj, candidates)
                    assert(result in candidates)
                    dec_graph.add_assign_node(self.source_layer, self.param, obj, result, index)

        for (index, obj) in enumerate(it):
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            if self.source_layer.get_param_value(self.analysis_engines[0], self.param, obj) is not None:
                continue

            candidates = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)

            if len(candidates) == 0:
                logging.error("No candidates left for param '%s'." % self.param)
                # TODO test case for testing that no candidates are left
                # (e.g. add dummy component for a function with an additional unresolvable dependency)
                raise ConstraintNotSatisfied(self.analysis_engines[0].layer, self.param, obj)

            result = self.analysis_engines[0].assign(obj, candidates)
            assert(result in candidates)

            if dec_graph is not None:
                dec_graph.add_assign_node(self.source_layer, self.param, obj, result, index)

            self.source_layer.set_param_value(self.analysis_engines[0], self.param, obj, result)

        return True

class BatchAssign(Assign):
    def __init__(self, ae, name=''):
        assert(isinstance(ae, ExternalAnalysisEngine))
        Assign.__init__(self, ae, name)

    def execute(self, iterable):
        # FIXME implement backtracking support

        ae = self.analysis_engines[0]

        # prepare
        for obj in iterable:
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            if self.source_layer.get_param_value(ae, self.param, obj) is not None:
                continue

            candidates = self.source_layer.get_param_candidates(ae, self.param, obj)
            if len(candidates) == 0:
                logging.error("No candidates left for param '%s'." % self.param)

            ae.prepare_assign(obj, candidates)

        # get results
        for obj in iterable:
            candidates = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)

            result = ae.assign(obj)

            assert(result in candidates)

            self.source_layer.set_param_value(ae, self.param, obj, result)

        return True

class Transform(Operation):
    """ Implements the transform operation, which transforms objects (nodes/edges) of one layer into objects of the target layer.
    """

    def __init__(self, ae, target_layer, name=''):
        """ Creates an assign operation.

        Args:
            :param ae: The analysis engine used for the operation.
            :type  ae: :class:`AnalysisEngine`
            :param target_layer: The target layer.
            :type  ae: :class:`Layer`
            :param name: An optional name.
            :type  name: str

        Raises:
            Exception: ae is not compatible
        """
        Operation.__init__(self, ae, name)
        self.target_layer = target_layer
        self.source_layer = ae.layer

    def _check_ae_compatible(self, ae):
        Operation._check_ae_compatible(self, ae)

        compatible = False
        for t in ae.target_types():
            if compatible:
                break

            for expected in self.target_layer.node_types():
                if issubclass(t, expected):
                    compatible = True
                    break

        if not compatible:
            print(ae.target_types())
            raise Exception("Analysis engine %s does not have nodetypes %s of target layer" % (ae,
                self.target_layer.node_types()))

    def register_ae(self, ae):
        """
        Returns:
            False -- only a single analysis engine must be registered (which is given on construction)
        """
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable, dec_graph=None):
        logging.info("Executing %s" % self)

        for (index ,obj) in enumerate(iterable):
            new_objs = self.analysis_engines[0].transform(obj, self.target_layer)
            assert new_objs, "transform() did not return any object"

            # remark: also returns already existing objects
            inserted = self.target_layer.insert_obj(new_objs)
            assert len(inserted) > 0

            for o in inserted:
                if not isinstance(o, Edge):
                    assert isinstance(o, self.target_layer.node_types()), "%s does not match types %s" % (o,
                            self.target_layer.node_types())

            if dec_graph is not None:
                dec_graph.add_transform_node(self.source_layer, self.target_layer,
                        obj, inserted, index)

            self.source_layer._set_param_value(self.target_layer.name, obj, inserted)
            for o in inserted:
                src = self.target_layer._get_param_value(self.source_layer.name, o)
                if src is None:
                    src = obj
                elif isinstance(src, set):
                    src.add(obj)
                else:
                    src = { src, obj }
                self.target_layer._set_param_value(self.source_layer.name, o, src)

        return True

class Check(Operation):
    """ Implements the check operation, which is used for admission testing.
    """
    def __init__(self, ae, name=''):
        Operation.__init__(self, ae, name)

    def execute(self, iterable, dec_graph=None):
        logging.info("Executing %s" % self)

        for ae in self.analysis_engines:
            first = True
            for obj in iterable:
                assert(self.check_source_type(obj))

                if not ae.check(obj, first):
                    raise ConstraintNotSatisfied(ae.layer, ae.param, obj)

                first = False

        return True

class ConstraintNotSatisfied(Exception):
    def __init__(self, layer, param, obj):
        super().__init__()
        self.layer    = layer
        self.param    = param
        self.obj      = obj

class Step:
    """ Implements model transformation step.

        A step consists of several operation that are executed sequentially.
        All operations must have the same source layer and target layer.

    """
    def __init__(self, op):
        """ Initialises the object and sets the first operation of type :class:`Operation`"""
        assert(isinstance(op, Operation))
        self.operations = [op]
        self.source_layer = op.source_layer
        self.target_layer = op.target_layer

    def add_operation(self, op):
        """ Adds an operation to the internal list.

        Args:
            :param op: The operation.
            :type  op: :class:`Operation`

        Returns:
            op
        """
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

    def execute(self, dec_graph=None):
        """ Must be implemented by derived classes.

        Raises:
            NotImplementedError
        """
        raise NotImplementedError()

class NodeStep(Step):
    """ Implements model transformation step on nodes.
    """
    def execute(self, dec_graph=None):
        """ For every operation, calls :func:`Operation.execute()` for every node in the layer.
        """
        last_index = 0
        if dec_graph is not None:
            if dec_graph.last_step == self:
                last_index = dec_graph.last_operation_index

        for op in self.operations[last_index:]:
            try:
                if dec_graph is not None:
                    dec_graph.set_operation_index(self.operations.index(op))
                    dec_graph.set_operation(op)
                    dec_graph.set_step(self)

                if not op.execute(self.source_layer.graph.nodes(), dec_graph):
                    raise Exception("NodeStep failed during '%s' on layer '%s'" % (op, self.source_layer.name))
                    return False
            except ConstraintNotSatisfied as cns:
                raise cns

        return True

class EdgeStep(Step):
    """ Implements model transformation step on edges.
    """
    def execute(self, dec_graph=None):
        """ For every operation, calls :func:`Operation.execute()` for every edge in the layer.
        """
        last_index = 0
        if dec_graph is not None:
            current = dec_graph.current
            if dec_graph.last_step == self:
                last_index = dec_graph.last_operation_index

        for op in self.operations[last_index:]:
            try:
                dec_graph.set_operation_index(self.operations.index(op))

                if not op.execute(self.source_layer.graph.edges(), dec_graph):
                    raise Exception("EdgeStep failed during %s on layer '%s'" % (op, self.source_layer.name))
                    return False
            except ConstraintNotSatisfied as cns:
                raise cns

        return True

class MapAssignNodeStep(NodeStep):
    def __init__(self, ae, name):
        NodeStep.__init__(self, Map(ae, name=name))
        self.add_operation(Assign(ae, name=name))

class MapAssignEdgeStep(EdgeStep):
    def __init__(self, ae, name):
        EdgeStep.__init__(self, Map(ae, name=name))
        self.add_operation(Assign(ae, name=name))

class CopyNodeTransform(Transform):
    """ Transform operation that returns the nodes found in the layer.
    """
    def __init__(self, layer, target_layer):
        Transform.__init__(self, DummyEngine(layer), target_layer)

class CopyEdgeTransform(Transform):
    """ Transform operation that returns the edges found in the layer.
    """
    def __init__(self, layer, target_layer):
        Transform.__init__(self, DummyEngine(layer), target_layer)

class CopyNodeStep(NodeStep):
    """ Copies nodes to target layer.
    """
    def __init__(self, layer, target_layer):
        NodeStep.__init__(self, CopyNodeTransform(layer, target_layer))

class CopyEdgeStep(EdgeStep):
    """ Copies edges to target layer.
    """
    def __init__(self, layer, target_layer):
        EdgeStep.__init__(self, CopyEdgeTransform(layer, target_layer))

class CopyMappingStep(NodeStep):
    """ Copies 'mapping' parameter of the nodes to the target layer.
    """
    def __init__(self, layer, target_layer):
        ce = CopyEngine(target_layer, 'mapping', layer)
        NodeStep.__init__(self, Map(ce))
        self.add_operation(Assign(ce))

class CopyServiceStep(EdgeStep):
    """ Copies 'service' parameter of the edges to the target layer.
    """
    def __init__(self, layer, target_layer):
        ce = CopyEngine(target_layer, 'service', layer)
        EdgeStep.__init__(self, Map(ce))
        self.add_operation(Assign(ce))

class CopyServicesStep(EdgeStep):
    """ Copies 'source-service' and 'target-service' parameter of the edges to the target layer.
    """
    def __init__(self, layer, target_layer):
        ce1 = CopyEngine(target_layer, 'source-service', layer)
        ce2 = CopyEngine(target_layer, 'target-service', layer)
        EdgeStep.__init__(self, Map(ce1, 'source-service'))
        self.add_operation(Assign(ce1, 'source-service'))
        self.add_operation(Map(ce2, 'target-service'))
        self.add_operation(Assign(ce2, 'target-service'))

class InheritFromSourceStep(NodeStep):
    """ Inherits a parameter value from neighbouring source nodes.
    """
    def __init__(self, layer, param):
        ie = InheritEngine(layer, param, out_edges=False, in_edges=True)
        NodeStep.__init__(self, Map(ie))
        self.add_operation(Assign(ie))

class InheritFromTargetStep(NodeStep):
    """ Inherits a parameter value from neighbouring target nodes.
    """
    def __init__(self, layer, param):
        ie = InheritEngine(layer, param, out_edges=True, in_eges=False)
        NodeStep.__init__(self, Map(ie))
        self.add_operation(Assign(ie))

class InheritFromBothStep(NodeStep):
    """ Inherits a parameter value from neighbouring source and target nodes.
    """

    def __init__(self, layer, param, engines=None):
        ie = InheritEngine(layer, param='mapping')
        op = Map(ie)
        if engines is not None:
            for ae in engines:
                op.register_ae(ae)
        NodeStep.__init__(self, op)
        self.add_operation(Assign(ie))
