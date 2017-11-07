import networkx as nx

class GraphObj:
    # captures dangling graph objects, i.e. Edge or Node, and its parameters

    def __init__(self, obj, params=None):
        self.obj = obj
        self._params = params

    def is_edge(self):
        if isinstance(self.obj, Edge):
            return True

        return False

    def params(self):
        if self._params is None:
            return dict()

        return self._params

class Edge:
    def __init__(self, source, target):
        self.source = source
        self.target = target

class Graph:
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
