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

    def valid_nodes(self):
        return self.nodes().filter(lambda x: x.valid)

class Node():
    """Represents a Node in the Dependency Graph"""
    def __init__(self):
        self.valid = True

class MapNode(Node):
    def __init__(self, layer, param, candidates, value):
        self.layer      = layer
        self.param      = param
        self.value      = value
        self.candidates = candidates

    def __str__(self):
        return 'Layer={}, Param={}, value={}, candidates={}'.format(self.layer, self.param, self.value, self.candidates)

class AssignNode(Node):
    """description"""
    def __init__(self, layer, param, value, match=None):
        self.layer = layer
        self.param = param
        self.value = value
        self.match = match

    def __str__(self):
        return 'Layer= {}, Param={}, value={}, match={}'.format(self.layer, self.param, self.value,
                self.match)

class DependNode(Node):
    """description"""
    def __init__(self, layer, params, dep):
        self.layer  = layer
        self.params = params
        self.dep    = dep

    def __str__(self):
        return 'Layer={}, Param={}, Dependencies={}'.format(self.layer, self.param, dep)

class DependencyGraph(Graph):
    def __init__(self):
        # the current node in the path
        super().__init__()
        self.current = None

    def add_node(self, obj):
        assert(isinstance(obj, MapNode) or isinstance(obj, AssignNode) or isinstance(obj, DependNode))

        if isinstance(obj, DependNode):
            super().add_node(obj)
            return

        self.current = obj
        super().add_node(obj)

    def next_legal_node(self):
        for node in self.graph.out_edges(self.current):
            if isinstance(node, DependNode):
                continue

    def set_next_legal_node(self):
        for (s, t, e) in self.graph.out_edges(current, keys=True):
            if t.valid:
                current = t
                return

    def append_node(self, node):
        assert(isinstance(node, MapNode) or isinstance(node, AssignNode) or isinstance(node, DependNode))

        current = self.current
        self.add_node(node)

        # TODO: wie kann es sein, dass wir ohne das if 190-210 kanten zu None haben ?
        if current is None:
            return
        edge = Edge(current, node)
        self.add_edge(edge)

    def find_map_node_from_assign_node(self, anode):
        for node in self.dep_graph.nodes():
            if not isinstance(node, MapNode) or not node.valid:
                continue

            if node.layer == bnode.layer and node.param == bnode.param and node.obj == bnode.obj:
                if node.valid:
                    return node
        return None

    def mark_subtree_as_bad(self, node):
        for (s, t, e) in self.graph.out_edges(node, keys=True):
            t.valid = False
            self.mark_subtree_bad(t)


    def write_dot(self):

        with open('DependencyGraph.dot', 'w') as file:
            file.write('digraph {\n')

            nodes = [node for node in self.graph.nodes()]

            for node in nodes:
                if node is None:
                    print('Node is none')
                node_str = ''
                if isinstance(node, MapNode):
                    node_str = '"{0}" [label="{0}", shape=hexagon]\n'.format(nodes.index(node))
                elif isinstance(node, AssignNode):
                    node_str = '"{0}" [label="{0}", shape=circle]\n'.format(nodes.index(node))
                elif isinstance(node, DependNode):
                    node_str = '"{0}" [label="{0}", shape=triangle]\n'.format(nodes.index(node))

                file.write(node_str)

            for (source, target) in self.graph.edges():
                edge = '{} -> {}\n'.format(nodes.index(source), nodes.index(target))
                file.write(edge)

                pass
            file.write('}\n')

