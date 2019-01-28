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

class DotFactory:
    def __init__(self, model, platform=None):
        self.model = model
        self.platform = platform
        self.dot_styles = dict()

        self.add_style(
                'func_arch',
                { 'node' : ['shape=rectangle', 'colorscheme=set39', 'fillcolor=5', 'style=filled'],
                  'edge' : 'arrowhead=normal, style=dotted, colorscheme=set39, color=3',
                  'map'  : 'arrowhead=none, style=dashed, color=dimgray' })

        self.add_style(
                'comp_arch',
                { 'node' : ['shape=component', 'colorscheme=set39', 'fillcolor=6', 'style=filled'],
                  'edge' : 'arrowhead=normal',
                  'map'  : 'arrowhead=none, style=dashed, color=dimgray' })

        self.add_style(
                'platform',
                { 'node' : ["shape=tab", "colorscheme=set39", "fillcolor=2", "style=filled"],
                               'edge' : {'undirected' : ['arrowhead=none', 'arrowtail=none'],
                                         'directed'   : [] } })

        self.copy_style('func_arch', 'comm_arch')
        self.copy_style('comp_arch', 'comp_inst')
        self.copy_style('comp_arch', 'comp_arch-pre1')
        self.copy_style('comp_arch', 'comp_arch-pre2')

    def copy_style(self, from_name, to_name):
        self.dot_styles[to_name] = self.dot_styles[from_name]

    def add_style(self, name, styles):
        self.dot_styles[name] = styles

    def _output_node(self, layer, dotfile, node, prefix="  "):
        label = "label=\"%s\"," % node.label()
        style = ','.join(self.dot_styles[layer.name]['node'])

        dotfile.write("%s%s [URL=\"%s\",%s%s];\n" % (prefix,
                                                     layer.graph.node_attributes(node)['id'],
                                                     layer.graph.node_attributes(node)['id'],
                                                     label,
                                                     style))

    def _output_edge(self, layer, dotfile, edge, prefix="  "):
        style = self.dot_styles[layer.name]['edge']
        name = layer._get_param_value('service', edge)

        if name is not None:
            label = "label=\"%s\"," % name
        else:
            label = ""

        dotfile.write("%s%s -> %s [%s%s];\n" % (prefix,
                                                layer.graph.node_attributes(edge.source)['id'],
                                                layer.graph.node_attributes(edge.target)['id'],
                                                label,
                                                style))

    def _output_layer(self, layername, output):
        layer = self.model.by_name[layername]

        output.write("digraph {\n")
        output.write("  compound=true;\n")

        # aggregate platform nodes
        subsystems = set()
        for n in layer.graph.nodes():
            sub = layer._get_param_value('mapping', n)
            if sub is not None:
                subsystems.add(sub)

        # write subsystem nodes
        i = 1
        n = 1
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
                if layer._get_param_value('mapping', comp) is None \
                   or sub.name() != layer._get_param_value('mapping', comp).name():
                    continue

                layer.graph.node_attributes(comp)['id'] = "c%d" % n
                n += 1

                # remember first node as cluster node
                if sub not in clusternodes:
                    clusternodes[sub] = layer.graph.node_attributes(comp)['id']

                self._output_node(layer, output, comp, prefix="    ")

            # add internal dependencies
            for edge in layer.graph.edges():
                sub1 = layer._get_param_value('mapping', edge.source)
                sub2 = layer._get_param_value('mapping', edge.target)
                if sub1 == sub and sub2 == sub:
                    self._output_edge(layer, output, edge, prefix="    ")

            output.write("  }\n")

        # add components with no subsystem
        for comp in layer.graph.nodes():
            # only process children in this subsystem
            if layer._get_param_value('mapping', comp) is not None:
                continue

            layer.graph.node_attributes(comp)['id'] = "c%d" % n
            n += 1

            # remember first node as cluster node
            if None not in clusternodes:
                clusternodes[None] = layer.graph.node_attributes(comp)['id']

            self._output_node(layer, output, comp, prefix="    ")

        # add internal dependencies
        for edge in layer.graph.edges():
            sub1 = layer._get_param_value('mapping', edge.source)
            sub2 = layer._get_param_value('mapping', edge.target)
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
                    style = ','.joint(self.dot_styles['platform']['edge']['directed'])
                output.write("  %s -> %s [ltail=%s, lhead=%s, %s];\n" % (clusternodes[e.source],
                                                      clusternodes[e.target],
                                                      clusters[e.source],
                                                      clusters[e.target],
                                                      style))

        # add child dependencies between subsystems
        for edge in layer.graph.edges():
            sub1 = layer._get_param_value('mapping', edge.source)
            sub2 = layer._get_param_value('mapping', edge.target)
            if sub1 != sub2:
                self._output_edge(layer, output, edge)

        output.write("}\n")

    def write_layer(self, layer, filename):
        with open(filename, 'w+') as dotfile:
            self._output_layer(layer, dotfile)

    def get_layer(self, layer):
        output = io.StringIO()
        self._output_layer(layer, output)
        return output.getvalue()
