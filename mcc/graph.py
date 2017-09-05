import networkx as nx

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

    def add_edge(self, source, target):
        e = Edge(source, target)
        self.graph.add_edge(source, target, key=e)
        return e

    def in_edges(self, node):
        edges = set()
        for (s, t, e) in self.graph.in_edges(node, keys=True):
            edges.add(e)

        return edges

    def in_edges(self, node):
        edges = set()
        for (s, t, e) in self.graph.out_edges(node, keys=True):
            edges.add(e)

        return edges

    def node_attributes(self, node):
        return self.node[node]

    def edge_attributes(self, edge):
        return self.edge[edge.source][edge.target][edge]

    def nodes(self):
        return self.graph.node.keys()
