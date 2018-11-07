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
    def __init__(self, layer, param, obj, candidates):
        super().__init__()
        self.layer      = layer
        self.param      = param
        self.obj        = obj
        self.candidates = candidates

    def __str__(self):
        return 'MapNode: layer={}\n, param={}\n, obj={}\n, candidates={}\n'.format(self.layer, self.param, self.obj, self.candidates)

class AssignNode(Node):
    """Represents an Assign Operation in the Dependency Graph"""
    def __init__(self, layer, param, obj, value):
        super().__init__()
        self.layer = layer
        self.param = param
        self.obj   = obj
        self.value = value

    def __str__(self):
        return 'AssignNode: Layer= {}\n, param={}\n, obj={}\n, value={}\n'.format(self.layer, self.param, self.obj, self.value)


class TransformNode(Node):
    """Represents a Transform Operation in the Dependency Graph"""
    def __init__(self, source_layer, target_layer, obj, inserted):
        super().__init__()
        self.source_layer = source_layer
        self.target_layer = target_layer
        self.obj          = obj
        self.inserted     = inserted

        def __str__(self):
            return 'source_layer {}\n, Target_layer {}\n, obj {}\n, inserted {}\n'.format(self.source_layer, self.target_layer, self.obj, self.inserted)

class DecisionGraph(Graph):
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
        assert(isinstance(obj, MapNode) or isinstance(obj, AssignNode) or isinstance(obj, TransformNode))

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
            used_candidates.add(edge.target.value)

        return used_candidates

    def shortest_path(self, source, target):
        return nx.shortest_path(self.graph, source, target)

    def append_node(self, node):
        assert(isinstance(node, MapNode) or isinstance(node, AssignNode) or isinstance(node, TransformNode))

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

    def add_transform_node(self, source_layer, target_layer, obj, inserted, attr_index):
        node = TransformNode(source_layer, target_layer, obj, inserted)
        node.attribute_index = attr_index
        self.append_node(node)

    def add_map_node(self, source_layer, param, obj, candidates, attr_index):
        node = MapNode(source_layer, param, obj, candidates)
        node.attribute_index = attr_index
        self.append_node(node)

    def add_assign_node(self, source_layer, param, obj, value, attr_index):
        node = AssignNode(source_layer, param, obj, value)
        node.attribute_index = attr_index
        self.append_node(node)

    def write_dot(self, filename):

        with open(filename, 'w') as file:
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
        self.dec_graph = DecisionGraph()
        self.backtracking_try = 0

    def execute(self):
        """ Executes the registered steps sequentially.
        """

        while not self._backtrack_execute():
            pass

        self._output_layer(self.steps[-1].target_layer)

    def _backtrack_execute(self):
        print()

        self.backtracking_try += 1

        last_step = 0
        if self.backtracking_try > 1:
            last_step = self.dec_graph.last_step_index

        logging.info('Backtracking Try {}, Last Step {}'.format(self.backtracking_try, last_step))
        for step in self.steps[last_step:]:

            previous_step = self._previous_step(step)
            if not Registry._same_layers(previous_step, step):
                logging.info("Creating layer %s" % step.target_layer)
                if previous_step is not None:
                    self._output_layer(previous_step.target_layer)

            try:
                self.dec_graph.set_step_index(self.steps.index(step))
                step.execute(self.dec_graph)

            except ConstraintNotSatisfied as cns:
                logging.info('{} failed:'.format(cns.obj))

                current = self.dec_graph.current

                head = self._mark_subtree_as_bad(cns.layer, cns.param, cns.obj)
                if head is None or self._candidates_exhausted(head):
                    current = self.dec_graph.current
                    head = self._get_last_valid_assign(current)
                    if head is None:
                        raise Exception('No config could be found')

                    self._mark_subtree_as_bad(head.layer, head.param, head.obj)

                self._revert_subtree(head, current)
                head = list(self.dec_graph.in_edges(head))[0].source

                self.dec_graph.set_operation_index(head.operation_index)
                self.dec_graph.set_step_index(head.step_index)

                # reset the pointer at the dependency tree that points to the
                # leaf in the current path
                self.dec_graph.current = head
                return False

            except Exception as ex:
                self._output_layer(step.target_layer, suffix='-error')
                import traceback
                traceback.print_exc()
                raise(ex)
        return True

    def _get_last_valid_assign(self, start):

        for edge in self.dec_graph.in_edges(start):
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
        params = anode.layer._get_params(anode.obj)
        candidates = params[anode.param]['candidates']
        used_candidates = self.dec_graph.get_used_candidates(anode)

        if candidates == used_candidates:
            return True

        return False

    def _revert_subtree(self, start, end):
        # iterate over the path, and revert the changes
        for node in self.dec_graph.shortest_path(start, end):
            assert(not node.valid)
            if isinstance(node, AssignNode):
                node.layer._set_param_value(node.param, node.obj, None)
            elif isinstance(node, MapNode):
                node.layer._set_param_candidates(node.param, node.obj, set())
            elif isinstance(node, Transform):
                node.source_layer._set_param_value(node.target_layer.name, node.obj, set())
                for o in node.inserted:
                    node.target_layer._set_param_value(node.source_layer.name, o, None)

    def _mark_subtree_as_bad(self, layer, param, culprit):
        # look for the last assign node that assings the culprit
        for node in self.dec_graph.valid_nodes()[::-1]:
            if not isinstance(node, AssignNode):
                continue

            if node.obj == culprit and node.layer == layer and node.param == param:
                node.valid = False
                self.dec_graph.mark_subtree_as_bad(node)
                return node

        return None

    def decision_graph(self):
        return self.dec_graph

    def write_analysis_engine_dependency_graph(self, outfile='AeDepGraph.dot'):
        analysis_engines = set()
        engines_id       = set()
        layers           = set()
        read_params      = set()
        write_params     = set()

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
                        read_params.add((en, str(layer).replace('-', '_'), param.replace('-', '_')))

                if 'writes'in ae.acl[layer]:
                    for param in ae.acl[layer]['writes']:
                        if param == None:
                            continue
                        write_params.add((en, str(layer).replace('-', '_'), param.replace('-', '_')))

        # TODO we might want to force the params from the same layer to the same rank for better readability
        with open(outfile, 'w') as file:
            file.write('digraph {\n')
            file.write('rankdir=LR;\n')

            for e in engines_id:
                e = e.replace('-', '_')
                node = '{0} [label="<{0}>",shape=octagon,colorscheme=set39,fillcolor=4,style=filled];\n'.format(e)
                file.write(node)

            # add params as nodes
            for (param_id, layer, param_label) in {(param, layer, param) for (ae, layer, param) in read_params | write_params}:
                node = '{0}{1} [label="{1}.{2}", shape=oval]\n'.format(param_id, layer, param_label)
                file.write(node)

            # edge AnalysisEngine to parameter e.g. CopyeEnine -> mapping
            for (ae, param_id) in {(ae, param+layer) for (ae, layer, param) in write_params}:
                edge = '{0} -> {1}\n'.format(ae, param_id)
                file.write(edge)

            # edge AnalysisEngine to parameter e.g. mapping -> CopyEngine
            for (ae, param_id) in {(ae, param+layer) for (ae, layer, param) in read_params}:
                edge = '{1} -> {0}\n'.format(ae, param_id)
                file.write(edge)

            file.write('}\n')

