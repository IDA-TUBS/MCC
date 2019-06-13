"""
Description
-----------

Produce DOT files from model

:Authors:
    - Johannes Schlatow

"""

import logging
import io

from mcc.framework import Registry, Layer
from mcc.graph import Edge

class DotFactory:
    def __init__(self, model, platform=None):
        self.model = model
        self.platform = platform
        self.dot_styles = dict()

        self.add_style(
                'func_arch',
                { 'node' : ['shape=rectangle', 'colorscheme=set39', 'fillcolor=5', 'style=filled'],
                  'edge' : 'arrowhead=normal, style=dotted, colorscheme=set39, color=5',
                  'map'  : 'cosntraint=false, arrowhead=none, style=dashed, color=dimgray' })

        self.add_style(
                'comp_arch',
                { 'node' : ['shape=component', 'colorscheme=set39', 'fillcolor=6', 'style=filled'],
                  'edge' : 'arrowhead=normal',
                  'map'  : 'constraint=false, arrowhead=none, style=dashed, color=dimgray' })

        self.add_style(
                'task_graph',
                { 'node' : ['shape=ellipse', 'colorscheme=set39', 'fillcolor=9', 'style=filled'],
                  'edge' : { 'call' : 'arrowhead=normal',
                             'signal' : 'arrowhead=normal,style=dashed' },
                  'map'  : 'constraint=false, arrowhead=none, style=dashed, color=dimgray' })

        self.add_style(
                'platform',
                { 'node' : ["shape=tab", "colorscheme=set39", "fillcolor=2", "style=filled"],
                               'edge' : {'undirected' : ['arrowhead=none', 'arrowtail=none'],
                                         'directed'   : [] } })

        self.add_style(
                'layer',
                { 'node' : ["shape=tab", "fillcolor=gray93", "style=filled"] })


        self.copy_style('func_arch', 'comm_arch')
        self.copy_style('func_arch', 'func_query')
        self.copy_style('comp_arch', 'comp_inst')
        self.copy_style('comp_arch', 'comp_arch-pre1')
        self.copy_style('comp_arch', 'comp_arch-pre2')


        # generate ids for all objects
        nid = 1
        eid = 1
        for layer in self.model.by_order:
            for node in layer.graph.nodes():
                layer.graph.node_attributes(node)['id'] = 'c%d' % nid
                nid += 1

            for edge in layer.graph.edges():
                layer.graph.edge_attributes(edge)['id'] = 'e%d' % eid
                eid += 1

    def copy_style(self, from_name, to_name):
        self.dot_styles[to_name] = self.dot_styles[from_name]

    def add_style(self, name, styles):
        self.dot_styles[name] = styles

    def _output_node(self, layer, dotfile, node, prefix="  "):
        label = "label=\"%s\"," % node.untracked_obj().label()
        style = ','.join(self.dot_styles[layer.name]['node'])

        dotfile.write("%s%s [URL=\"%s\",%s%s];\n" % (prefix,
                                                     layer.graph.node_attributes(node)['id'],
                                                     layer.graph.node_attributes(node)['id'],
                                                     label,
                                                     style))

    def _output_edge(self, layer, dotfile, edge, prefix="  "):
        style = self.dot_styles[layer.name]['edge']
        if isinstance(style, dict):
            style = style[edge.edgetype()]
        name = layer.untracked_get_param_value('service', edge)

        if name is not None:
            label = "label=\"%s\"," % name
        else:
            label = ""

        dotfile.write("%s%s -> %s [URL=%s,%s%s];\n" % (prefix,
                                                       layer.graph.node_attributes(edge.source)['id'],
                                                       layer.graph.node_attributes(edge.target)['id'],
                                                       layer.graph.edge_attributes(edge)['id'],
                                                       label,
                                                       style))

    def _output_map_edge(self, layer1, layer2, dotfile, node1, node2, prefix="  "):
        style = self.dot_styles[layer1.name]['map']

        dotfile.write("%s%s -> %s [%s];\n" % (prefix,
                                              layer1.graph.node_attributes(node1)['id'],
                                              layer2.graph.node_attributes(node2)['id'],
                                              style))

    def _output_single_layer(self, layername, output):
        layer = self.model.by_name[layername]

        output.write("digraph {\n")
        output.write("  compound=true;\n")

        # aggregate platform nodes
        subsystems = set()
        for n in layer.graph.nodes():
            sub = layer.untracked_get_param_value('mapping', n)
            if sub is not None:
                subsystems.add(sub)

        # write subsystem nodes
        i = 1

        clusternodes = dict()
        clusters = dict()
        for sub in subsystems:
            # generate and store node id
            clusters[sub] = "cluster%d" % i
            i += 1

            label = ""
            if sub.name() is not None:
                label = "label=\"%s\";" % sub.name()

            style = self.dot_styles['platform']['node']
            output.write("  subgraph %s {\n    %s\n" % (clusters[sub], label))
            for s in style:
                output.write("    %s;\n" % s)

            # add components of this subsystem
            for comp in layer.graph.nodes():
                # only process children in this subsystem
                if layer.untracked_get_param_value('mapping', comp) is None \
                   or sub.name() != layer.untracked_get_param_value('mapping', comp).name():
                    continue

                # remember first node as cluster node
                if sub not in clusternodes:
                    clusternodes[sub] = layer.graph.node_attributes(comp)['id']

                self._output_node(layer, output, comp, prefix="    ")

            # add internal dependencies
            for edge in layer.graph.edges():
                sub1 = layer.untracked_get_param_value('mapping', edge.source)
                sub2 = layer.untracked_get_param_value('mapping', edge.target)
                if sub1 == sub and sub2 == sub:
                    self._output_edge(layer, output, edge, prefix="    ")

            output.write("  }\n")

        # add components with no subsystem
        for comp in layer.graph.nodes():
            # only process children in this subsystem
            if layer.untracked_get_param_value('mapping', comp) is not None:
                continue

            # remember first node as cluster node
            if None not in clusternodes:
                clusternodes[None] = layer.graph.node_attributes(comp)['id']

            self._output_node(layer, output, comp, prefix="    ")

        # add internal dependencies
        for edge in layer.graph.edges():
            sub1 = layer.untracked_get_param_value('mapping', edge.source)
            sub2 = layer.untracked_get_param_value('mapping', edge.target)
            if sub1 == None and sub2 == None:
                self._output_edge(layer, output, edge, prefix="    ")

        if self.platform is not None:
            pfg = self.platform.platform_graph
            # write subsystem edges
            for e in pfg.edges():
                # skip if one of the subsystems is empty
                if e.source not in clusternodes or e.target not in clusternodes:
                    continue
                if pfg.edge_attributes(e)['undirected']:
                    style = ','.join(self.dot_styles['platform']['edge']['undirected'])
                else:
                    style = ','.join(self.dot_styles['platform']['edge']['directed'])
                output.write("  %s -> %s [ltail=%s, lhead=%s, %s];\n" % (clusternodes[e.source],
                                                      clusternodes[e.target],
                                                      clusters[e.source],
                                                      clusters[e.target],
                                                      style))

        # add child dependencies between subsystems
        for edge in layer.graph.edges():
            sub1 = layer.untracked_get_param_value('mapping', edge.source)
            sub2 = layer.untracked_get_param_value('mapping', edge.target)
            if sub1 != sub2:
                self._output_edge(layer, output, edge)

        output.write("}\n")

    def _output_multiple_layers(self, layernames, output):
        output.write("digraph {\n")
        output.write("  compound=true;\n")

        # second, add layer nodes (each layer within a cluster node)
        i = 1
        for layername in layernames:
            layer = self.model.by_name[layername]

            clusterid = "cluster%d" % i
            i += 1

            label = 'label="%s";' % layername
            style = self.dot_styles['layer']['node']

            output.write("  subgraph %s {\n    %s\n" % (clusterid, label))
            for s in style:
                output.write("    %s;\n" % s)

            for comp in layer.graph.nodes():
                self._output_node(layer, output, comp, prefix="    ")

            # add internal dependencies
            for edge in layer.graph.edges():
                self._output_edge(layer, output, edge, prefix="    ")

            output.write("  }\n")

        output.write("  }\n")

    def write_layer(self, layer, filename):
        with open(filename, 'w+') as dotfile:
            self._output_single_layer(layer, dotfile)

    def write_layers(self, layers, filename):
        with open(filename, 'w+') as dotfile:
            self._output_multiple_layers(layers, dotfile)

    def get_layer(self, layer):
        output = io.StringIO()
        self._output_single_layer(layer, output)
        return output.getvalue()

    def get_layers(self, layers):
        output = io.StringIO()
        self._output_multiple_layers(layers, output)
        return output.getvalue()
