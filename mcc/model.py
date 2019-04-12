"""
Description
-----------

Implements model-specific data structures which are used by our cross-layer model.

:Authors:
    - Johannes Schlatow

"""
import copy

from mcc.parser import *
from mcc.framework import *
from mcc.backtracking import *
from mcc.taskmodel import Task
from mcc.dot import DotFactory

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


class NetworkManager:
    def __init__(self, subnet, prefix_len=24):
        assert prefix_len < 32
        self.num_ips  = 2**(32-prefix_len) - 1

        self.start_ip   = self._ip_to_integer(subnet)
        self.end_ip     = self.start_ip + self.num_ips
        self.current_ip = self.start_ip

        self.registry = dict()

    def _ip_to_integer(self, ip):
        assert isinstance(ip, list) and len(ip) == 4

        return ip[0] << 24 | ip[1] << 16 | ip[2] << 8 | ip[1];

    def _integer_to_ip(self, i):
        return [(i >> 24) & 0xFF,
                (i >> 16) & 0xFF,
                (i >> 8)  & 0xFF,
                i & 0xFF]

    def lookup_or_allocate(self, idx, num=1):
        if idx not in self.registry:
            self.registry[idx] = list()
            for i in range(num):
                self.registry[idx].append(self.allocate_ip())

        return self.registry[idx]

    def allocate_ip(self):
        self.current_ip += 1
        assert self.current_ip <= self.end_ip

        return self._integer_to_ip(self.current_ip)


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

    def reset(self):
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
            functions.update(inst.component.functions())

        return functions

    def components(self):
        return self._instances

    def __repr__(self):
        return "Base on %s" % self.subsystem()

    #######################
    # Component interface #
    #######################

    def properties(self):
        return set()

    def prio(self):
        return 0

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
            if function is None or function in inst.component.functions():
                services.update(inst.provides_services(name, ref))

        return list(services)

    def providing_component(self, service, function=None, to_ref=None):
        for inst in self._instances:
            if function is not None and function not in inst.component.functions():
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

    def __repr__(self):
        return 'Proxy %s via %s' % (self.service.name, self.carrier)

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
        self.add_layer(Layer('task_graph', nodetypes={Task}))

        self.platform = platform
        self.repo = repo
        self.dotpath = dotpath

    def find_parents(self, child, cur_layer, in_layer=None, parent_type=None):
        """ Find nodes in upper layer `in_layer` or of type `parent_type` that have a correspondence
            connection to `child`.
        """
        assert in_layer is not None or parent_type is not None
        assert in_layer is None or in_layer in self.by_name.keys() or in_layer in self.by_name.values()
        assert cur_layer in self.by_name.keys() or cur_layer in self.by_name.values()

        layer    = self.by_name[cur_layer] if cur_layer in self.by_name.keys() else cur_layer

        if in_layer is not None:
            in_layer = self.by_name[in_layer] if in_layer in self.by_name.keys() else in_layer

            if cur_layer is in_layer:
                return ({ child }, cur_layer)
        else:
            if isinstance(child, parent_type):
                return ({ child }, cur_layer)

        parent_layer = self._prev_layer(layer)
        if parent_layer is None:
            return set()

        # perform a breadth-first search
        parents = layer._get_param_value(parent_layer.name, child)
        if isinstance(parents, set):
            result = set()
            for p in parents:
                found, layer = self.find_parents(p, parent_layer, in_layer, parent_type)
                result.update(found)
            return result, layer
        else:
            return self.find_parents(parents, parent_layer, in_layer, parent_type)

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
                    for node in fa.graph.nodes():
                        if node is not c:
                            funcs = copy.copy(node.functions())
                            if hasattr(node, 'query'):
                                for provider in self.repo.find_components_by_type(node.query(), node.type()):
                                    funcs.update(provider.functions())

                            if depfunc in funcs:
                                if list(fa._get_param_candidates('mapping', node))[0].in_native_domain(pf_component):
                                    local_match = node
                                else:
                                    remote_match = node

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
            DotFactory(self, self.platform).write_layer(layer.name, self.dotpath+layer.name+suffix+".dot")

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

