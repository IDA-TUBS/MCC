"""
Description
-----------

Implements graph-related data structures.
Serves as a wrapper to networkx so that we could potentially replace it with another graph library.

:Authors:
    - Johannes Schlatow

"""
from  networkx import MultiDiGraph
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
    """ Wrapper for :class:`networkx.MultiDiGraph`.
    """
    def __init__(self):
        self.graph = MultiDiGraph()

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

    def node_attributes(self, node, params=None):
        if params is None:
            return self.graph.node[node]
        else:
            filtered_attrs = { 'params' : dict() }
            for attr, val in self.graph.node[node].items():
                if attr == 'params':
                    for param, pval in val.items():
                        if param in params:
                            filtered_attrs['params'][param] = { 'value' : pval['value'], 'candidates' : None }
                else:
                    filtered_attrs[attr] = val

            return filtered_attrs

    def edge_attributes(self, edge, params=None):
        if params is None:
            return self.graph.edges[edge.source,edge.target,edge]
        else:
            filtered_attrs = { 'params' : dict() }
            for attr, val in self.graph.edges[edge.source,edge.target,edge].items():
                if attr == 'params':
                    for param, pval in val.items():
                        if param in params:
                            filtered_attrs['params'][param] = { 'value' : pval['value'], 'candidates' : None }
                else:
                    filtered_attrs[attr] = val

            return filtered_attrs

    def generate_ids(self):
        # TODO store (arbitrary) IDs as node and edge attributes
        raise NotImplementedError

    def nodes(self):
        return self.graph.node.keys()

    def export_filter(self, node_params, edge_params):
        self._node_params = node_params
        self._edge_params = edge_params

    def __getstate__(self):
        return GraphExporter(self, self._node_params, self._edge_params).__dict__

#    def __getstate__(self):
#        node_attrs = dict()
#        edge_attrs = dict()
#        for node in self.nodes():
#            node_attrs[node] = self.node_attributes(node, self.node_params_filter)
#        for edge in self.edges():
#            edge_attrs[edge] = self.edge_attributes(edge, self.edge_params_filter)
#
#        return { 'nodes' : self.nodes(),
#                 'edges' : self.graph.edges(keys=True),
#                 'node_attributes' : node_attrs,
#                 'edge_attributes' : edge_attrs}
#
#    def __setstate__(self, state):
#        self.graph = MultiDiGraph()
#        self.graph.add_nodes_from(state['nodes'])
#        self.graph.add_edges_from(state['edges'])
#
#        for node, attrs in state['node_attributes'].items():
#            for attr, aval in attrs.items():
#                self.node_attributes(node)[attr] = aval
#
#        for edge, attrs in state['edge_attributes'].items():
#            for attr, aval in attrs.items():
#                self.edge_attributes(edge)[attr] = aval

class GraphExporter(Graph):
    def __init__(self, graph, node_params, edge_params):
        self.graph = graph.graph.fresh_copy()
        self.graph.add_nodes_from(graph.graph)
        self.graph.add_edges_from(graph.graph.edges(keys=True))

        for node in self.graph.nodes():
            self.node_attributes(node).update(graph.node_attributes(node, node_params))

        for edge in self.edges():
            self.edge_attributes(edge).update(graph.edge_attributes(edge, edge_params))

        return

