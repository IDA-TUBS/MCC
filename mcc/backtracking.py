"""
Description
-----------

Implements backtracking-related data structures.

:Authors:
    - Dustin Frey

"""

import networkx as nx
from mcc.framework import *
from mcc.graph import *

class Node():
    """Represents a Node in the Dependency Graph"""
    def __init__(self):
        self.valid           = True
        self.step_index      = 0
        self.operation_index = 0
        self.attribute_index = 0
        self.operation       = None


class MapNode(Node):
    """Represents a Map Operation in the Dependency Graph"""
    def __init__(self, layer, param, value, candidates):
        super().__init__()
        self.layer      = layer
        self.param      = param
        self.value      = value
        self.candidates = candidates

    def __str__(self):
        return 'MapNode: Layer={}\n, Param={}\n, value={}\n, candidates={}\n'.format(self.layer, self.param, self.value, self.candidates)

class AssignNode(Node):
    """Represents an Assign Operation in the Dependency Graph"""
    def __init__(self, layer, param, value, match):
        super().__init__()
        self.layer = layer
        self.param = param
        self.value = value
        self.match = match

    def __str__(self):
        return 'AssignNode: Layer= {}\n, Params={}\n, value={}\n, match={}\n'.format(self.layer, self.param, self.value, self.match)

class DependNode(Node):
    """Represents parameters used in a Map operation"""
    def __init__(self, layer, params, dep):
        super().__init__()
        self.layer  = layer
        self.params = params
        self.dep    = dep

    def __str__(self):
        return 'DependNode: Layer={}\n, Params={}\n, Dependencies={}\n'.format(self.layer, self.params, self.dep)

class TransformNode(Node):
    """Represents a Transform Operation in the Dependency Graph"""
    def __init__(self, source_layer, target_layer, value, inserted):
        super().__init__()
        self.source_layer = source_layer
        self.target_layer = target_layer
        self.value        = value
        self.inserted     = inserted

        def __str__(self):
            return 'source_layer {}\n, Target_layer {}\n, value {}\n, inserted {}\n'.format(self.source_layer, self.target_layer, self.value, self.inserted)

class DependencyGraph(Graph):
    """ Dependency Graph saves Operations executed by the BacktrackingRegistry
        and is used to revert to a previous state.
    """
    def __init__(self):
        # the current node in the path
        super().__init__()
        self.current         = None
        self.root            = None

        self.last_operation_index = 0
        self.last_operation       = None
        self.last_step_index      = 0
        self.last_step            = None

    def add_node(self, obj):
        assert(isinstance(obj, MapNode) or isinstance(obj, AssignNode) or isinstance(obj, DependNode) or isinstance(obj, TransformNode))

        if isinstance(obj, DependNode):
            super().add_node(obj)
            return

        if self.root is None:
            self.root = obj

        self.current = obj
        super().add_node(obj)

    def set_operation(self, operation):
        self.last_operation = operation

    def set_operation_index(self, operation_index):
        self.last_operation_index = operation_index

    def set_step_index(self, step_index):
        self.last_step_index = step_index

    def set_step(self, step):
        self.last_step = step

    def valid_nodes(self):
        nodes = []
        for node in self.nodes():
            if node.valid:
                nodes.append(node)
        return nodes

    def get_used_candidates(self, anode):
        aprev = None
        for edge in self.in_edges(anode):
            if edge.source.valid:
                aprev = edge.source
                break

        used_candidates = set()

        for edge in self.out_edges(aprev):
            if not isinstance(edge.target, AssignNode):
                continue
            used_candidates.add(edge.target.match)

        return used_candidates

    def shortest_path(self, source, target):
        return nx.shortest_path(self.graph, source, target)

    def append_node(self, node):
        assert(isinstance(node, MapNode) or isinstance(node, AssignNode) or isinstance(node, DependNode) or isinstance(node, TransformNode))

        current              = self.current
        node.step_index      = self.last_step_index
        node.operation_index = self.last_operation_index
        node.operation       = self.last_operation

        self.add_node(node)

        # skip creating an edge on first node
        if current is None:
            return

        edge = Edge(current, node)
        self.add_edge(edge)

    def mark_subtree_as_bad(self, node):
        for (s, t, e) in self.graph.out_edges(node, keys=True):
            t.valid = False
            self.mark_subtree_as_bad(t)

    def write_dot(self):

        with open('DependencyGraph.dot', 'w') as file:
            file.write('digraph {\n')

            nodes = [node for node in self.graph.nodes()]

            for node in nodes:
                if node is None:
                    print('Node is none')
                node_str = ''
                not_valid = ']\n'

                if not node.valid:
                    not_valid = ', colorscheme=set39,fillcolor=5, style=filled]\n'
                if isinstance(node, MapNode):
                    node_str = '"{0}" [label="{1}", shape=hexagon'.format(nodes.index(node), (node))
                elif isinstance(node, AssignNode):
                    node_str = '"{0}" [label="{1}", shape=circle'.format(nodes.index(node), (node))
                elif isinstance(node, DependNode):
                    node_str = '"{0}" [label="{1}", shape=triangle'.format(nodes.index(node), (node))
                elif isinstance(node, TransformNode):
                    node_str = '"{0}" [label="{1}", shape=egg'.format(nodes.index(node), (node))

                node_str += not_valid

                file.write(node_str)

            for (source, target) in self.graph.edges():
                edge = '{} -> {}\n'.format(nodes.index(source), nodes.index(target))
                file.write(edge)

                pass
            file.write('}\n')

class BacktrackRegistry(Registry):
    """ Implements/manages a cross-layer model.

    Layers and transformation steps are stored, managed, and executed by this class.
    Uses Backtracking to find a valid config instead of failing
    """
    def __init__(self):
        super().__init__()
        self.dep_graph = DependencyGraph()
        self.backtracking_try = 0

    def execute(self):
        """ Executes the registered steps sequentially.
        """

        while not self._backtrack_execute():
            pass

        self._output_layer(self.steps[-1].target_layer)
        self.dep_graph.write_dot()

    def _backtrack_execute(self):
        print()

        self.backtracking_try += 1

        last_step = 0
        if self.backtracking_try > 1:
            last_step = self.dep_graph.last_step_index

        logging.info('Backtracking Try {}, Last Step {}'.format(self.backtracking_try, last_step))
        for step in self.steps[last_step:]:

            previous_step = self._previous_step(step)
            if not Registry._same_layers(previous_step, step):
                logging.info("Creating layer %s" % step.target_layer)
                if previous_step is not None:
                    self._output_layer(previous_step.target_layer)

            try:
                self.dep_graph.set_step_index(self.steps.index(step))
                step.execute(self.dep_graph)

            except ConstraintNotStatisfied as cns:
                logging.info('{} failed:'.format(cns.obj))

                current = self.dep_graph.current

                head = self._mark_subtree_as_bad(cns.layer, cns.param, cns.obj)
                if head is None or self._candidates_exhausted(head):
                    current = self.dep_graph.current
                    head = self._get_last_valid_assign(current)
                    if head is None:
                        raise Exception('No config could be found')

                    self._mark_subtree_as_bad(head.layer, head.param, head.value)

                self._revert_subtree(head, current)
                head = list(self.dep_graph.in_edges(head))[0].source

                self.dep_graph.set_operation_index(head.operation_index)
                self.dep_graph.set_step_index(head.step_index)

                # reset the pointer at the dependency tree that points to the
                # leaf in the current path
                self.dep_graph.current = head
                return False

            except Exception as ex:
                self._output_layer(step.target_layer, suffix='-error')
                raise(ex)
        return True

    def _get_last_valid_assign(self, start):

        for edge in self.dep_graph.in_edges(start):
            if not edge.source.valid:
                continue

            # if non assign operation just go higher
            if not isinstance(start, AssignNode):
                return self._get_last_valid_assign(edge.source)

            if self._candidates_exhausted(start):
                return self._get_last_valid_assign(edge.source)

            return start

        return None

    def _candidates_exhausted(self, anode):
        params = anode.layer._get_params(anode.value)
        candidates = params[anode.param]['candidates']
        used_candidates = self.dep_graph.get_used_candidates(anode)

        if candidates == used_candidates:
            return True

        return False

    def _revert_subtree(self, start, end):
        # iterate over the path, and revert the changes
        for node in self.dep_graph.shortest_path(start, end):
            assert(not node.valid)
            if isinstance(node, AssignNode):
                node.layer._set_param_value(node.param, node.value, None)
            elif isinstance(node, MapNode):
                node.layer._set_param_candidates(node.param, node.value, set())
            elif isinstance(node, Transform):
                node.source_layer._set_param_value(node.target_layer.name, node.value, set())
                for o in node.inserted:
                    node.target_layer._set_param_value(node.source_layer.name, o, None)

    def _mark_subtree_as_bad(self, layer, param, culprit):
        # look for the last assign node that assings the culprit
        for node in self.dep_graph.valid_nodes()[::-1]:
            if not isinstance(node, AssignNode):
                continue

            if node.value == culprit and node.layer == layer and node.param == param:
                node.valid = False
                self.dep_graph.mark_subtree_as_bad(node)
                return node

        return None

    def write_analysis_engine_dependency_graph(self):
        analysis_engines = set()
        engines_id       = set()
        layers           = set()
        params           = set()

        for step in self.steps:
            for op in step.operations:
                analysis_engines.update(op.analysis_engines)

        print()

        for ae in analysis_engines:
            en = '{}'.format(type(ae).__name__)
            engines_id.add(en)

            for layer in ae.acl:
                la = str(layer).replace('-', '_')
                layers.add(la)
                if 'reads' in ae.acl[layer]:
                    for param in ae.acl[layer]['reads']:
                        if param == None:
                            continue
                        params.add((en, str(layer).replace('-', '_'), param.replace('-', '_')))

                if 'writes'in ae.acl[layer]:
                    for param in ae.acl[layer]['writes']:
                        if param == None:
                            continue
                        params.add((en, str(layer).replace('-', '_'), param.replace('-', '_')))

        with open('AeDepGraph.dot', 'w') as file:
            file.write('digraph {\n')

            for e in engines_id:
                e = e.replace('-', '_')
                node = '{0} [label="<{0}>",shape=octagon,colorscheme=set39,fillcolor=4,style=filled];\n'.format(e)
                file.write(node)

            for l in layers:
                l = l.replace('-', '_')
                node = '{0} [label="<{0}>",shape=parallelogram,colorscheme=set39, fillcolor=5,style=filled];\n'.format(l)
                file.write(node)

            # add params as nodes
            for (param_id, param_label) in {(param+layer, param) for (ae, layer, param) in params}:
                node = '{0} [label="{1}", shape=oval]\n'.format(param_id, param_label)
                file.write(node)

            # edge AnalysisEngine to parameter e.g. CopyeEnine -> mapping
            for (ae, param_id) in {(ae, param+layer) for (ae, layer, param) in params}:
                edge = '{0} -> {1}\n'.format(ae, param_id)
                file.write(edge)

            # edge param -> Layer
            for (layer, param) in {(layer, param) for (ae, layer, param) in params}:
                edge = '{0}{1} -> {1}\n'.format(param, layer)
                file.write(edge)

            file.write('}\n')

