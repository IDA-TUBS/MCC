
from lxml import objectify
from lxml import etree as ET
from lxml.etree import XMLSyntaxError

from mcc.framework import *
from mcc.backtracking import *

import networkx as nx


class ModelExtractor():
    def __init__(self, layers, file_name, dep_graph=None):
        self.layers = layers
        self.file_name = file_name
        self.dep_graph = dep_graph

        # self.predecessors = nx.predecessors(self.dep_graph.graph)

    def _write_dep_graph(self, filename):
        nodes = list()
        for n in self.dep_graph.nodes():
            nodes.append(n)

        nodes = list(nodes)
        root = ET.Element('dependency_graph')
        params = {}

        for (i, n) in enumerate(nodes):
            if n.param not in params:
                params[n.param] = ET.SubElement(root, 'parameter', name=n.param)

            parents = list(self.dep_graph.graph.predecessors(n))

            parent_index = -1

            # root node has no parents
            if len(parents) > 0:
                parent_index = nodes.index(parents[0])


            node = ET.SubElement(params[n.param], 'node', id=str(i), valid=str(n.valid))
            parent_node = ET.SubElement(node, 'parent_node')
            # parent_node.text(parent_index)

            if not isinstance(n, TransformNode):
                value_elem = ET.SubElement(node, 'value')
                value_elem.text = str(n.value)

                layer_elem = ET.SubElement(node, 'layer')
                layer_elem.text = str(n.layer)

                param_elem = ET.SubElement(node, 'param')
                param_elem.text = str(n.param)

            if isinstance(n, AssignNode):
                node.set('type', 'assign')

                match_elem = ET.SubElement(node, 'match')
                match_elem.text = str(n.match)

            if isinstance(n, MapNode):
                node.set('type', 'map')

                for can in n.candidates:
                    can_elem = ET.SubElement(node, 'candidate')
                    can_elem.text = str(can)

            if isinstance(n, TransformNode):
                node.set('type', 'transform')

                source_elem = ET.SubElement(node, 'source-layer')
                source_elem.text = str(n.source_layer)

                target_elem = ET.SubElement(node, 'target-layer')
                target_elem.text = str(n.target_layer)

                value_elem = ET.SubElement(node, 'value')
                value_elem.text = str(n.value)

        layer_tree = ET.ElementTree(root)
        layer_tree.write(filename, pretty_print=True)

    def _write_layer(self):
        root = ET.Element('layers')

        for layer_name, layer in self.layers.items():
            graph = layer.graph

            layer_root = ET.SubElement(root, 'layer', name=layer_name)

            for node in graph.nodes():
                n_attributes = graph.node_attributes(node)
                for param in n_attributes['params']:
                    param_root = ET.SubElement(layer_root, 'param', name=param) 

                    value = n_attributes['params'][param]['value']
                    candidates = n_attributes['params'][param]['candidates']

                    # print(n_attributes['params'])
                    if 'match' in n_attributes['params'][param]:
                        match = n_attributes['params'][param]['match']
                        # print(str(match))
                        match_node = ET.SubElement(param_root, 'match')
                        match_node.text = str(match)
                    value_node = ET.SubElement(param_root, 'value')
                    value_node.text = str(value)

                    for can in candidates:
                        can_node = ET.SubElement(param_root, 'candidate')
                        can_node.text = str(can)

            for edge in graph.edges():
                n_attributes = graph.edge_attributes(edge)
                for param in n_attributes['params']:
                    param_root = ET.SubElement(layer_root, 'param', name=param)

                    value = n_attributes['params'][param]['value']
                    candidates = n_attributes['params'][param]['candidates']
                    value_edge = ET.SubElement(param_root, 'value')
                    value_edge.text = str(value)

                    if 'match' in n_attributes['params'][param]:
                        match = n_attributes['params'][param]['match']
                        match_node = ET.SubElement(param_root, 'match')
                        match_node.text = str(match)

                    for can in candidates:
                        can_edge = ET.SubElement(param_root, 'candidate')
                        can_edge.text = str(can)

        return root

    def _export_dep_graph(self):
        if self.dep_graph is None:
            return

        self._write_dep_graph('/tmp/dep_graph.xml')
        # nx.write_gml(self.dep_graph.graph, '/tmp/dep_graph.gml', stringizer=stringizer)

    def write_modell(self):
        layer_xml = self._write_layer()
        self._export_dep_graph()

        layer_tree = ET.ElementTree(layer_xml)
        layer_tree.write(self.file_name, pretty_print=True)

def stringizer(value):
    return str(value)

"""
{'params': {'mapping'  : {'value': <mcc.parser.Subsystem object at 0x7f92f8f25588>, 'candidates': {<mcc.parser.Subsystem object at 0x7f92f8f25588>}},
            'comm_arch': {'value': {object_recog}, 'candidates': set()}}} 

Example XMl File

<layers>
    <func_arch>
        <mapping>
            <value>object_recog</value>
            <match> blub </match>
            <candidate>mcc.parser.Substem object at 0x898....</candidate>
            <candidate>via Rom</candidate>
            <candidate>via Nic</candidate>
        </mapping>
        <comm_arch>
            <value>Foobar</value
            <candidate>Via Nic</candidate>
            <candidate>Stereo</candidate>
        </mapping>
        </comm_arch>
    </func_arch>
</layers>
"""
