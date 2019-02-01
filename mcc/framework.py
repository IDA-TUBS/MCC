"""
Description
-----------

Implements generic MCC framework, i.e. cross-layer model, model operations, and generic analysis engines.

:Authors:
    - Johannes Schlatow

"""

import logging
from mcc.graph import *

class DecisionGraph(Graph):
    """ Stores dependencies between decisions.
    """

    class Node:
        def __init__(self, layer, obj, param):
            self.layer = layer
            self.obj   = obj
            self.param = param

        def __repr__(self):
            return self.__str__()

        def __str__(self):
            return '%s:%s:%s' % (self.layer, self.obj, self.param)

    def __init__(self):
        super().__init__()

        self.read    = set()
        self.written = set()

        self.node_store = dict()

        # add root node
        self.root = self.Node(None, None, None)
        super().add_node(self.root, {self.Node})

    def candidates_exhausted(self, node):
        # are there any candidates left
        candidates  = node.layer._get_param_candidates(node.param, node.obj)
        failed      = node.layer.get_param_failed(node.param, node.obj)
        value       = {node.layer._get_param_value(node.param, node.obj)}

        return len(candidates-failed-value) == 0

    def initialize_tracking(self, layers):
        for layer in layers:
            layer.dependency_tracker = self

    def start_tracking(self):
        self.read    = set()
        self.written = set()

    def stop_tracking(self, operation):
        self.add_dependencies(operation, self.read-self.written, self.written)
        self.read    = set()
        self.written = set()

    def track_read(self, layer, obj, param):
        self.read.add(self.find_dependency(layer, obj, param))

    def track_written(self, layer, obj, param):
        self.written.add(self.add_node(layer, obj, param))

    def find_dependency(self, layer, obj, param):
        node = self.find_node(layer, obj, param)
        if node is None:
            return self.root

        return node

    def find_node(self, layer, obj, param):
        if layer not in self.node_store:
            return None

        if obj not in self.node_store[layer]:
            return None

        if param not in self.node_store[layer][obj]:
            return None

        return self.node_store[layer][obj][param]

    def search(self, layer, obj):
        if layer not in self.node_store:
            return None

        if obj not in self.node_store[layer]:
            return None

        nodes = set()
        for node in self.node_store[layer][obj].values():
            nodes.add(node)

        return nodes

    def operations(self, node):
        return self.node_attributes(node)['operations']

    def add_node(self, layer, obj, param):
        found = self.find_node(layer, obj, param)
        if found is None:
            found = super().add_node(self.Node(layer, obj, param), {self.Node})
            self.node_attributes(found)['operations'] = set()

            if layer not in self.node_store:
                self.node_store[layer] = dict()
            if obj not in self.node_store[layer]:
                self.node_store[layer][obj] = dict()

            self.node_store[layer][obj][param] = found

        return found

    def add_dependencies(self, operation, read, written):
        if len(read) == 0 and len(written) > 0:
            read.add(self.root)

        for n in written:
            self.node_attributes(n)['operations'].add(operation)

            for dep in read:
                self.create_edge(dep, n)

    def remove(self, node):
        self.remove_node(node)
        del self.node_store[node.layer][node.obj][node.param]

    def write_dot(self, filename):

        # TODO for readability, we could omit the root node
        # TODO for readability, we should write subgraphs

        with open(filename, 'w') as file:
            file.write('digraph {\n')

            nodes = [node for node in self.graph.nodes()]

            for node in nodes:
                if node is None:
                    print('Node is none')

                node_str = '"{0}" [label="{1}", shape=hexagon]'.format(nodes.index(node), (node))

                file.write(node_str)

            for (source, target) in self.graph.edges():
                edge = '{} -> {}\n'.format(nodes.index(source), nodes.index(target))
                file.write(edge)

                pass
            file.write('}\n')


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

    def _prev_layer(self, layer):
        if layer in self.by_name.keys():
            current_layer = self.by_name[layer.name]
        else:
            assert layer in self.by_name.values()
            current_layer = layer

        idx = self.by_order.index(current_layer)
        if len(self.by_order) > 0:
            return self.by_order[idx-1]
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

    def execute(self, decision_graph=None):
        """ Executes the registered steps sequentially.
        """

        if decision_graph is not None:
            decision_graph.initialize_tracking(self.by_order)

        print()
        for step in self.steps:

            previous_step = self._previous_step(step)
            if not Registry._same_layers(previous_step, step):
                logging.info("Creating layer %s" % step.target_layer)
                if previous_step is not None:
                    self._output_layer(previous_step.target_layer)

            try:
                step.execute(self)
            except Exception as ex:
                self._output_layer(step.target_layer, suffix='-error')
                raise(ex)

        self._output_layer(self.steps[-1].target_layer)

    def complete_operation(self, operation):
        return

    def skip_operation(self, operation):
        return False

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
        self.dependency_tracker = None
        self.tracked_operation  = None

    def __getstate__(self):
        return (self.graph, self.name, self._nodetypes)

    def __setstate__(self, state):
        self.graph, self.name, self._nodetypes = state
        self.dependency_tracker = None
        self.tracked_operation  = None

    def add_node(self, obj):
        return self.graph.add_node(obj, self.node_types())

    def add_edge(self, obj):
        return self.graph.add_edge(obj)

    def remove_node(self, obj):
        return self.graph.remove_node(obj)

    def remove_edge(self, obj):
        return self.graph.remove_edge(obj.source, obj.target, obj)

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

    def start_tracking(self, op):
        if self.dependency_tracker is not None:
            assert(self.tracked_operation is None)
            self.tracked_operation = op
            self.dependency_tracker.start_tracking()

    def stop_tracking(self):
        if self.dependency_tracker is not None:
            assert(self.tracked_operation is not None)
            self.dependency_tracker.stop_tracking(self.tracked_operation)
            self.tracked_operation = None

    def set_params(self, ae, obj, params):
        for name, value in params.items():
            self.set_param_value(ae, name, obj, value)

    def insert_obj(self, ae, obj, nodes_only=False):
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
                tmp = self.insert_obj(ae, o, nodes_only=True)
                if len(tmp) == 0:
                    edges.add(o)
                else:
                    inserted.update(tmp)

            # now we add the remaining edges
            for o in edges:
                inserted.update(self.insert_obj(ae, o, nodes_only=False))
            assert(len(obj) == len(inserted))
        elif isinstance(obj, GraphObj):
            if obj.is_edge():
                if not nodes_only:
                    o = self.add_edge(obj.obj)
                    self.set_params(ae, o, obj.params())
                    inserted.add(o)
            else:
                o = self.add_node(obj.obj)
                self.set_params(ae, o, obj.params())
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

        if self.dependency_tracker:
            self.dependency_tracker.track_read(self, obj, param)

        return self._get_param_candidates(param, obj)

    def _get_param_candidates(self, param, obj):
        params = self._get_params(obj)

        if param in params:
            return params[param]['candidates']
        else:
            return set()

    def get_param_failed(self, param, obj):
        params = self._get_params(obj)

        if param in params:
            if 'failed' in params[param]:
                return params[param]['failed']

        return set()

    def add_param_failed(self, param, obj, value):
        params = self._get_params(obj)

        assert param in params, "param %s not available on %s for %s" % (param,self,obj)

        if 'failed' not in params[param]:
            params[param]['failed'] = set()

        params[param]['failed'].add(value)

    def _clear_param_value(self, param, obj):
        self._set_param_value(param, obj, None)

    def _clear_param_candidates(self, param, obj):
        params = self._get_params(obj)
        if param in params:
            params[param]['candidates'] = set()

            if 'failed' in params[param]:
                params[param]['failed'] = set()

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

        if self.dependency_tracker:
            self.dependency_tracker.track_written(self, obj, param)

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

        if self.dependency_tracker:
            self.dependency_tracker.track_read(self, obj, param)

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

        if self.dependency_tracker:
            self.dependency_tracker.track_written(self, obj, param)

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
            print("Waiting for file %s" % filename)
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

    def execute(self, iterable):
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

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        # check if we need to skip elements
        for obj in iterable:
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            param_value = self.source_layer._get_param_value(self.param, obj)
            if param_value is not None:
                continue

            # check if we can resue old results
            candidates = self.source_layer._get_param_candidates(self.param, obj)
            if len(candidates) == 0 or (len(candidates) == 1 and list(candidates)[0] == None):
                candidates = None

            self.source_layer.start_tracking(self)

            for ae in self.analysis_engines:

                if candidates is None:
                    candidates = ae.map(obj, None)
                else:
                    # build intersection of candidates for all analyses
                    new_candidates = ae.map(obj, set(candidates))
                    if new_candidates is not None:
                        candidates &= new_candidates

            self.source_layer.set_param_candidates(self.analysis_engines[0], self.param, obj, candidates)

            self.source_layer.stop_tracking()

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

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        it = iter(iterable)

        for obj in iterable:
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            if self.source_layer.get_param_value(self.analysis_engines[0], self.param, obj) is not None:
                continue

            self.source_layer.start_tracking(self)

            raw_cand   = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)
            candidates = raw_cand - self.source_layer.get_param_failed(self.param, obj)

            if len(candidates) == 0:
                logging.error("No candidates left for param '%s'." % self.param)
                # TODO test case for testing that no candidates are left
                # (e.g. add dummy component for a function with an additional unresolvable dependency)
                raise ConstraintNotSatisfied(self.analysis_engines[0].layer, self.param, obj)

            result = self.analysis_engines[0].assign(obj, candidates)
            assert(result in candidates)

            self.source_layer.set_param_value(self.analysis_engines[0], self.param, obj, result)

            self.source_layer.stop_tracking()

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

        if 'writes' not in ae.acl[self.source_layer]:
            ae.acl[self.source_layer]['writes'] = set()

        if self.target_layer not in ae.acl:
            ae.acl[self.target_layer] = { 'writes' : set() }

        if 'writes' not in ae.acl[self.target_layer]:
            ae.acl[self.target_layer]['writes'] = set()

        ae.acl[self.source_layer]['writes'].add(self.target_layer.name)
        ae.acl[self.target_layer]['writes'].add(self.source_layer.name)

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

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        for (index ,obj) in enumerate(iterable):
            self.source_layer.start_tracking(self)

            new_objs = self.analysis_engines[0].transform(obj, self.target_layer)
            assert new_objs, "transform() did not return any object"

            # remark: also returns already existing objects
            inserted = self.target_layer.insert_obj(self.analysis_engines[0], new_objs)
            assert len(inserted) > 0

            for o in inserted:
                if not isinstance(o, Edge):
                    assert isinstance(o, self.target_layer.node_types()), "%s does not match types %s" % (o,
                            self.target_layer.node_types())

            self.source_layer.set_param_value(self.analysis_engines[0], self.target_layer.name, obj, inserted)
            for o in inserted:
                src = self.target_layer._get_param_value(self.source_layer.name, o)
                if src is None:
                    src = obj
                elif isinstance(src, set):
                    src.add(obj)
                else:
                    src = { src, obj }
                self.target_layer.set_param_value(self.analysis_engines[0], self.source_layer.name, o, src)

            self.source_layer.stop_tracking()

        return True

class Check(Operation):
    """ Implements the check operation, which is used for admission testing.
    """
    def __init__(self, ae, name=''):
        Operation.__init__(self, ae, name)

    def execute(self, iterable):
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

    def execute(self):
        """ Must be implemented by derived classes.

        Raises:
            NotImplementedError
        """
        raise NotImplementedError()

class NodeStep(Step):
    """ Implements model transformation step on nodes.
    """
    def execute(self, registry):
        """ For every operation, calls :func:`Operation.execute()` for every node in the layer.
        """

        for op in self.operations:
            if registry.skip_operation(op):
                continue

            try:
                if not op.execute(self.source_layer.graph.nodes()):
                    raise Exception("NodeStep failed during '%s' on layer '%s'" % (op, self.source_layer.name))
                    return False

                registry.complete_operation(op)
            except ConstraintNotSatisfied as cns:
                raise cns

        return True

class EdgeStep(Step):
    """ Implements model transformation step on edges.
    """
    def execute(self, registry):
        """ For every operation, calls :func:`Operation.execute()` for every edge in the layer.
        """

        for op in self.operations:
            if registry.skip_operation(op):
                continue

            try:
                if not op.execute(self.source_layer.graph.edges()):
                    raise Exception("EdgeStep failed during %s on layer '%s'" % (op, self.source_layer.name))
                    return False

                registry.complete_operation(op)
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
