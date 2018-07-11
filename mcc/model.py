"""
Description
-----------

Implements model-specific data structures which are used by our cross-layer model.

:Authors:
    - Johannes Schlatow

"""

from mcc.parser import *
from mcc.framework import *

class ServiceConstraints:
    def __init__(self, name=None, function=None, to_ref=None, from_ref=None):
        self.name     = name
        self.function = function
        self.to_ref   = to_ref
        self.from_ref = from_ref

    def __repr__(self):
        f = '' if self.function is None else '%s ' % self.function
        n = '' if self.name is None else 'via %s' % self.name
        pre = '' if self.to_ref is None and self.from_ref is None else ' ('
        post = '' if self.to_ref is None and self.from_ref is None else ')'
        mid = '' if self.to_ref is None and self.from_ref is None else '->'
        fr = '' if self.from_ref is None else self.from_ref
        to = '' if self.to_ref is None else self.to_ref

        return '%s%s%s%s%s%s%s' % (f, n, pre, fr, mid, to, post) 

class Proxy:
    """ Node type representing to-be-inserted proxies; used in comm_arch layer.
    """
    def __init__(self, carrier, service):
        self.carrier = carrier
        self.service = service

    def label(self):
        return "Proxy(%s)" % self.carrier

    def query(self):
        return { 'service' : self.service.name, 'carrier' : self.carrier }

    def type(self):
        return 'proxy'

class QueryModel(object):
    """ Base class for a query model which is given to the MCC.
    """

    def __init__(self):
        self.query_graph = Graph()
        self.dot_styles = { 'node' : { 'function'  : ['shape=rectangle', 'colorscheme=set39', 'fillcolor=5', 'style=filled'],
                                       'component' : ['shape=component', 'colorscheme=set39', 'fillcolor=6', 'style=filled'],
                                       'composite' : ['shape=component', 'colorscheme=set39', 'fillcolor=9', 'style=filled'] },
                            'edge' : { 'service'   : ['arrowhead=normal'],
                                       'function'  : ['arrowhead=normal', 'style=dotted', 'colorscheme=set39', 'color=3']
                            }}

    def children(self):
        """
        Returns:
            nodes of the query graph
        """
        return self.query_graph.nodes()

    def routes(self):
        """
        Returns:
            edges of the query graph
        """
        return self.query_graph.edges()

    def _write_dot_node(self, dotfile, node, prefix=""):
        label = ""
        label = "label=\"%s\"," % node.identifier()
        style = ','.join(self.dot_styles['node'][node.type()])

        dotfile.write("%s%s [%s%s];\n" % (prefix, self.query_graph.node_attributes(node)['id'], label, style))

    def _write_dot_edge(self, dotfile, edge, prefix="  "):
        attr = self.query_graph.edge_attributes(edge)
        if 'function' in attr:
            style = ','.join(self.dot_styles['edge']['function'])
            label = "label=\"%s\"," % attr['function']
        elif 'service' in attr:
            style = ','.join(self.dot_styles['edge']['service'])
            label = "label=\"%s\"," % attr['service']
        else:
            style = ','.join(self.dot_styles['edge']['function'])
            label = ""

        dotfile.write("%s%s -> %s [%s%s];\n" % (prefix,
                                                self.query_graph.node_attributes(edge.source)['id'],
                                                self.query_graph.node_attributes(edge.target)['id'],
                                                label,
                                                style))


class PlatformModel(object):
    """ Base class of a platform model.
    """

    def __init__(self):
        self.platform_graph = Graph()

        self.pf_dot_styles = { 'node' : ["shape=tab", "colorscheme=set39", "fillcolor=2", "style=filled"],
                               'edge' : '' }

    def reachable(self, from_component, to_component):
        raise NotImplementedError()

class SubsystemModel(PlatformModel, QueryModel):
    """ Models the (hierarchical) structure of (Genode) subsystems.

    A subsystem model specifies both, the platform (consisting of subsystems) and an abstract, pre-defined mapping
    of children that reside in the subsystems.
    """

    def __init__(self, parser):
        """ Initialises the query model and platform model using the given parser.

        Args:
            :type parser: :class:`mcc.parser.SubsystemParser`
        """
        PlatformModel.__init__(self)
        self.subsystem_root = None
        self.subsystem_graph = self.platform_graph
        self.parser = parser

        self._parse()

        QueryModel.__init__(self)
        self._create_query_model()

    def _parse(self, start=None):
        if self.subsystem_root is None:
            self.subsystem_root = self.parser.root()
            self.add_subsystem(self.subsystem_root)

        if start is None:
            start = self.subsystem_root

        for sub in start.subsystems():
            self.add_subsystem(sub, parent=start)
            self._parse(sub)

    def _create_query_model(self):
        for sub in self.subsystem_graph.nodes():
            for ch in sub.children():
                self.query_graph.add_node(ch)

        # parse and add explicit routes
        for ch in self.query_graph.nodes():
            for route in ch.routes():
                target = self.find_child(route['child'])
                if target is not None:
                    e = self.query_graph.create_edge(ch, target)
                    self.query_graph.edge_attributes(e).update(route)
                else:
                    logging.error("Cannot route to referenced child %s. Not found." % (route['child']))

    def find_child(self, name):
        for ch in self.query_graph.nodes():
            if ch.identifier() == name:
                return ch

        return None

    def add_subsystem(self, subsystem, parent=None):
        self.subsystem_graph.add_node(subsystem)

        if parent is not None:
            if parent not in self.subsystem_graph.nodes():
                raise Exception("Cannot find parent '%s' in subsystem graph." % parent)
            self.subsystem_graph.create_edge(parent, subsystem)
        else:
            self.subsystem_root = subsystem

    def write_dot(self, filename):
    
        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")
            dotfile.write("  compound=true;\n")

            # write subsystem nodes
            i = 1
            n = 1
            clusternodes = dict()
            for sub in self.subsystem_graph.nodes():
                # generate and store node id
                self.subsystem_graph.node_attributes(sub)['id'] = "cluster%d" % i
                i += 1

                label = ""
                if sub.name(None) is not None:
                    label = "label=\"%s\";" % sub.name()

                style = self.pf_dot_styles['node']
                dotfile.write("  subgraph %s {\n    %s\n" % (self.subsystem_graph.node_attributes(sub)['id'], label))
                for s in style:
                    dotfile.write("    %s;\n" % s)

                # add children of this subsystem
                for ch in self.query_graph.nodes():
                    # only process children in this subsystem
                    if ch.subsystem() is not sub:
                        continue

                    self.query_graph.node_attributes(ch)['id'] = "ch%d" % n
                    n += 1
                    # remember first child node as cluster node
                    if sub not in clusternodes:
                        clusternodes[sub] = self.query_graph.node_attributes(ch)['id']

                    QueryModel._write_dot_node(self, dotfile, ch, prefix="    ")

                # add internal dependencies
                for e in self.query_graph.edges():
                    if e.source.subsystem() == sub and e.target.subsystem() == sub:
                        QueryModel._write_dot_edge(self, dotfile, e, prefix="    ")

                dotfile.write("  }\n")

            # write subsystem edges
            for e in self.subsystem_graph.edges():
                # skip if one of the subsystems is empty
                if e.source not in clusternodes or e.target not in clusternodes:
                    continue
                style = self.pf_dot_styles['edge']
                dotfile.write("  %s -> %s [ltail=%s, lhead=%s, %s];\n" % (clusternodes[e.source],
                                                      clusternodes[e.target],
                                                      self.subsystem_graph.node_attributes(e.source)['id'],
                                                      self.subsystem_graph.node_attributes(e.target)['id'],
                                                      style))

            # add children with no subsystem
            for ch in self.query_graph.nodes():
                if ch.subsystem() is None:
                    self.query_graph.node[ch]['id'] = "ch%d" % n
                    n += 1
                    QueryModel._write_dot_node(self, dotfile, ch)

            # add child dependencies between subsystems
            for e in self.query_graph.edges():
                if e.source.subsystem() != e.target.subsystem():
                    QueryModel._write_dot_edge(self, dotfile, e)

            dotfile.write("}\n")

        return

    def reachable(self, from_component, to_component):
        if from_component == to_component or from_component in to_component.subsystems() or to_component in from_component.subsystems():
            return True, 'native', from_component
        else:
            # here, we assume subsystems are connected via network
            return False, 'Nic', 'Network'

class SystemModel(BacktrackRegistry):
    """ Our cross-layer model.
    """
    def __init__(self, repo, platform, dotpath=None):
        super().__init__()
        self.add_layer(Layer('func_arch', nodetypes={Subsystem.Child}))
        self.add_layer(Layer('comm_arch', nodetypes={Subsystem.Child,Proxy}))
        self.add_layer(Layer('comp_arch-pre1', nodetypes={Repository.Component}))
        self.add_layer(Layer('comp_arch-pre2', nodetypes={Repository.Component}))
        self.add_layer(Layer('comp_arch', nodetypes={Repository.Component}))
        self.add_layer(Layer('comp_inst', nodetypes={Repository.Component}))

        self.platform = platform
        self.repo = repo
        self.dotpath = dotpath

        self.dot_styles = { 
                self.by_name['func_arch'] : 
                { 'node' : ['shape=rectangle', 'colorscheme=set39', 'fillcolor=5', 'style=filled'],
                  'edge' : 'arrowhead=normal, style=dotted, colorscheme=set39, color=3',
                  'map'  : 'arrowhead=none, style=dashed, color=dimgray' },
                self.by_name['comp_arch'] :
                { 'node' : ['shape=component', 'colorscheme=set39', 'fillcolor=6', 'style=filled'],
                  'edge' : 'arrowhead=normal',
                  'map'  : 'arrowhead=none, style=dashed, color=dimgray' },
                self.platform : self.platform.pf_dot_styles
                }

        self.dot_styles[self.by_name['comm_arch']]      = self.dot_styles[self.by_name['func_arch']]
        self.dot_styles[self.by_name['comp_inst']]      = self.dot_styles[self.by_name['comp_arch']]
        self.dot_styles[self.by_name['comp_arch-pre1']] = self.dot_styles[self.by_name['comp_arch']]
        self.dot_styles[self.by_name['comp_arch-pre2']] = self.dot_styles[self.by_name['comp_arch']]

    def _output_layer(self, layer, suffix=''):
        if self.dotpath is not None:
            self.write_dot_layer(layer.name, self.dotpath+layer.name+suffix+".dot")

    def from_query(self, query_model):
        fa = self.by_name['func_arch']
        self.reset(fa)

        # insert nodes
        for child in query_model.children():
            self._insert_query(child)

        # insert edges
        for route in query_model.routes():
            # remark: nodes in query_model and fa are the same objects
            e = fa.graph.create_edge(route.source, route.target)
            if 'service' in query_model.query_graph.edge_attributes(route):
                fa._set_param_value('service', e, ServiceConstraints(name=query_model.query_graph.edge_attributes(route)['service']))
            else:
                function = None
                if route.target.type() == 'function':
                    function = route.target.query()
                fa._set_param_value('service', e, ServiceConstraints(function=function))

    def _insert_query(self, child):
        assert(len(self.by_name['comp_arch'].graph.nodes()) == 0)

        # add node to functional architecture layer
        fa = self.by_name['func_arch']
        fa.graph.add_node(child)

        # set pre-defined mapping
        if child.platform_component() is not None:
            fa._set_param_candidates('mapping', child, set([child.platform_component()]))

    def _write_dot_node(self, layer, dotfile, node, prefix="  "):
        label = "label=\"%s\"," % node.label()
        style = ','.join(self.dot_styles[layer]['node'])

        dotfile.write("%s%s [%s%s];\n" % (prefix, layer.graph.node_attributes(node)['id'], label, style))

    def _write_dot_edge(self, layer, dotfile, edge, prefix="  "):
        style = self.dot_styles[layer]['edge']
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


    def write_dot_layer(self, layername, filename):
        layer = self.by_name[layername]

        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")
            dotfile.write("  compound=true;\n")


            # write subsystem nodes
            i = 1
            n = 1
            clusternodes = dict()
            pfg = self.platform.platform_graph
            for sub in pfg.nodes():
                # generate and store node id
                pfg.node_attributes(sub)['id'] = "cluster%d" % i
                i += 1

                label = ""
                if sub.name(None) is not None:
                    label = "label=\"%s\";" % sub.name()

                style = self.dot_styles[self.platform]['node']
                dotfile.write("  subgraph %s {\n    %s\n" % (pfg.node_attributes(sub)['id'], label))
                for s in style:
                    dotfile.write("    %s;\n" % s)

                # add components of this subsystem
                for comp in layer.graph.nodes():
                    # only process children in this subsystem
                    if sub is not layer._get_param_value('mapping', comp):
                        continue

                    layer.graph.node_attributes(comp)['id'] = "c%d" % n
                    n += 1

                    # remember first node as cluster node
                    if sub not in clusternodes:
                        clusternodes[sub] = layer.graph.node_attributes(comp)['id']

                    self._write_dot_node(layer, dotfile, comp, prefix="    ")

                # add internal dependencies
                for edge in layer.graph.edges():
                    sub1 = layer._get_param_value('mapping', edge.source)
                    sub2 = layer._get_param_value('mapping', edge.target)
                    if sub1 == sub and sub2 == sub:
                        self._write_dot_edge(layer, dotfile, edge, prefix="    ")

                dotfile.write("  }\n")

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

                self._write_dot_node(layer, dotfile, comp, prefix="    ")

            # add internal dependencies
            for edge in layer.graph.edges():
                sub1 = layer._get_param_value('mapping', edge.source)
                sub2 = layer._get_param_value('mapping', edge.target)
                if sub1 == None and sub2 == None:
                    self._write_dot_edge(layer, dotfile, edge, prefix="    ")

            # write subsystem edges
            for e in pfg.edges():
                # skip if one of the subsystems is empty
                if e.source not in clusternodes or e.target not in clusternodes:
                    continue
                style = self.dot_styles[self.platform]['edge']
                dotfile.write("  %s -> %s [ltail=%s, lhead=%s, %s];\n" % (clusternodes[e.source],
                                                      clusternodes[e.target],
                                                      pfg.node_attributes(e.source)['id'],
                                                      pfg.node_attributes(e.target)['id'],
                                                      style))

            # add child dependencies between subsystems
            for edge in layer.graph.edges():
                sub1 = layer._get_param_value('mapping', edge.source)
                sub2 = layer._get_param_value('mapping', edge.target)
                if sub1 != sub2:
                    self._write_dot_edge(layer, dotfile, edge)

            dotfile.write("}\n")

#    def _merge_component(self, c1, c2):
#        sub1 = self.mapping_query2subsystem[self.mapping_component2query[c1]]
#        sub2 = self.mapping_query2subsystem[self.mapping_component2query[c2]]
#        if sub1 == sub2:
#
#            # redirect edges of c2
#            for edge in self.component_in_edges(c2):
#                if c1.max_clients(edge.attr['service']) <= c1.connections(self, edge.attr['service']):
#                    logging.info("Merging components '%s' because of max_clients restriction." % c1.xml.get('name'))
#                    return True
#
#                self.component_graph.remove_edge(edge.source, edge.target)
#                newedge = self.add_component_edge(edge.source, c1, edge.attr)
#                if edge in self.mapping_session2query:
#                    self.mapping_session2query[newedge] = self.mapping_session2query[edge]
#                    del self.mapping_session2query[edge]
#
#            logging.info("Merging components '%s'." % c1.xml.get('name'))
#
#            # remove node
#            self.component_graph.remove_node(c2)
#            # remark: this actually removes information about from which query this component resulted
#            del self.mapping_component2query[c2]
#        else:
#            logging.info("Not merging component '%s' because is present in different subsystems." % c1.xml.get('name'))
#
#        return True
#
#    def merge_components(self, singleton=True):
#
#        # find duplicates
#        processed = set()
#        for comp in nx.topological_sort(self.component_graph, reverse=True):
#            if comp in processed:
#                continue
#
#            # skip non-singleton components if we only operate on singletons
#            if singleton and ('singleton' not in comp.xml.keys() or comp.xml.get('singleton').lower() != "true"):
#                continue
#
#            for dup in self.component_graph.nodes():
#                if dup is not comp and dup.is_comp(comp.component()):
#                    # duplicates must only be replaced if they connect to the same services
#                    # -> as a result we need to iterate the nodes in reverse topological order
#                    if self.component_graph.successors(comp) == self.component_graph.successors(dup):
#                        processed.add(dup)
#                        if not self._merge_component(comp, dup):
#                            return False
#
#        return True
