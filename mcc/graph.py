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

    def __repr__(self):
        if self.is_edge():
            return "Edge(%s, params=%s)" % (self.obj, self.params())
        else:
            return "Node(%s, params=%s)" % (self.obj, self.params())

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

    def remove_node(self, obj):
        return self.graph.remove_node(obj)

    def remove_edge(self, obj):
        return self.graph.remove_edge(obj.source, obj.target, obj)

    def create_edge(self, source, target):
        e = Edge(source, target)
        return self.add_edge(e)

    def add_edge(self, edge):
        assert(isinstance(edge, Edge))
        if edge.source not in self.graph.nodes():
            logging.warning("source node '%s' does not exist" % edge.source)

        if edge.target not in self.graph.nodes():
            logging.warning("target node '%s' does not exist" % edge.target)

        self.graph.add_edge(edge.source, edge.target, key=edge)
        return edge

    def _neighbours(self, node, aggregator, recursive):
        result = set(aggregator(node))

        if recursive:
            tmp = set()
            for n in result:
                tmp.update(self._neighbours(n, aggregator, recursive))
            result.update(tmp)

        return result

    def leaves(self, node):
        result = set()
        for n in self.graph.successors(node):
            result.update(self.leaves(n))

        if len(result) == 0:
            result.add(node)

        return result

    def roots(self, node):
        result = set()
        for n in self.graph.predecessors(node):
            result.update(self.roots(n))

        if len(result) == 0:
            result.add(node)

        return result

    def predecessors(self, node, recursive=False):
        return self._neighbours(node, self.graph.predecessors, recursive)

    def successors(self, node, recursive=False):
        return self._neighbours(node, self.graph.successors, recursive)

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

    def subgraph(self, nodes):
        result = set()
        for n in nodes:
            assert n in self.graph.node.keys()
            attribs = self.node_attributes(n)
            params = attribs['params'] if 'params' in attribs else None
            result.add(GraphObj(n, None))

        for e in self.edges():
            if e.source in nodes and e.target in nodes:
                attribs = self.edge_attributes(n)
                params = attribs['params'] if 'params' in attribs else None
                result.add(GraphObj(e, params))

        return result

    def export_filter(self, node_params, edge_params):
        self._node_params = node_params
        self._edge_params = edge_params

    def __getstate__(self):
        return GraphExporter(self, self._node_params, self._edge_params).__dict__


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

