
from lxml import objectify
from lxml import etree as ET
from lxml.etree import XMLSyntaxError

from mcc.framework import *
from mcc.backtracking import *

import networkx as nx

class DecisionGraphExtractor():
    def __init__(self, dec_graph):
        self.dec_graph = dec_graph

    def _write_dec_graph(self, filename):
        nodes = list()
        for n in self.dec_graph.nodes():
            nodes.append(n)

        nodes = list(nodes)
        root = ET.Element('dependency_graph')
        params = {}

        for (i, n) in enumerate(nodes):
            if hasattr(n, 'param') and n.param not in params:
                params[n.param] = ET.SubElement(root, 'parameter', name=n.param)

            parents = list(self.dec_graph.graph.predecessors(n))

            parent_index = -1

            # root node has no parents
            if len(parents) > 0:
                parent_index = nodes.index(parents[0])

            # FIXME there is no param attribute in TransformNode
            node = ET.SubElement(params[n.param], 'node', id=str(i), valid=str(n.valid))
            parent_node = ET.SubElement(node, 'parent_node')
            # parent_node.text(parent_index)

            if not isinstance(n, TransformNode):
                obj_elem = ET.SubElement(node, 'obj')
                obj_elem.text = str(n.obj)

                layer_elem = ET.SubElement(node, 'layer')
                layer_elem.text = str(n.layer)

                param_elem = ET.SubElement(node, 'param')
                param_elem.text = str(n.param)

            if isinstance(n, AssignNode):
                node.set('type', 'assign')

                value_elem = ET.SubElement(node, 'match')
                value_elem.text = str(n.value)

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

                obj_elem = ET.SubElement(node, 'obj')
                obj_elem.text = str(n.obj)

        layer_tree = ET.ElementTree(root)
        layer_tree.write(filename, pretty_print=True)

    def write_xml(self, filename):
        self._write_dec_graph(filename)
        # nx.write_gml(self.dec_graph.graph, '/tmp/dec_graph.gml', stringizer=stringizer)


class ModelExtractor():
    def __init__(self, layers):
        self.layers = layers

    def _write_layer(self):
        root = ET.Element('layers')

        for layer_name, layer in self.layers.items():
            graph = layer.graph

            layer_root = ET.SubElement(root, 'layer', name=layer_name)

            for node in graph.nodes():

                node_root = ET.SubElement(layer_root, 'node', name=str(node))

                n_attributes = graph.node_attributes(node)
                for param in n_attributes['params']:
                    param_root = ET.SubElement(node_root, 'param', name=param) 

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

                edge_root = ET.SubElement(layer_root, 'edge', source=str(edge.source),
                                                              target=str(edge.target))

                n_attributes = graph.edge_attributes(edge)
                for param in n_attributes['params']:
                    param_root = ET.SubElement(edge_root, 'param', name=param)

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

    def write_xml(self, filename):
        # FIXME create GEXF format instead custom XML
        layer_xml = self._write_layer()

        layer_tree = ET.ElementTree(layer_xml)
        layer_tree.write(filename, pretty_print=True)

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
