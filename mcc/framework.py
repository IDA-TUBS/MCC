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

    class Writers:
        def __init__(self):
            self.assign    = None
            self.map       = None
            self.transform = set()

        def all(self):
            result = set()

            if self.assign is not None:
                result.add(self.assign)

            if self.map is not None:
                result.add(self.map)

            result.update(self.transform)

            return result

        def empty(self):
            return self.assign is None and self.map is None and len(self.transform) == 0

        def register(self, node):
            if isinstance(node.operation, Assign):
                assert self.assign is None, "%s already registered where %s should go" % (self.assign, node)
                self.assign = node
            elif isinstance(node.operation, Map):
                assert self.map is None, "Multiple map operations are not supported (%s present, %s new)" \
                    % (self.map, node)
                self.map = node
            elif isinstance(node.operation, Transform):
                self.transform.add(node)
            else:
                raise NotImplementedError

        def deregister(self, node):
            if isinstance(node.operation, Assign):
                assert self.assign == node
                self.assign = None
            elif isinstance(node.operation, Map):
                assert self.map == node
                self.map = None
            elif isinstance(node.operation, Transform):
                self.transform.remove(node)
            else:
                raise NotImplementedError


    class Param:
        def __init__(self, layer, obj, param):
            self.layer = layer
            self.obj   = obj
            self.param = param

        def __repr__(self):
            return self.__str__()

        def __str__(self):
            return '%s:(%s):%s' % (self.layer, self.obj, self.param)

        def __hash__(self):
            return hash((self.layer, self.obj, self.param))

        def __eq__(self, rhs):
            return self.layer == rhs.layer and \
                   self.obj   == rhs.obj   and \
                   self.param == rhs.param


    class Node:
        def __init__(self, layer, obj, operation, iteration):
            self.layer     = layer
            self.obj       = obj
            self.operation = operation
            self.iteration = iteration

        def __repr__(self):
            return self.__str__()

        def __hash__(self):
            return hash((self.layer, self.obj, self.operation))

        def __str__(self):
            if self.operation is None:
                return 'Root'

            param = ''
            if self.operation.param is not None:
                param = " '%s'" % self.operation.param

            return '%d:[%s] %s%s (%s)' % (self.iteration,self.layer, type(self.operation).__name__, param, self.obj)

        def __eq__(self, rhs):
            return self.layer == rhs.layer and \
                   self.obj   == rhs.obj   and \
                   self.operation == rhs.operation


    class Failed:
        def __init__(self, params):
            self.params    = tuple(params)
            self.blacklist = set()

        def mark_current_bad(self):
            if len(self.params) == 1:
                p = self.params[0]
                # add current value to blacklist
                self.blacklist.add(p.layer.untracked_get_param_value(p.param, p.obj))
            else:
                # get current values, create a tuple and add it to blacklist
                cur = list()
                for p in self.params:
                    cur.append(p.layer.untracked_get_param_value(p.param, p.obj))
                self.blacklist.add(tuple(cur))

        def bad_values(self):
            if len(self.params) == 1:
                return self.blacklist
            else:
                return set()

        def bad_combinations(self):
            assert len(self.params) > 1

            objects = tuple([x.obj for x in self.params])
            return objects, self.blacklist

        def candidates_left(self):
            if len(self.params) == 1:
                p = self.params[0]
                candidates = p.layer.untracked_get_param_candidates(p.param, p.obj)
                value      = p.layer.untracked_get_param_value(p.param, p.obj)
                return len(candidates - self.blacklist - {value}) > 0
            else:
                return True

        def destroy(self):
            for p in self.params:
                p.layer.set_param_failed(p.param, p.obj, None)


    def __init__(self):
        super().__init__()

        self.read    = set()
        self.written = set()

        self.param_store = dict()

        self.iterations    = 0
        self.revise_assign = None

        # add root node
        self.root = self.add_node(None, None, None)

    def next_iteration(self, culprit):
        self.iterations += 1

        # remember the (assign) operation to be revised
        # because we keep this in the graph/tree to
        # maintain the order (i.e. all assigns that
        # were previously orderer below this operation
        # shall be inserted below again)
        self.revise_assign = culprit

    def candidates_exhausted(self, p):
        assert isinstance(p, self.Param)

        failed = p.layer.get_param_failed(p.param, p.obj)
        if failed is None:
            candidates = p.layer.untracked_get_param_candidates(p.param, p.obj)
            return len(candidates) <= 1

        return not failed.candidates_left()

    def revisable(self, n):
        assert isinstance(n, self.Node)

        # only Assign operations are revisable
        # remark: BatchAssign inherits from Assign
        if isinstance(n.operation, Assign):
            for p in self.written_params(n):
                if not self.candidates_exhausted(p):
                    return True

        return False

    def mark_bad(self, n):
        assert isinstance(n, self.Node)
        assert isinstance(n.operation, Assign)
        # remark: BatchAssign inherits from Assign

        if isinstance(n.operation, BatchAssign):
            # remark: all written params have the same Failed object
            written = self.written_params(n)
            p = list(written)[0]
            failed = p.layer.get_param_failed(p.param, p.obj)

            # create Failed object and add to all params
            if failed is None:
                failed = DecisionGraph.Failed(written)

                for p in written:
                    p.layer.set_param_failed(p.param, p.obj, failed)

            failed.mark_current_bad()

        elif isinstance(n.operation, Assign):
            written = self.written_params(n)
            assert len(written) == 1
            p = list(written)[0]
            failed = p.layer.get_param_failed(p.param, p.obj)
            if failed is None:
                failed = DecisionGraph.Failed([p])
                p.layer.set_param_failed(p.param, p.obj, failed)

            failed.mark_current_bad()

    def decisions(self, n):
        assert isinstance(n, self.Node)

        if not isinstance(n.operation, Assign):
            return set()

        decisions = set()

        for p in self.written_params(n):
            if len(p.layer.untracked_get_param_candidates(p.param, p.obj)) > 1:
                decisions.add(p)

        return decisions

    def initialize_tracking(self, layers):
        for layer in layers:
            layer.dependency_tracker = self

    def start_tracking(self):
        self.read    = set()
        self.written = set()

    def stop_tracking(self, layer, obj, operation, error=False):
        if isinstance(operation, Check):
            self.check_tracking()

        if self.revise_assign is not None and \
           self.revise_assign == self.Node(layer, obj, operation, self.iterations-1):
            node = self.revise_assign
            self.revise_assign = None
        else:
            debug = False
            node = self.Node(layer, obj, operation, 0)
            if node in self.nodes():
                assert isinstance(operation, Check), "%s already in dependency graph" % node
                print("%s already exists" % (node))
                for r in self.read-self.written:
                    if r not in self.read_params(node):
                        debug = True
                        print("read param %s not in %s: %s" % (r, node, self.read_params(node)))
                for w in self.written:
                    if w not in self.written_params(node):
                        debug = True
                        print("written param %s not in %s: %s" % (w, node, self.written_params(node)))


                assert not debug

            else:
                node = self.add_node(layer, obj, operation)
                self.add_dependencies(node, self.read-self.written, self.written, force_sequential=error)

        self.read    = set()
        self.written = set()

        return node

    def _raw_dependencies(self, node, read, written):
        written_params = self.written_params(node)
        read_params    = self.read_params(node)

        # if we wrote a parameter, there is an implicit read dependency to 'obj'
        for p in written:
            tmp = self.Param(p.layer, p.obj, 'obj')
            if tmp not in written:
                # if we haven't written 'obj' ourselves
                read.add(tmp)

        writers = set()
        for p in read:
            tmp = self.find_writers(p.layer, p.obj, p.param)
            if not tmp.empty():
                read_params.add(p)
                writers.update(tmp.all())
            else:
                logging.debug("no writer for read dependency %s from %s" % (p, node))

        # if node.operation is assign, add connection to map operation
        if isinstance(node.operation, Assign):
            assert len(written) == 1 or isinstance(node.operation, BatchAssign)
            for p in written:
                tmp = self.find_writers(p.layer, p.obj, p.param)
                assert tmp.map is not None, "Cannot find map operation for %s" % p
                writers.add(tmp.map)

        for p in written:
            written_params.add(p)

            if p not in self.param_store:
                self.param_store[p] = self.Writers()

            self.param_store[p].register(node)

        return writers

    def check_tracking(self):
        assert len(self.written) == 0, "check operation has written params: %s" % self.written

    def track_read(self, layer, obj, param):
        self.read.add(self.Param(layer, obj, param))

    def track_written(self, layer, obj, param):
        self.written.add(self.Param(layer, obj, param))

    def find_writers(self, layer, obj, param):
        param_obj = self.Param(layer, obj, param)
        if param_obj not in self.param_store.keys():
            return self.Writers()

        return self.param_store[param_obj]

    def find_operations(self, layer, obj):
        nodes = set()
        for node in self.nodes():
            if node.layer == layer and node.obj == obj:
                nodes.add(node)

        return nodes

    def read_params(self, node):
        return self.node_attributes(node)['read']

    def written_params(self, node):
        return self.node_attributes(node)['written']

    def add_node(self, layer, obj, operation):
        node = super().add_node(self.Node(layer, obj, operation, self.iterations))
        self.node_attributes(node)['written'] = set()
        self.node_attributes(node)['read']    = set()

        return node

    def remove(self, node):
        for p in self.written_params(node):
            w = self.find_writers(p.layer, p.obj, p.param)
            w.deregister(node)

            if w.empty():
                del self.param_store[p]

        self.remove_node(node)

    def root_path(self, u):
        preds = self.predecessors(u)
        reverse_path = [u]
        cnt = 0
        while len(preds) != 0:
            cnt += 1
            if len(preds) != 1:
                print('cnt: %d, u: %s, op: %s, preds: %s' % (cnt, u, u.operation, preds))
                print('GOTCHA nontree!')
            assert len(preds) == 1
            p = list(preds)[0]
#            assert p not in reverse_path
            reverse_path.append(p)
            preds = self.predecessors(p)

        reverse_path.reverse()
        return reverse_path

    def _stylize_node(self, node, reshape=False, highlight=False):

        all_no  = True
        choice  = False
        for p in self.written_params(node):
            if p.obj is None:
                continue
            ncands = len(p.layer.untracked_get_param_candidates(p.param, p.obj))
            if ncands != 0:
                all_no = False
            if ncands > 1:
                choice = True

        style = "shape=box"
        if reshape:
            style = "shape=ellipse"

        if highlight:
            style += ",style=\"filled,solid\",fillcolor=firebrick1"
        elif choice:
            style += ",style=\"filled,solid\",fillcolor=coral"
        elif all_no:
            style += ",style=dashed"
        else:
            style += ",style=\"filled,solid\",fillcolor=grey90"

        return style

    def write_dot(self, filename, leaves=None, verbose=False, reshape=set(), highlight=set(), skip_check=True):
        """
        Args:
            :param leaves: skip nodes which are not predecessors of the leaves
            :param verbose: show additional data for each node
        """

        with open(filename, 'w') as file:
            file.write('digraph {\n')

            if leaves is None:
                nodes = list(self.graph.nodes())
            else:
                #first, avoid duplicates
                nodes = set(leaves)
                for leaf in leaves:
                    nodes |= self.predecessors(leaf, True)
                nodes = list(nodes) #now, allow indexing

            #nodes.remove(self.root) #increase readability
            # Skip check nodes
            if skip_check:
                checks = {node for node in nodes if isinstance(node.operation, Check)} - highlight
                nodes = list(set(nodes) - checks)

            for node in nodes:
                if node is None:
                    logging.info('Node is none')

                style = self._stylize_node(node, reshape=node in reshape, highlight=node in highlight)

                label = str(node)
                if verbose:
                    def plist(data):
                        return '\n'.join([str(o) for o in data])

                    data = { 'written' : plist(self.written_params(node)),
                             'read'    : plist(self.read_params(node)) }

                    data = '\n'.join(['%s: %s' % (l,r) for l,r in data.items()])
                    label += '\n' + data

                node_str = '"{0}" [label="{1}", {2}]\n'.format(nodes.index(node), label, style)
                file.write(node_str)

            for (source, target) in self.graph.edges():
                if not {source, target}.issubset(nodes):
                    continue
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
            current_layer = self.by_name[layer]
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
#                self.print_steps()
#                logging.info(step)
                assert(step.target_layer == self._next_layer(self.steps[-1].target_layer))
        else:
            assert(step.source_layer == self.by_order[0])

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
                    dotfile.write('%s [label="%s(%s)",shape=trapezium,group=op,colorscheme=set39,fillcolor=6,style=filled];\n' %
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

    class Node:
        def __init__(self, obj):
            self._obj = obj

        def obj(self, layer):
            layer.track_read('obj', self)
            return self._obj

        def untracked_obj(self):
            return self._obj

        def __repr__(self):
            return 'Node: %s' % self._obj


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

    def _add_node(self, node):
        assert isinstance(node, self.Node)
        obj  = node.untracked_obj()
        assert isinstance(obj, self.node_types()), \
               "%s is does not match types %s" % (obj, self.node_types())

        assert node not in self.graph.nodes(), '%s already inserted' % node

        self.track_written('obj', node)
        self.track_written('outedges', node)
        self.track_written('inedges',  node)
        self.track_written('nodes',  None)
        return self.graph.add_node(node)

    def _add_edge(self, obj):
        assert isinstance(obj, Edge)
        assert obj not in self.graph.edges(), '%s already inserted' % obj

        self.track_written('obj', obj)
        self.track_read('obj', obj.source)
        self.track_read('obj', obj.target)
        self.track_written('outedges', obj.source)
        self.track_written('inedges',  obj.target)
        self.track_written('edges',  None)
        return self.graph.add_edge(obj)

    def out_edges(self, node):
        self.track_read('outedges', node)
        return self.graph.out_edges(node)

    def in_edges(self, node):
        self.track_read('inedges', node)
        return self.graph.in_edges(node)

    def nodes(self):
        self.track_read('nodes', None)
        return self.graph.nodes()

    def edges(self):
        self.track_read('edges', None)
        return self.graph.edges()

    def remove_node(self, obj):
        return self.graph.remove_node(obj)

    def remove_edge(self, obj):
        return self.graph.remove_edge(obj)

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
            self.tracked_operation = op
            self.dependency_tracker.start_tracking()

    def stop_tracking(self, obj, error=False):
        node = None
        if self.dependency_tracker is not None:
            assert(self.tracked_operation is not None)
            node = self.dependency_tracker.stop_tracking(self, obj, self.tracked_operation, error=error)
            self.tracked_operation = None

        return node

    def set_params(self, ae, obj, params):
        for name, value in params.items():
            self.set_param_value(ae, name, obj, value)

    def insert_obj(self, ae, obj, parent, local=True, nodes=True, edges=True):
        """ Inserts one or multiple objects into the layer.

        Args:
            :param obj: Object(s) to be inserted.
            :type  obj: :class:`mcc.graph.Edge`, :class:`mcc.graph.GraphObj`, :class:`mcc.framework.Layer.Node`, a list or set of these.

        Returns:
            set of actually inserted nodes and edges
        """
        inserted = set()

        if isinstance(obj, Edge) and edges:
            missing = {obj.source, obj.target}.difference(self.graph.nodes())
            assert len(missing) == 0, "Missing nodes detected during edge creation: %s.\n" \
                                      "Please consider creating the edge %s by " \
                                      "transforming edges and not during node transformation. " \
                                      "Alternatively use a BatchTransform." \
                                      % (missing, obj)

            # local insertions are restricted to edges between nodes whose parents
            # are already connected (or have the same parent)
            if local:
                if isinstance(parent, Edge):
                    # check that connected nodes either belong to one of
                    # the parents or are newly inserted
                    source_parents = self.associated_objects(ae.layer.name, obj.source)
                    target_parents = self.associated_objects(ae.layer.name, obj.target)

                    if len(source_parents) == 0:
                        source_parents = {parent}

                    if len(target_parents) == 0:
                        target_parents = {parent}

                    if len(source_parents & target_parents) == 0:
                        if parent in target_parents:
                            assert parent.source in source_parents, \
                                "Locality not given when inserting edge %s, " \
                                "unexpected source. Please use BatchTransform instead." \
                                % (obj)
                        if parent in source_parents:
                            assert parent.target in target_parents, \
                                "Locality not given when inserting edge %s, " \
                                "unexpected target. Please use BatchTransform instead." \
                                % (obj)
                else:
                    # check that there is an edge between parent objects
                    source_parents = self.associated_objects(ae.layer.name, obj.source)
                    target_parents = self.associated_objects(ae.layer.name, obj.target)

                    if len(source_parents) == 0:
                        source_parents = {parent}

                    if len(target_parents) == 0:
                        target_parents = {parent}

                    if len(source_parents & target_parents) == 0:
                        found = False
                        for p in source_parents:
                            for e in ae.layer.graph.out_edges(p):
                                if e.target in target_parents:
                                    found = True
                                    break

                        assert found, "Locality not given when inserting edge %s. " \
                                      "Please use BatchTransform instead." % (obj)

            inserted.add(self._add_edge(obj))
        elif isinstance(obj, Graph):
            raise NotImplementedError()
        elif isinstance(obj, (set, list, frozenset)):
            for o in obj:
                inserted.update(self.insert_obj(ae, o, parent=parent,
                                                       local=local,
                                                       nodes=nodes,
                                                       edges=edges))
        elif isinstance(obj, GraphObj):
            assert isinstance(obj.obj, (self.Node, Edge))
            tmp = self.insert_obj(ae, obj.obj, parent=parent,
                                               local=local,
                                               nodes=nodes,
                                               edges=edges)
            if len(tmp):
                self.set_params(ae, obj.obj, obj.params())
            inserted.update(tmp)
        elif isinstance(obj, self.Node) and nodes:
            if obj not in self.graph.nodes():
                self._add_node(obj)
            # If obj was already inserted, it was inserted during a
            # transformation to an edge, maybe even during a transformation
            # from another object. In order to track everything properly, we
            # add a dependency to the actual writing operation.
            # FIXME the multiple writer issue should be handled by the dependency graph
            self.track_read('obj', obj)
            inserted.add(obj)

        return inserted

    def untracked_get_params(self, obj):
        if isinstance(obj, Edge): # obj is an edge
            attributes = self.graph.edge_attributes(obj)
        else:
            # obj is a node
            attributes = self.graph.node_attributes(obj)

        if 'params' not in attributes:
            attributes['params'] = dict()

        return attributes['params']

    def _interlayer(self, obj):
        if isinstance(obj, Edge):
            attributes = self.graph.edge_attributes(obj)
        else:
            attributes = self.graph.node_attributes(obj)

        if 'interlayer' not in attributes:
            attributes['interlayer'] = dict()

        return attributes['interlayer']

    def associated_objects(self, target_layer, obj):
        assert isinstance(target_layer, str)

        interlayer = self._interlayer(obj)

        if target_layer not in interlayer:
            return set()

        return interlayer[target_layer]

    def _set_associated_objects(self, target_layer, obj, objects):
        assert isinstance(target_layer, str)
        assert isinstance(objects, set) or isinstance(objects, frozenset), "objects %s are of type %s"  %(objects, type(objects))
        assert target_layer != self.name

        interlayer = self._interlayer(obj)
        interlayer[target_layer] = objects

    def _mark_all_params_read(self, param, nodes=True, edges=True):
        if not self.dependency_tracker:
            return

        if nodes:
            for n in self.graph.nodes():
                if param in self.untracked_get_params(n):
                    self.dependency_tracker.track_read(self, n, param)
        if edges:
            for e in self.graph.edges():
                if param in self.untracked_get_params(e):
                    self.dependency_tracker.track_read(self, e, param)

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

        return self.untracked_get_param_candidates(param, obj)

    def untracked_get_param_candidates(self, param, obj):
        params = self.untracked_get_params(obj)

        if param in params and 'candidates' in params[param]:
            return params[param]['candidates']
        else:
            return set()

    def get_param_failed(self, param, obj):
        params = self.untracked_get_params(obj)

        if param in params:
            if 'failed' in params[param]:
                return params[param]['failed']

        return None

    def set_param_failed(self, param, obj, failed):
        assert failed is None or isinstance(failed, DecisionGraph.Failed)
        params = self.untracked_get_params(obj)

        assert param in params, "param %s not available on %s for %s" % (param,self,obj)

        if failed is None:
            del params[param]['failed']
        else:
            params[param]['failed'] = failed

    def untracked_clear_param_value(self, param, obj):
        params = self.untracked_get_params(obj)

        if param in params:
            if 'value' in params[param]:
                del params[param]['value']

    def untracked_clear_param_candidates(self, param, obj):
        params = self.untracked_get_params(obj)

        del params[param]

    def isset_param_value(self, ae, param, obj):
        return self.untracked_isset_param_value(param, obj)

    def untracked_isset_param_value(self, param, obj):
        params = self.untracked_get_params(obj)
        if param in params and 'value' in params[param]:
            return True

        return False

    def isset_param_candidates(self, ae, param, obj):
        return self.untracked_isset_param_candidates(param, obj)

    def untracked_isset_param_candidates(self, param, obj):
        params = self.untracked_get_params(obj)
        if param in params and 'candidates' in params[param]:
            return True

        return False

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

        self.track_written(param, obj)

        self.untracked_set_param_candidates(param, obj, candidates)

    def untracked_set_param_candidates(self, param, obj, candidates):
        params = self.untracked_get_params(obj)

        if param not in params:
            params[param] = dict()

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
        assert ae.check_acl(self, param, 'reads'), "read access to %s not granted" % param

        self.track_read(param, obj)

        return self.untracked_get_param_value(param, obj)

    def track_read(self, param, obj):

        if self.dependency_tracker:
            self.dependency_tracker.track_read(self, obj, param)

    def track_written(self, param, obj):

        if self.dependency_tracker:
            self.dependency_tracker.track_written(self, obj, param)

    def untracked_get_param_value(self, param, obj):
        params = self.untracked_get_params(obj)

        assert param in params, "%s not present for %s" % (param, obj)

        assert 'value' in params[param], "value not assigned for %s on %s" % (param, obj)
        return params[param]['value']

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

        self.track_written(param, obj)

        self.untracked_set_param_value(param, obj, value)

    def untracked_set_param_value(self, param, obj, value):
        params = self.untracked_get_params(obj)

        if param not in params:
            params[param] = { 'value' : value, 'candidates' : set() }
        else:
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

    def batch_map(self, data):
        """ Must be implemented by derived classes.

        Args:
            :param data: key = graph object, value = candidates
            :type  data: dict

        Returns:
            dictionary with key = graph object, value = set of candidates values

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

    def batch_assign(self, data, objects, blacklist):
        """ Must be implemented by derived classes.

        Args:
            :param data: key = graph object, value = candidates
            :type  data: dict
            :param objects: ordered objects (correspond to entries in blacklist)
            :type  objects: tuple
            :param blacklist: blacklisted combinations of values
            :type  blacklist: set of tuples

        Returns:
            dictionary with key = graph object, value = assigned value

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

    def check(self, obj):
        """ Must be implemented by derived classes.

        Raises:
            NotImplementedError
        """
        raise NotImplementedError()

    def batch_check(self, iterable):
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

    def _prepare_map(self, obj, candidates):
        self._state_check_EXPORTED()

        self._query_map(obj, candidates)

    def _prepare_assign(self, obj, candidates):
        self._state_check_EXPORTED()

        self._query_assign(obj, candidates)

    def run(self):
        self._state_check_WAITING()

        if self._wait_for_result():
            self.state = "READY"

    def _map(self, obj):
        self._state_check_READY()

        return self._parse_map(obj)

    def _assign(self, obj):
        self._state_check_READY()

        return self._parse_assign(obj)

    def check(self, obj):
        raise NotImplementedError()

    def transform(self, obj, target_layer):
        raise NotImplementedError()

    def batch_assign(self, data, objects, blacklist):
        # conservatively mark all nodes and edges accessed for the params in ACL
        for layer in self.acl:
            for param in self.acl[layer]['reads']:
                layer._mark_all_params_read(param)

        for obj, candidates in data.items():
            self._prepare_assign(obj, candidates)

        result = dict()
        for obj, candidates in data.items():
            result[obj] = self._assign(obj)

        return result

    def batch_map(self, data):
        # conservatively mark all nodes and edges accessed for the params in ACL
        for layer in self.acl:
            for param in self.acl[layer]['reads']:
                layer._mark_all_params_read(param)

        for obj, candidates in data.items():
            self._prepare_map(obj, candidates)

        result = dict()
        for obj, candidates in data.items():
            result[obj] = self._map(obj)

        return result


class DummyEngine(AnalysisEngine):
    """ Can be used for identity-tranformation.
    """
    def __init__(self, layer, target_layer, params=None):
        if params is not None:
            acl = { layer        : {'reads'  : set()},
                    target_layer : {'writes' : set()}}
            for param in params:
                acl[layer]['reads'].add(param)
                acl[target_layer]['writes'].add(param)

        AnalysisEngine.__init__(self, layer, None, acl=acl)
        self.params = params

    def transform(self, obj, target_layer):
        if isinstance(obj, Edge):
            assert(obj.source in target_layer.graph.nodes())
            assert(obj.target in target_layer.graph.nodes())

        if self.params is None:
            return obj

        params = dict()
        for p in self.params:
            if self.layer.isset_param_value(self, p, obj):
                params[p] = self.layer.get_param_value(self, p, obj)

        return GraphObj(obj, params=params)

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
        acl = { source_layer : {'reads' : set([source_param])}}

        AnalysisEngine.__init__(self, layer, param, acl=acl)
        self.source_layer = source_layer
        self.source_param = source_param

    def map(self, obj, candidates):
        src_objs = self.layer.associated_objects(self.source_layer.name, obj)
        assert len(src_objs) == 1
        return {self.source_layer.get_param_value(self, self.source_param, list(src_objs)[0])}

    def assign(self, obj, candidates):
        return list(candidates)[0]

class InheritEngine(AnalysisEngine):
    """ Inherits a parameter from neighbouring nodes.
    """
    def __init__(self, layer, param, out_edges=True, in_edges=True, target_param=None):
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
        if target_param is None:
            target_param = param
        else:
            acl = { layer : {'reads' : set([param])}}

        AnalysisEngine.__init__(self, layer, target_param, acl=acl)
        self.out_edges=out_edges
        self.in_edges=in_edges
        self.source_param = param

    def map(self, obj, candidates):
        candidates = set()

        if self.source_param != self.param:
            if self.layer.isset_param_value(self, self.source_param, obj):
                candidates.add(self.layer.get_param_value(self, self.source_param, obj))

        if self.out_edges:
            edges = self.layer.graph.out_edges(obj)

            for e in edges:
                if self.layer.isset_param_value(self, self.source_param, e.target):
                    candidates.add(self.layer.get_param_value(self, self.source_param, e.target))

        if self.in_edges:
            edges = self.layer.graph.in_edges(obj)

            for e in edges:
                if self.layer.isset_param_value(self, self.source_param, e.source):
                    candidates.add(self.layer.get_param_value(self, self.source_param, e.source))

        if len(candidates) > 1:
            logging.warning("Cannot inherit '%s' from source/target node unambiguously" % (self.source_param))
        elif len(candidates) == 0:
            logging.warning("No value for param '%s' for node %s\'s nodes." % (self.source_param, obj))

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
        if not hasattr(self, 'target_layer'):
            self.target_layer = ae.layer

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
        if not isinstance(obj, Edge):
            obj = obj.untracked_obj()
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

            # skip if candidates are already present
            if self.source_layer.untracked_isset_param_candidates(self.param, obj):
                logging.debug("skipping %s on %s, because candidates are already present: %s" \
                        % (self, obj, self.source_layer.untracked_get_param_candidates(self.param,obj)))
                continue

            # check if we can reuse old results
            candidates = self.source_layer.untracked_get_param_candidates(self.param, obj)
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

            self.source_layer.stop_tracking(obj)

        return True

class BatchMap(Map):
    def __init__(self, ae, name=''):
        Map.__init__(self, ae, name)

    def register_ae(self, ae):
        """
        Returns:
            False -- only a single analysis engine must be registered (which is given on construction)
        """
        # only one analysis engine can be registered
        assert(False)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        ae = self.analysis_engines[0]

        self.source_layer.start_tracking(self)

        # prepare data
        data = dict()
        for obj in iterable:
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            if self.source_layer.untracked_isset_param_value(ae, self.param, obj):
                continue

            candidates = self.source_layer.get_param_candidates(ae, self.param, obj)
            if len(candidates) == 0 or (len(candidates) == 1 and list(candidates)[0] == None):
                candidates = None

            if candidates is None:
                data[obj] = None
            else:
                data[obj] = set(candidates)

        # execute batch map
        result = ae.batch_map(data)
        assert len(result) == len(data)

        # insert results into layer
        for obj, new_candidates in result.items():

            candidates = self.source_layer.get_param_candidates(ae, self.param, obj)
            if len(candidates) == 0 or (len(candidates) == 1 and list(candidates)[0] == None):
                candidates = None

            if candidates is None:
                candidates = new_candidates
            else:
                if new_candidates is not None:
                    candidates &= new_candidates

            # update candidates for this parameter in layer object
            assert(candidates is not None)
            self.source_layer.set_param_candidates(ae, self.param, obj, candidates)

        self.source_layer.stop_tracking(None)

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

        for obj in iterable:
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            if self.source_layer.untracked_isset_param_value(self.param, obj):
                logging.debug("skipping %s for object %s" % (self, obj))
                continue

            self.source_layer.start_tracking(self)

            raw_cand   = self.source_layer.get_param_candidates(self.analysis_engines[0], self.param, obj)
            failed     = self.source_layer.get_param_failed(self.param, obj)
            bad_values = set()
            if failed is not None:
                bad_values = failed.bad_values()

            candidates = raw_cand - bad_values

            if len(candidates) == 0:
                logging.error("No candidates left for param '%s' of object %s." % (self.param, obj))
                # simulate write access to param
                self.source_layer.track_written(self.param, obj)
                # insert operation into decision graph
                node = self.source_layer.stop_tracking(obj, error=True)
                raise ConstraintNotSatisfied(node)

            result = self.analysis_engines[0].assign(obj, candidates)
            assert result in candidates

            self.source_layer.set_param_value(self.analysis_engines[0], self.param, obj, result)

            self.source_layer.stop_tracking(obj)

        return True

class BatchAssign(Assign):
    def __init__(self, ae, name=''):
        Assign.__init__(self, ae, name)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        ae = self.analysis_engines[0]

        self.source_layer.start_tracking(self)

        # prepare data
        failed = None
        data = dict()
        for obj in iterable:
            assert(self.check_source_type(obj))

            # skip if parameter was already selected
            if self.source_layer.untracked_isset_param_value(self.param, obj):
                logging.debug("skipping %s for object %s" % (self, obj))
                continue

            raw_cand   = self.source_layer.get_param_candidates(ae, self.param, obj)
            failed     = self.source_layer.get_param_failed(self.param, obj)
            bad_values = set()
            if failed is not None:
                bad_values = failed.bad_values()

            candidates = raw_cand - bad_values

            if len(candidates) == 0:
                logging.error("No candidates left for param '%s' of object %s." % (self.param, obj))
                # simulate write access to param
                self.source_layer.track_written(self.param, obj)
                # insert operation into decision graph
                node = self.source_layer.stop_tracking(None, error=True)
                raise ConstraintNotSatisfied(node)

            data[obj] = candidates

        objects = None
        bad_combinations = set()
        if failed is not None:
            objects, bad_combinations = failed.bad_combinations()
            assert len(objects) == len(data), "Failed has %s objects but passing %s" % (objects, data.keys())

        # execute batch assign
        #  remark: we assume that data will not be modified by ae (can we enforce this?)
        # FIXME we need better feedback from the external analysis engine
        #     idea: let ExternalAnalysisEngine raise exception containing culprits
        result = ae.batch_assign(data, objects, bad_combinations)
        if not isinstance(result, dict) and result == False:
            # simulate write access to param
            for obj in data.keys():
                self.source_layer.track_written(self.param, obj)
            node = self.source_layer.stop_tracking(None, error=True)
            raise ConstraintNotSatisfied(node)

        assert len(result) == len(data)

        for obj, value in result.items():
            assert value in data[obj]
            self.source_layer.set_param_value(ae, self.param, obj, value)

        self.source_layer.stop_tracking(None)

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
        if hasattr(ae, 'target_layer'):
            assert target_layer == ae.target_layer
        self.target_layer = target_layer

        Operation.__init__(self, ae, name)

        if 'writes' not in ae.acl[self.source_layer]:
            ae.acl[self.source_layer]['writes'] = set()

        if self.target_layer not in ae.acl:
            ae.acl[self.target_layer] = { 'writes' : set() }

        if 'writes' not in ae.acl[self.target_layer]:
            ae.acl[self.target_layer]['writes'] = set()

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
            raise Exception("Analysis engine %s does not have nodetypes %s of target layer: %s" % (ae,
                self.target_layer.node_types(), ae.target_types()))

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

            # skip if parameter was already selected
            if len(self.source_layer.associated_objects(self.target_layer.name, obj)) > 0:
                logging.info("Not transforming %s on layer %s" % (obj, self.source_layer))
                continue

            self.source_layer.start_tracking(self)

            new_objs = self.analysis_engines[0].transform(obj, self.target_layer)
            if not new_objs:
                logging.warning("transform() did not return any object (returned: %s)" % new_objs)
            else:
                # remark: also returns already existing objects
                inserted_nodes = self.target_layer.insert_obj(self.analysis_engines[0],
                                                              new_objs,
                                                              parent=obj,
                                                              edges=False)
                inserted_edges = self.target_layer.insert_obj(self.analysis_engines[0],
                                                              new_objs,
                                                              parent=obj,
                                                              nodes=False)
                inserted = inserted_nodes | inserted_edges
                assert len(inserted) > 0

                for o in inserted:
                    if not isinstance(o, Edge):
                        assert isinstance(o.untracked_obj(),
                                          self.target_layer.node_types()), \
                               "%s does not match types %s" \
                                    % (o.untracked_obj(), self.target_layer.node_types())

                self.source_layer._set_associated_objects(self.target_layer.name, obj, inserted)

                for o in inserted:
                    src = self.target_layer.associated_objects(self.source_layer.name, o)
                    if src is None:
                        src = { obj }
                    elif isinstance(src, set) or isinstance(src, frozenset):
                        src.add(obj)
                    else:
                        # should never happen, because src must be a set
                        src = { src, obj }
                    self.target_layer._set_associated_objects(self.source_layer.name, o, src)

            self.source_layer.stop_tracking(obj)

        return True


class BatchTransform(Transform):
    """ Implements the transform operation as a batch operation.

        The batch operation will only insert a single node into the dependency graph.
        It is required for operations that insert non-local edges.
    """
    def __init__(self, ae, target_layer, name=''):
        Transform.__init__(self, ae, target_layer, name)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        self.source_layer.start_tracking(self)

        objects  = set()
        new_objs = dict()
        inserted_nodes = dict()

        # first pass: call transform() on all objects and fill new_objs and insert nodes
        for (index ,obj) in enumerate(iterable):

            # skip if parameter was already selected
            if len(self.source_layer.associated_objects(self.target_layer.name, obj)) > 0:
                logging.info("Not transforming %s on layer %s" % (obj, self.source_layer))
                continue

            objects.add(obj)

            new_objs[obj] = self.analysis_engines[0].transform(obj, self.target_layer)
            if not new_objs[obj]:
                logging.warning("transform() did not return any object (returned: %s)" % new_objs[obj])
            else:
                # remark: also returns already existing objects
                inserted_nodes[obj] = self.target_layer.insert_obj(self.analysis_engines[0],
                                                                   new_objs[obj],
                                                                   parent=obj,
                                                                   local=False,
                                                                   edges=False)
        # second pass: insert edges into target_layer
        for obj, new in new_objs.items():
            inserted_edges = self.target_layer.insert_obj(self.analysis_engines[0],
                                                          new,
                                                          parent=obj,
                                                          local=False,
                                                          nodes=False)
            inserted = inserted_nodes[obj] | inserted_edges
            assert len(inserted) > 0

            for o in inserted:
                if not isinstance(o, Edge):
                    assert isinstance(o.untracked_obj(),
                                      self.target_layer.node_types()), \
                           "%s does not match types %s" \
                                % (o.untracked_obj(), self.target_layer.node_types())

            self.source_layer._set_associated_objects(self.target_layer.name, obj, inserted)

            for o in inserted:
                src = self.target_layer.associated_objects(self.source_layer.name, o)
                if src is None:
                    src = { obj }
                elif isinstance(src, set) or isinstance(src, frozenset):
                    src.add(obj)
                else:
                    # should never happen, because src must be a set
                    src = { src, obj }
                self.target_layer._set_associated_objects(self.source_layer.name, o, src)

        self.source_layer.stop_tracking(frozenset(objects))

        return True


class Check(Operation):
    """ Implements the check operation, which is used for admission testing.
    """
    def __init__(self, ae, name=''):
        Operation.__init__(self, ae, name)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        for obj in iterable:
            assert(self.check_source_type(obj))

            self.source_layer.start_tracking(self)

            # Note: We also re-run checks for nodes have not been
            #       rolled back properly. An entire check operation
            #       is marked invalidated if at least one of its nodes
            #       was removed from the dependency graph. Other nodes
            #       may still persist but we re-run the check anyway.
            #       This could be omitted by checking whether there
            #       is already a node in the graph.
            #       For the moment, however, we re-run the check to
            #       see whether its dependencies changed.

            for ae in self.analysis_engines:
                result = ae.check(obj)
                if isinstance(result, DecisionGraph.Node):
                    raise ConstraintNotSatisfied(result)
                elif not result:
                    # we must stop tracking (to insert a new node) and
                    # fail on this node
                    node = self.source_layer.stop_tracking(obj, error=True)
                    logging.error("Check failed on object %s" % obj)
                    raise ConstraintNotSatisfied(node)

            self.source_layer.stop_tracking(obj)

        return True


class BatchCheck(Check):
    """ Implements the check operation, which is used for admission testing.
    """
    def __init__(self, ae, name=''):
        Check.__init__(self, ae, name)

    def execute(self, iterable):
        logging.info("Executing %s" % self)

        self.source_layer.start_tracking(self)

        for obj in iterable:
            assert(self.check_source_type(obj))

        for ae in self.analysis_engines:
            result = ae.batch_check(iterable)

            if isinstance(result, DecisionGraph.Node):
                raise ConstraintNotSatisfied(result)
            elif not result:
                # we must stop tracking (to insert a new node) and
                # fail on this node
                node = self.source_layer.stop_tracking(None, error=True)
                raise ConstraintNotSatisfied(node)

        # remark: the same operation should never be used in multiple steps
        self.source_layer.stop_tracking(None)

        return True

class ConstraintNotSatisfied(Exception):
    def __init__(self, node):
        super().__init__()
        self.node = node

        assert isinstance(node, DecisionGraph.Node)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return self.node.__repr__()

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
    def __init__(self, layer, target_layer, params):
        Transform.__init__(self, DummyEngine(layer, target_layer, params), target_layer)

class CopyEdgeTransform(Transform):
    """ Transform operation that returns the edges found in the layer.
    """
    def __init__(self, layer, target_layer, params):
        Transform.__init__(self, DummyEngine(layer, target_layer, params), target_layer)

class CopyNodeStep(NodeStep):
    """ Copies nodes to target layer.
    """
    def __init__(self, layer, target_layer, params):
        NodeStep.__init__(self, CopyNodeTransform(layer, target_layer, params))

class CopyEdgeStep(EdgeStep):
    """ Copies edges to target layer.
    """
    def __init__(self, layer, target_layer, params):
        EdgeStep.__init__(self, CopyEdgeTransform(layer, target_layer, params))

class CopyMappingStep(NodeStep):
    """ Copies 'mapping' parameter of the nodes to the target layer.
    """
    def __init__(self, layer, target_layer, target_param='mapping', source_param='mapping'):
        ce = CopyEngine(target_layer, target_param, layer, source_param=source_param)
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
        ie = InheritEngine(layer, param, out_edges=True, in_edges=False)
        NodeStep.__init__(self, Map(ie))
        self.add_operation(Assign(ie))

class InheritFromBothStep(NodeStep):
    """ Inherits a parameter value from neighbouring source and target nodes.
    """

    def __init__(self, layer, param, target_param=None, engines=None):
        ie = InheritEngine(layer, param=param, target_param=target_param)
        op = Map(ie)
        if engines is not None:
            for ae in engines:
                op.register_ae(ae)
        NodeStep.__init__(self, op)
        self.add_operation(Assign(ie))
