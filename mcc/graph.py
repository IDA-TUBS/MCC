"""
Description
-----------

Implements graph-related data structures.
Serves as a wrapper to networkx so that we could potentially replace it with another graph library.

:Authors:
    - Johannes Schlatow

"""
import networkx as nx
import logging

class GraphObj:
    """ Captures dangling graph objects, i.e. Edge or Node, and its parameters.

    Used by :func:`mcc.framework.AnalysisEngine.transform()`.
    """

    def __init__(self, obj, params=None):
        """
        Args:
            :param obj: Node or Edge wrapped by this class.
            :param params: params of obj
            :type  params: dict or None
        """
        self.obj = obj
        self._params = params

    def is_edge(self):
        if isinstance(self.obj, Edge):
            return True

        return False

    def params(self):
        """
        Returns:
            params
        """
        if self._params is None:
            return dict()

        return self._params

class Edge:
    """ Edge object used by :class:`Graph`.
    """
    def __init__(self, source, target):
        self.source = source
        self.target = target
        assert(not isinstance(self.source, list))
        assert(not isinstance(self.target, list))

    def __repr__(self):
        return "%s -> %s" % (self.source, self.target)

class Graph:
    """ Wrapper for :class:`nx.MultiDiGraph`.
    """
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_node(self, obj):
        self.graph.add_node(obj)
        return obj

    def create_edge(self, source, target):
        e = Edge(source, target)
        return self.add_edge(e)

    def add_edge(self, edge):
        assert(isinstance(edge, Edge))
        if edge.source not in self.graph.nodes():
            logging.error("source node '%s' does not exist" % edge.source)

        if edge.target not in self.graph.nodes():
            logging.error("target node '%s' does not exist" % edge.target)

        self.graph.add_edge(edge.source, edge.target, key=edge)
        return edge

    def in_edges(self, node):
        edges = set()
        for (s, t, e) in self.graph.in_edges(node, keys=True):
            edges.add(e)

        return edges

    def out_edges(self, node):
        edges = set()
        for (s, t, e) in self.graph.out_edges(node, keys=True):
            edges.add(e)

        return edges

    def edges(self):
        edges = set()
        for (s, t, e) in self.graph.edges(keys=True):
            edges.add(e)

        return edges

    def node_attributes(self, node):
        return self.graph.node[node]

    def edge_attributes(self, edge):
        return self.graph.edges[edge.source,edge.target,edge]

    def nodes(self):
        return self.graph.node.keys()


class Node():
    """Represents a Node in the Dependency Graph"""
    def __init__(self):
        self.valid           = True
        self.step_index      = 0
        self.operation_index = 0
        self.attribute_index = 0
        self.operation       = None
        self.param           = ''


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

