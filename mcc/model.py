"""
Description
-----------

Implements model-specific data structures which are used by our cross-layer model.

:Authors:
    - Johannes Schlatow

"""

from mcc.parser import *
from mcc.framework import *
from mcc.backtracking import *

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


class Instance:
    """ Wrapper for components for managing instantiations
    """
    def __init__(self, identifier, component, config=None):
        self.identifier = identifier
        self.component  = component
        self.config     = config
        self.replaces = set()

    def is_component(self, rhs):
        return self.component.uid() == rhs.uid()

    def component_uid(self):
        if self.config is None:
            return self.component.uid()
        else:
            return '%s-%s' % (self.component.uid(), hash(self.config))

    def register_replacement(self, instance):
        self.replaces.add(instance)

    def replaces(self):
        return self.replaces

    def shared(self):
        return len(self.replaces) > 0

    def label(self):
        return self.identifier

    def requires_services(self):
        return self.component.requires_services()

    def provides_services(self, name=None, ref=None):
        return self.component.provides_services(name, ref)

    def uid(self):
        return self

    def __repr__(self):
        return self.identifier

class InstanceFactory:
    """ Stores instances
    """

    def __init__(self):
        self.instances = dict()
        self.identifiers = dict()

    def unique_name(self, component):
        # build unique name from component name, object id and sequence number
        if component.unique_label() not in self.identifiers:
            self.identifiers[component.unique_label()] = 1
        else:
            self.identifiers[component.unique_label()] += 1

        return "%s-%s" % (component.unique_label(), self.identifiers[component.unique_label()])

    def insert_existing_instances(self, subsystem, existing):
        if subsystem not in self.instances:
            self.instances[subsystem] = { 'shared' : dict(),
                                          'dedicated' : dict() }

        for inst in existing:
            assert isinstance(inst, Instance)
            self.instances[subsystem]['shared'][inst.component_uid()] = inst
            self.instances[subsystem]['dedicated'][inst.component]    = inst


    def dedicated_instance(self, subsystem, component, config=None):
        """ create and return dedicated instance
        """
        if subsystem not in self.instances:
            self.instances[subsystem] = { 'shared' : dict(),
                                          'dedicated' : dict() }

        if component not in self.instances[subsystem]['dedicated']:
            new_inst = Instance(self.unique_name(component), component, config)

            self.instances[subsystem]['dedicated'][component] = new_inst

            # insert new_inst as shared instance is there is none yet
            if new_inst.component_uid() not in self.instances[subsystem]['shared']:
                self.instances[subsystem]['shared'][new_inst.component_uid()] = new_inst
            else: # register new_inst at shared instance
                self.instances[subsystem]['shared'][new_inst.component_uid()].register_replacement(new_inst)

        return self.instances[subsystem]['dedicated'][component]

    def shared_instance(self, subsystem, component, config=None):
        """ return matching shared instance from same subsystem
        """
        dedicated = self.dedicated_instance(subsystem, component, config)

        if subsystem in self.instances:
            if dedicated.component_uid() in self.instances[subsystem]['shared']:
                return self.instances[subsystem]['shared'][dedicated.component_uid()]

        return dedicated

    def parent_instance(self, subsystem, component):
        """ return matching shared instance from parent
        """
        # TODO allow mapping to instance from parent subsystems?
        raise NotImplementedError()

    def types(self):
        return {Instance}


class BaseChild:
    def __init__(self, name, subsystem, instances, subgraph):
        self._name       = name
        self._subsystem  = subsystem
        self._instances  = instances
        self._subgraph   = subgraph

    ########################
    # ChildQuery interface #
    ########################

    def subsystem(self):
        return self._subsystem

    def routes(self):
        return set()

    def dependencies(self, dtype):
        return set()

    def label(self):
        return self._name

    def functions(self):
        functions = set()
        for inst in self._instances:
            functions.add(inst.component.function())

        return functions

    def components(self):
        return self._instances

    #######################
    # Component interface #
    #######################

    def requires_rte(self):
        # all components have the same RTE requirement
        return list(self._instances)[0].component.requires_rte()

    def requires_specs(self):
        # aggregate spec requirements
        specs = set()
        for inst in self._instances:
            specs.update(inst.component.requires_specs())

        return specs

    def requires_functions(self):
        return set()

    def patterns(self):
        return {self}

    def provides_services(self, name=None, ref=None, function=None):
        services = set()
        for inst in self._instances:
            if function is None or function == inst.component.function():
                services.update(inst.provides_services(name, ref))

        return list(services)

    def providing_component(self, service, function=None, to_ref=None):
        for inst in self._instances:
            if function is not None and inst.component.function() != function:
                continue

            for s in inst.provides_services(service, to_ref):
                # we found a match
                return inst, to_ref

        logging.error("Cannot find providing component for %s %s %s" % (service, function, to_ref))
        return None, None

    def type(self):
        return 'function'

    ##############################
    # PatternComponent interface #
    ##############################

    def flatten(self):
        return self._subgraph


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
                               'edge' : {'undirected' : ['arrowhead=none', 'arrowtail=none'],
                                         'directed'   : [] } }

    def reachable(self, from_component, to_component):
        raise NotImplementedError()

class SimplePlatformModel(PlatformModel):
    """ Implements a simple platform model with resources (nodes) and communication paths (edges).
    """
    def __init__(self, parser):
        """ Initialises the platform model using the given parser.

        Args:
            :type parser: :class:`mcc.parser.PlatformParser`
        """
        self.parser = parser
        PlatformModel.__init__(self)

        self._parse()

    def _parse(self):
        reachability_map = dict()
        for comm in self.parser.comm_names():
            reachability_map[comm] = set()

        for c in self.parser.pf_components():
            self.platform_graph.add_node(c, {self.parser.PfComponent})
            for comm in c.comms():
                reachability_map[comm].add(c)

        processed = set()
        for comm in reachability_map:
            for src in reachability_map[comm]:
                processed.add(src)
                for dst in reachability_map[comm] - processed:
                    e1 = self.platform_graph.create_edge(src, dst)
                    self.platform_graph.edge_attributes(e1)['carrier'] = comm
                    self.platform_graph.edge_attributes(e1)['undirected'] = True

    def find_by_name(self, name):
        for n in self.platform_graph.nodes():
            if n.name() == name:
                return n

        return None

    def write_dot(self, filename):
        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")

            id_lookup = dict()
            next_node_id = 1
            for n in self.platform_graph.nodes():
                id_lookup[n.name()] = "n%d" % next_node_id
                next_node_id += 1

                label = "label=\"%s\"," % n.name()
                style = ','.join(self.pf_dot_styles['node'])

                dotfile.write("%s [%s%s];\n" % (id_lookup[n.name()], label, style))

            for e in self.platform_graph.edges():
                attr = self.platform_graph.edge_attributes(e)

                if 'undirected' in attr and attr['undirected']:
                    style = ','.join(self.pf_dot_styles['edge']['undirected'])
                else:
                    style = ','.join(self.pf_dot_styles['edge']['directed'])

                if 'carrier' in attr:
                    label = "label=\"%s\"," % attr['carrier']
                else:
                    label = ""

                dotfile.write("%s -> %s [%s%s];\n" % (id_lookup[e.source.name()],
                                                      id_lookup[e.target.name()],
                                                      label,
                                                      style))

            dotfile.write('}\n')

    def reachable(self, from_component, to_component):
        assert isinstance(from_component, PlatformParser.PfComponent)
        assert isinstance(to_component, PlatformParser.PfComponent)

        if from_component.in_native_domain(to_component):
            return True, 'native', from_component
        else:
            # FIXME automatically determine carrier from contract repository

            for e in self.platform_graph.out_edges(from_component):
                if e.target == to_component:
                    attr = self.platform_graph.edge_attributes(e)
                    if attr['carrier'].startswith("Network") or attr['carrier'].startswith("network"):
                        return False, 'Nic', attr['carrier']
                    else:
                        logging.warning("Cannot determine interface for carrier '%s'" % attr['carrier'])
                        return False, None, attr['carrier']

            for e in self.platform_graph.out_edges(to_component):
                attr = self.platform_graph.edge_attributes(e)
                if e.target == from_component and attr['undirected']:
                    if attr['carrier'].startswith("Network") or attr['carrier'].startswith("network"):
                        return False, 'Nic', attr['carrier']
                    else:
                        logging.warning("Cannot determine interface for carrier '%s'" % attr['carrier'])
                        return False, None, attr['carrier']

        logging.error("No reachability between %s and %s" % (from_component, to_component))
        return False, None, None

class FuncArchQuery(QueryModel):
    def __init__(self, parser):
        self.parser = parser

        QueryModel.__init__(self)

        self._parse()

    def _parse(self):
        for child in self.parser.children():
            self.query_graph.add_node(child, {ChildQuery})

        # parse and add explicit routes
        for child in self.query_graph.nodes():
            for route in child.dependencies('child'):
                target = self.find_child(route['child'])
                if target is not None:
                    e = self.query_graph.create_edge(child, target)
                    self.query_graph.edge_attributes(e).update(route)
                else:
                    logging.error("Cannot route to referenced child %s. Not found." % (route['child']))

    def find_child(self, name):
        for ch in self.query_graph.nodes():
            if ch.identifier() == name:
                return ch

        return None

    def write_dot(self, filename):
        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")

            next_node_id = 1
            for n in self.query_graph.nodes():
                self.query_graph.node_attributes(n)['id'] = "n%d" % next_node_id
                next_node_id += 1

                QueryModel._write_dot_node(self, dotfile, n)

            for e in self.query_graph.edges():
                QueryModel._write_dot_edge(self, dotfile, e)

            dotfile.write('}\n')


class SystemModel(BacktrackRegistry):
    """ Our cross-layer model.
    """
    def __init__(self, repo, platform, dotpath=None):
        super().__init__()
        self.add_layer(Layer('func_arch', nodetypes={ChildQuery,BaseChild}))
        self.add_layer(Layer('comm_arch', nodetypes={ChildQuery,Proxy,BaseChild}))
        self.add_layer(Layer('comp_arch-pre1', nodetypes={Repository.Component,Instance}))
        self.add_layer(Layer('comp_arch-pre2', nodetypes={Repository.Component,Instance}))
        self.add_layer(Layer('comp_arch', nodetypes={Repository.Component,Instance}))
        self.add_layer(Layer('comp_inst', nodetypes={Instance}))

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

    def connect_functions(self):
        fa = self.by_name['func_arch']

        for c in fa.graph.nodes():
            # for each dependency
            for dep in c.dependencies('function'):
                depfunc = dep['function']
                # edge exists?
                satisfied = False
                for e in fa.graph.out_edges(c):
                    sc = fa._get_param_value('service', e)
                    if sc.function == depfunc:
                        satisfied = True

                if not satisfied:
                    # find providing child
                    local_match = None
                    remote_match = None
                    pf_component = list(fa._get_param_candidates('mapping', c))[0]
                    for provider in fa.graph.nodes():
                        if provider is not c:
                            if depfunc in provider.functions():
                                if list(fa._get_param_candidates('mapping', provider))[0].in_native_domain(pf_component):
                                    local_match = provider
                                else:
                                    remote_match = provider

                    provider = None
                    if local_match is not None:
                        provider = local_match
                    elif remote_match is not None:
                        provider = remote_match

                    if provider is not None:
                        e = fa.create_edge(c, provider)
                        fa._set_param_value('service', e, ServiceConstraints(function=depfunc))
                        satisfied = True

                assert satisfied, "Cannot satisfy function dependency '%s' from '%s'" % (depfunc, c)

    def _output_layer(self, layer, suffix=''):
        if self.dotpath is not None:
            self.write_dot_layer(layer.name, self.dotpath+layer.name+suffix+".dot")

    def _insert_base(self, base):
        fa = self.by_name['func_arch']

        for bcomp in base.base_arch():
            fa.add_node(bcomp)
            pf_comp = self.platform.find_by_name(bcomp.subsystem())
            fa._set_param_candidates('mapping', bcomp, set([pf_comp]))

    def from_query(self, query_model, base=None):
        fa = self.by_name['func_arch']
        self.reset(fa)

        if base is not None:
            self._insert_base(base)

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
                functions = route.target.functions()
                assert len(functions) <= 1, "Dependency to child with multiple functions (%s) detected." % functions

                function = None
                if len(functions) == 1:
                    function = list(functions)[0]

                fa._set_param_value('service', e, ServiceConstraints(function=function))

    def _insert_query(self, child):
        assert(len(self.by_name['comp_arch'].graph.nodes()) == 0)

        # add node to functional architecture layer
        fa = self.by_name['func_arch']
        fa.add_node(child)

        # set pre-defined mapping
        if hasattr(child, "platform_component"):
            if child.platform_component() is not None:
                fa._set_param_candidates('mapping', child, set([child.platform_component()]))
        elif child.subsystem() is not None:
            pf_comp = self.platform.find_by_name(child.subsystem())
            fa._set_param_candidates('mapping', child, set([pf_comp]))

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
                if sub.name() is not None:
                    label = "label=\"%s\";" % sub.name()

                style = self.dot_styles[self.platform]['node']
                dotfile.write("  subgraph %s {\n    %s\n" % (pfg.node_attributes(sub)['id'], label))
                for s in style:
                    dotfile.write("    %s;\n" % s)

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
                if pfg.edge_attributes(e)['undirected']:
                    style = ','.join(self.dot_styles[self.platform]['edge']['undirected'])
                else:
                    style = ','.joint(self.dot_styles[self.platform]['edge']['directed'])
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
