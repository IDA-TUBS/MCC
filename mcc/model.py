from . import parser

# wrapper class to allow multiple nodes of the same component
class Component:
    def __init__(self, xml_node):
        self.xml = xml_node

    def route_to(self, system_graph, service, component, label=None):
        # check component specifications
        if not self.requires(service):
            logging.error("Cannot route service '%s' of component '%s' which does not require this service." % (service, self.xml.get('name')))
            return False

        if not component.provides(service):
            logging.error("Cannot route service '%s' to component '%s' which does not provide this service." % (service, component.xml.get('name')))
            return False

        # add edge
        attribs = {'service' : service}
        if label is not None and label != 'None':
            attribs['label'] = label

        return system_graph.add_component_edge(self, component, attribs)

    def max_clients(self, name):
        if self.xml.find('provides') is not None:
            for s in self.xml.find('provides').findall('service'):
                if s.get('name') == name:
                    if 'max_clients' in s.keys():
                        return int(s.get('max_clients'))

        return float('inf')

    def connections(self, system_graph, name):
        i = 0
        for e in system_graph.component_in_edges(self):
            if e.attr['service'] == name:
                i += 1

        return i

    def connected(self, system_graph, name, label):
        for e in system_graph.component_out_edges(self):
            if e.attr['service'] == name:
                if label is not None and label != 'None':
                    if 'label' in e.attr and e.attr['label'] == label:
                        return True
                else:
                    return True

        return False

    def provides(self, name, provisiontype='service'):
        if self.xml.find('provides') is not None:
            for s in self.xml.find('provides').findall(provisiontype):
                if s.get('name') == name:
                    return True

        return False

    def requires(self, name, requirementtype='service'):
        if self.xml.find('requires') is not None:
            for s in self.xml.find('requires').findall(requirementtype):
                if s.get('name') == name:
                    return True

        return False

    def is_comp(self, component):
        return component is self.xml

    def component(self):
        return self.xml

class PlatformModel(object):

    def __init__(self):
        self.platform_graph = nx.DiGraph()

    def reachable(self, from_component, to_component):
        # TODO implement
        return

class SubsystemModel(PlatformModel):
    # the subsystem graph models the (hierarchical) structure of the subsystems

    def __init__(self):
        PlatformModel.__init__(self)
        self.subsystem_root = None
        self.subsystem_graph = self.platform_graph

    def add_subsystem(self, subsystem, parent=None):
        self.subsystem_graph.add_node(subsystem)

        if parent is not None:
            if parent not in self.subsystem_graph:
                raise Exception("Cannot find parent '%s' in subsystem graph." % parent)
            self.subsystem_graph.add_edge(parent, subsystem)
        else:
            self.subsystem_root = subsystem


class SystemModel(framework.Registry):
    def __init__(self, repo):
        add_layer('func_arch')
        add_layer('comm_arch')
        add_layer('comp_arch')
        add_layer('comp_inst')

        self.platform_graph = PlatformModel()

        self.repo = repo

        self.node_type_styles = { "subsystem" : ["shape=tab", "colorscheme=set39", "fillcolor=2", "style=filled"],
                                  "function"  : "shape=rectangle, colorscheme=set39, fillcolor=5, style=filled",
                                  "composite" : "shape=component, colorscheme=set39, fillcolor=9, style=filled",
                                  "component" : "shape=component, colorscheme=set39, fillcolor=6, style=filled" }
        
        self.edge_type_styles = { "subsystem"   : "",
                                  "service"     : "arrowhead=normal",
                                  "function"    : "arrowhead=normal, style=dotted, colorscheme=set39, color=3",
                                  "mapping"     : "arrowhead=none, style=dashed, color=dimgray" }

    def reset(self):
        # TODO reset/invalidate all graphs
        return

    def add_query(self, child, platform_component=None):
        # FIXME reset/invalidate component graph
        assert(len(self.component_graph) == 0)

        # add node to functional architecture layer
        fa = self.by_name['func_arch']
        fa.add_node(child)

        # set pre-defined mapping
        if platform_component is not None:
            fa.node.set_param_candidates('mapping', child, set([platform_component]))

        # set pre-defined transformation patterns
        if "component" in child.keys():
            components = self.repo._find_element_by_attribute("component", { "name" : child.get("component") })
            if len(components) == 0:
                logging.error("Cannot find referenced child component '%s'." % child.get("component"))
            else:
                if len(components) > 1:
                    logging.info("Multiple candidates found for child component '%s'." % child.get("component"))

                fa.set_param_candidates('components', child, set(components))

        elif "composite" in child.keys():
            components = self.repo._find_element_by_attribute("composite", { "name" : child.get("composite") })
            if len(components) == 0:
                logging.error("Cannot find referenced child composite '%s'." % child.get("composite"))
            else:
                if len(components) > 1:
                    logging.info("Multiple candidates found for child composite '%s'." % child.get("composite"))

                fa.set_param_candidates('components', child, set(components))
#                self.query_graph.node[child]['patterns']  = PatternManager(components[0], self.repo)

        elif "function" in child.keys():
            functions = self.repo._find_function_by_name(child.get("function"))
            
            if len(functions) == 0:
                logging.error("Cannot find referenced child function '%s'." % child.get("function"))
            else:
                if len(functions) > 1:
                    logging.info("Multiple candidates found for child function '%s'." % child.get("function"))

                fa.set_param_candidates('components', child, set(functions))
#                if functions[0].tag == "composite":
#                    self.query_graph.node[child]['patterns']  = PatternManager(functions[0], self.repo)
#                self.add_function(child.get("function"), child)

#    def add_function(self, name, child):
#        if name in self.functions.keys():
#            loggging.error("Function '%s' cannot be present multiple times." % name) 
#        else:
#            self.functions[name] = child

    def subsystems(self, subsystem):
        return self.subsystem_graph.successors(subsystem)

    def children(self, subsystem):
        # TODO refactor
        if subsystem is None:
            return self.query_graph.nodes()

        children = set()
        for child in self.mapping_query2subsystem.keys():
            if self.mapping_query2subsystem[child] == subsystem:
                children.add(child)

        return children

#    def explicit_routes(self, child):
#        res_in = list()
#        for e in self.query_in_edges(child):
#            res_in.append(e.attr)
#
#        res_out = list()
#        for e in self.query_out_edges(child):
#            res_out.append(e.attr)
#
#        return res_in, res_out

    def get_alternatives(self, child):
        return self.query_graph.node[child]['options'] - self.query_graph.node[child]['dismissed']

    def get_options(self, child):
        return self.query_graph.node[child]['options']

    def provisions(self, child, provisiontype='service'):
        result = set()
        chosen = self.query_graph.node[child]['chosen']
        if chosen.find("provides") is not None:
            for p in chosen.find("provides").findall(provisiontype):
                result.add(p.get('name'))

        return result

    def components(self, child):
        chosen = self.query_graph.node[child]['chosen']
        if chosen.tag == "component":
            return set(chosen)
        else: # composite
            return self.query_graph.node[child]['patterns'].components(chosen)

    def choose_component(self, child, component):
        # FIXME reset/invalidate component graph
        assert(len(self.component_graph) == 0)
        # FIXME we might wanna check whether 'component' is in 'options' - 'dismissed'
        self.query_graph.node[child]['chosen'] = component

    def exclude_component(self, child, component):
        # FIXME we might wanna check whether 'component' is in 'options'
        self.query_graph.node[child]['dismissed'].add(component)

    def _compatible(self, child, component, callback, check_pattern):
        if not callback(component, child):
            return False
        elif component.tag == "composite" and check_pattern:
            return self.query_graph.node[child]['patterns'].find_compatible(component, callback)

        return True

    def find_compatible_component(self, child, callback, check_pattern=True):
        # FIXME reset/invalidate component graph
        assert(len(self.component_graph) == 0)

        found = False
        # try non-dismissed alternatives
        for alt in self.get_alternatives(child):
            if self._compatible(child, alt, callback, check_pattern):
                if not found:
                    self.choose_component(child, alt)
                    found = True
            else:
                self.exclude_component(child, alt)

        if not found:
            names = [ x.get("name") for x in self.get_options(child) ]
            logging.error("No compatible component found for child '%s' among %s." % (child.attrib, names))
            return False

        return True

    def connect_functions(self):
        for child in self.query_graph.nodes():
            chosen = self.query_graph.node[child]['chosen']
            if chosen.find('requires') is not None:
                for f in chosen.find('requires').findall('function'):

                    # function requirements are only allowed for composites
                    assert(chosen.tag == "composite")
                    fname = f.get('name')
                    provider = self.functions[fname]
                    # get services from chosen composite pattern
                    for (sname, slabel) in self.query_graph.node[child]['patterns'].services_routed_to_function(chosen, fname):
                        # skip if edge already exists
                        exists = False
                        for e in self.query_out_edges(child):
                            if ('label' not in e.attr or e.attr['label'] == slabel) and e.attr['service'] == sname:
                                if 'function' in e.attr:
                                    if e.attr['function'] == fname:
                                        exists = True
                                else:
                                    exists = True

                        if not exists:
                            self.add_query_edge(child, provider, { 'service' : sname, 'label' : slabel, 'function' : fname})

        return True

#    def query_in_edges(self, node):
#        edges = list()
#        for (s, t, d) in self.query_graph.in_edges(node, data=True):
#            edges = edges + d['container']
#
#        return edges
#
#    def query_out_edges(self, node):
#        edges = list()
#        for (s, t, d) in self.query_graph.out_edges(node, data=True):
#            edges = edges + d['container']
#
#        return edges
#
#    def query_edges(self, nbunch=None):
#        edges = list()
#        for (s, t, d) in self.query_graph.edges(nbunch=nbunch, data=True):
#            edges = edges + d['container']
#
#        return edges
#
#    def add_query_edge(self, s, t, attr):
#        edge = Edge(s, t, attr)
#        if self.query_graph.has_edge(s, t):
#            self.query_graph.edge[s][t]['container'].append(edge)
#        else:
#            self.query_graph.add_edge(s, t, { 'container' : [edge] })
#
#        return edge
#
#    def remove_query_edge(self, edge):
#        if self.query_graph.has_edge(edge.source, edge.target):
#            self.query_graph.edge[edge.source][edge.target]['container'].remove(edge)
#            if len(self.query_graph.edge[edge.source][edge.target]['container']) == 0:
#                self.query_graph.remove_edge(edge.source, edge.target)
#        else:
#            raise Exception("trying to remove non-existing edge")

    def add_component(self, component_xml):
        node = Component(component_xml)
        self.component_graph.add_node(node)
        return node

    def component_in_edges(self, node):
        edges = list()
        for (s, t, d) in self.component_graph.in_edges(node, data=True):
            edges = edges + d['container']

        return edges

    def component_out_edges(self, node):
        edges = list()
        for (s, t, d) in self.component_graph.out_edges(node, data=True):
            edges = edges + d['container']

        return edges

    def component_edges(self, nbunch=None):
        edges = list()
        for (s, t, d) in self.component_graph.edges(nbunch=nbunch, data=True):
            edges = edges + d['container']

        return edges

    def add_component_edge(self, s, t, attr):
        edge = Edge(s, t, attr)
        if self.component_graph.has_edge(s, t):
            self.component_graph.edge[s][t]['container'].append(edge)
        else:
            self.component_graph.add_edge(s, t, { 'container' : [edge] })

        return edge

    def remove_component_edge(self, edge):
        if self.component_graph.has_edge(edge.source, edge.target):
            self.component_graph.edge[edge.source][edge.target]['container'].remove(edge)
            if len(self.component_graph.edge[edge.source][edge.target]['container']) == 0:
                self.component_graph.remove_edge(edge.source, edge.target)
        else:
            raise Exception("trying to remove non-existing edge")

    def build_component_graph(self):
        # iterate children and add chosen components to graph
        for child in self.query_graph.nodes():
            chosen = self.query_graph.node[child]['chosen']
            if 'patterns' in self.query_graph.node[child]:
                nodes = self.query_graph.node[child]['patterns'].add_to_graph(chosen, self)
                for n in nodes:
                    self.mapping_component2query[n] = child

                    # dirty 'hack'
                    if self.mapping_query2subsystem[child] is None:
                        self.mapping_proxy2subsystem[n] = None
            else:
                assert(chosen.tag == "component")
                n = Component(chosen)
                self.component_graph.add_node(n)
                self.mapping_component2query[n] = child

    def _get_provider(self, child, service):
        chosen = self.query_graph.node[child]['chosen']
        if chosen.tag == 'component':
            return chosen
        else:
            # find provider in pattern
            return self.query_graph.node[child]['patterns'].component_exposing_service(chosen, service)

    def _get_clients(self, child, function, service):
        chosen = self.query_graph.node[child]['chosen']
        if chosen.tag == 'component':
            matches = self.repo._find_element_by_attribute('service', { name : service }, chosen.find('requires'))
            if len(matches) > 1:
                logging.error("Cannot decide which service to use.")

            match = matches.pop()
            label = None
            if 'label' in match.keys():
                label = match.get('label')
            return set((chosen, label))
        else:
            return self.query_graph.node[child]['patterns'].components_requiring_external_service(chosen, function, service)

    def _source_components(self, child, function, service):
        source_candidates = set()
        for comp in self.mapping_component2query.keys():
            if self.mapping_component2query[comp] == child:
                source_candidates.add(comp)

        assert(len(source_candidates) > 0)

        source_nodes = set()
        if len(source_candidates) > 1:
            for comp, label in self._get_clients(child, function, service):
                for c in source_candidates:
                    if c.is_comp(comp):
                        source_nodes.add((c, label))

            assert(len(source_nodes) > 0)
        else:
            source_nodes = set([(source_candidates.pop(), None)])

        return source_nodes

    def _target_component(self, child, service):
        target_candidates = set()
        for comp in self.mapping_component2query.keys():
            if self.mapping_component2query[comp] == child:
                target_candidates.add(comp)

        assert(len(target_candidates) > 0)

        if len(target_candidates) > 1:
            comp = self._get_provider(child, service)
            if comp is None:
                return

            target_node = None
            for c in target_candidates:
                if c.is_comp(comp):
                    target_node = c

            assert(target_node)
        else:
            target_node = target_candidates.pop()

        return target_node

    def _add_connections(self, edge, source_nodes, target_node, service):
        for source_node,label in source_nodes:
            cedge = source_node.route_to(self, service, target_node, label)
            # add mapping
            self.mapping_session2query[cedge] = edge

    def _connect_children(self, edge, service):
        # find components
        function = None
        if 'function' in edge.attr:
            function = edge.attr['function']

        source_nodes = self._source_components(edge.source, function, service)
        target_node = self._target_component(edge.target, service)

        self._add_connections(edge, source_nodes, target_node, service)

    def insert_protocol(self, prot, edge, from_service, to_service):
        node = Component(prot)
        self.component_graph.add_node(node)

        # remark: in order to map protocol components to subsystems, we insert a mapping to a dummy 'query' node
        self.mapping_component2query[node] = node
        self.mapping_query2subsystem[node] = None

        source_nodes = self._source_components(edge.source, None, to_service)
        target_node  = self._target_component(edge.target, from_service)

        self._add_connections(edge, source_nodes, node, to_service)
        self._add_connections(edge, [(node, None)], target_node, from_service)

    def solve_routes(self):
        for e in self.query_edges():
            req_service = e.attr['service']
            label = None
            if label in e.attr:
                label = e.attr['label']

            if 'function' in e.attr:
                # check compatibility
                provisions = self.provisions(e.target)
                if req_service in provisions:
                    # connect children
                    self._connect_children(e, req_service)
                else:
                    # search and insert protocol stack (via repo)
                    logging.info("Connecting '%s' to '%s' via service '%s' requires a protocol stack." % (e.source.attrib,
                        e.target.attrib, req_service))
                    found = False
                    for c in self.repo._find_component_by_class('protocol'):
                        if found:
                            break
                        for prot in c.findall('protocol'):
                            if prot.get('to') == req_service:
                                if prot.get('from') in provisions:
                                    # check specs and RTE
                                    sub1 = self.mapping_query2subsystem[e.source]
                                    sub2 = self.mapping_query2subsystem[e.target]
                                    if sub1.is_compatible(c) or sub2.is_compatible(c):
                                        found = True
                                        self.insert_protocol(c, e, prot.get('from'), prot.get('to'))
                                        break

                    if not found:
                        logging.critical("Cannot find suitable protocol stack from='%s' to='%s'." % (req_service, provisions))
                        return False

            else: # service
                self._connect_children(e, req_service)

        return True

    def solve_pending(self):
        for comp in self.component_graph.nodes():
            xml = comp.component()
            if xml.find('requires') is not None:
                for s in xml.find('requires').findall('service'):
                    if not comp.connected(self, s.get('name'), s.get('label')):
                        # find reachable service provider
                        found = False
                        for prov in self.component_graph.nodes():
                            if prov.provides(s.get('name')):
                                sub_p = self.mapping_query2subsystem[self.mapping_component2query[prov]]
                                sub_r = self.mapping_query2subsystem[self.mapping_component2query[comp]]
                                if sub_p == sub_r or nx.has_path(self.subsystem_graph, sub_p, sub_r):
                                    comp.route_to(self, s.get('name'), prov, s.get('label'))
                                    found = True
                                    break

                        if found:
                            logging.info("Connecting pending service '%s' (label='%s') of component '%s'." % (s.get('name'), s.get('label'), xml.get('name')))
                        else:
                            logging.info("Cannot solve pending service requirement '%s' (label='%s') of component '%s'." % (s.get('name'), s.get('label'), xml.get('name')))

        return True

    def write_query_node(self, dotfile, child, prefix="  "):
        label = ""
        if 'composite' in child.keys():
            label = "label=\"%s\"," % child.get('composite')
            style = self.node_type_styles['composite']
        elif 'component' in child.keys():
            label = "label=\"%s\"," % child.get('component')
            style = self.node_type_styles['component']
        elif 'function' in child.keys():
            label = "label=\"%s\"," % child.get('function')
            style = self.node_type_styles['function']

        if 'name' in child.keys():
            label = "label=\"%s\"," % child.get('name')

        dotfile.write("%s%s [%s%s];\n" % (prefix, self.query_graph.node[child]['id'], label, style))

    def write_query_edge(self, dotfile, v, u, attrib, prefix="  "):
        if 'function' in attrib:
            style = self.edge_type_styles['function']
            label = "label=\"%s\"," % attrib['function']
        else:
            style = self.edge_type_styles['service']
            label = "label=\"%s\"," % attrib['service']

        dotfile.write("%s%s -> %s [%s%s];\n" % (prefix,
                                                self.query_graph.node[v]['id'],
                                                self.query_graph.node[u]['id'],
                                                label,
                                                style))

    def write_component_node(self, dotfile, comp, prefix="  "):
        label = "label=\"%s\"," % comp.xml.get('name')
        style = self.node_type_styles['component']

        dotfile.write("%s%s [%s%s];\n" % (prefix, self.component_graph.node[comp]['id'], label, style))

    def write_component_edge(self, dotfile, v, u, attrib, prefix="  "):
        style = self.edge_type_styles['service']
        label = "label=\"%s\"," % attrib['service']

        dotfile.write("%s%s -> %s [%s%s];\n" % (prefix,
                                                self.component_graph.node[v]['id'],
                                                self.component_graph.node[u]['id'],
                                                label,
                                                style))

    def write_query_dot(self, filename):
        # TODO continue refactoring
    
        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")
            dotfile.write("  compound=true;\n")

            # write subsystem nodes
            i = 1
            n = 1
            clusternodes = dict()
            for sub in self.subsystem_graph.nodes():
                # generate and store node id
                self.subsystem_graph.node[sub]['id'] = "cluster%d" % i
                i += 1

                label = ""
                if 'name' in sub.root.keys():
                    label = "label=\"%s\";" % sub.root.get('name')

                style = self.node_type_styles['subsystem']
                dotfile.write("  subgraph %s {\n    %s\n" % (self.subsystem_graph.node[sub]['id'], label))
                for s in style:
                    dotfile.write("    %s;\n" % s)

                # add children of this subsystem
                for ch in self.query_graph.nodes():
                    # only process children in this subsystem
                    if self.mapping_query2subsystem[ch] is not sub:
                        continue

                    self.query_graph.node[ch]['id'] = "ch%d" % n
                    n += 1
                    # remember first child node as cluster node
                    if sub not in clusternodes:
                        clusternodes[sub] = self.query_graph.node[ch]['id']

                    self.write_query_node(dotfile, ch, prefix="    ")

                # add internal dependencies
                for e in self.query_edges():
                    if self.mapping_query2subsystem[e.source] == sub and self.mapping_query2subsystem[e.target] == sub:
                        self.write_query_edge(dotfile, e.source, e.target, e.attr, prefix="    ")

                dotfile.write("  }\n")

            # write subsystem edges
            for e in self.subsystem_graph.edges():
                # skip if one of the subsystems is empty
                if e[0] not in clusternodes or e[1] not in clusternodes:
                    continue
                style = self.edge_type_styles['subsystem']
                dotfile.write("  %s -> %s [ltail=%s, lhead=%s, %s];\n" % (clusternodes[e[0]],
                                                      clusternodes[e[1]],
                                                      self.subsystem_graph.node[e[0]]['id'],
                                                      self.subsystem_graph.node[e[1]]['id'],
                                                      style))

            # add children with no subsystem
            for ch in self.query_graph.nodes():
                if self.mapping_query2subsystem[ch] is None:
                    self.query_graph.node[ch]['id'] = "ch%d" % n
                    n += 1
                    self.write_query_node(dotfile, ch)

            # add child dependencies between subsystems
            for e in self.query_edges():
                if self.mapping_query2subsystem[e.source] != self.mapping_query2subsystem[e.target]:
                    self.write_query_edge(dotfile, e.source, e.target, e.attr)

            dotfile.write("}\n")

        return

    def write_component_dot(self, filename):
        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")

            dotfile.write("  { rank = same;\n")
            # write query nodes
            n = 1
            for ch in self.query_graph.nodes():
                if not 'id' in self.query_graph.node[ch]:
                    self.query_graph.node[ch]['id'] = "chn%d" % n
                    n += 1

                self.write_query_node(dotfile, ch, prefix="    ")

            # connect query nodes
            for e in self.query_edges():
                self.write_query_edge(dotfile, e.source, e.target, e.attr, prefix="    ")

            dotfile.write("  }\n")

            dotfile.write("  { \n")

            # write component nodes
            n = 1
            for comp in self.component_graph.nodes():
                self.component_graph.node[comp]['id'] = "c%d" % n
                n += 1

                self.write_component_node(dotfile, comp, prefix="    ")

            # connect components
            for edge in self.component_edges():
                self.write_component_edge(dotfile, edge.source, edge.target, edge.attr, prefix="    ")

            dotfile.write("  }\n")

            # add mappings (nodes)
            for (comp, child) in self.mapping_component2query.items():
                if comp is child: # skip dummy mappings
                    continue

                style = self.edge_type_styles['mapping']
                if child is not None:
                    dotfile.write("  %s -> %s [%s];" % (self.query_graph.node[child]['id'],
                                                        self.component_graph.node[comp]['id'],
                                                        style))

            # remark: we cannot draw the mappings between edges

            dotfile.write("}\n")

    def _get_subsystem(self, component):
        if component in self.mapping_proxy2subsystem:
            return self.mapping_proxy2subsystem[component]
        else:
            return self.mapping_query2subsystem[self.mapping_component2query[component]]

    def write_subsystem_dot(self, filename):
        with open(filename, 'w+') as dotfile:
            dotfile.write("digraph {\n")
            dotfile.write("  compound=true;\n")

            # write subsystem nodes
            i = 1
            n = 1
            clusternodes = dict()
            for sub in self.subsystem_graph.nodes():
                # generate and store node id
                self.subsystem_graph.node[sub]['id'] = "cluster%d" % i
                i += 1

                label = ""
                if 'name' in sub.root.keys():
                    label = "label=\"%s\";" % sub.root.get('name')

                style = self.node_type_styles['subsystem']
                dotfile.write("  subgraph %s {\n    %s\n" % (self.subsystem_graph.node[sub]['id'], label))
                for s in style:
                    dotfile.write("    %s;\n" % s)

                # add components of this subsystem
                for comp in self.component_graph.nodes():
                    # only process children in this subsystem
                    if sub is not self._get_subsystem(comp):
                        continue

                    self.component_graph.node[comp]['id'] = "c%d" % n
                    n += 1

                    # remember first node as cluster node
                    if sub not in clusternodes:
                        clusternodes[sub] = self.component_graph.node[comp]['id']

                    self.write_component_node(dotfile, comp, prefix="    ")

                # add internal dependencies
                for edge in self.component_edges():
                    sub1 = self._get_subsystem(edge.source)
                    sub2 = self._get_subsystem(edge.target)
                    if sub1 == sub and sub2 == sub:
                        self.write_component_edge(dotfile, edge.source, edge.target, edge.attr, prefix="    ")

                dotfile.write("  }\n")

            # write subsystem edges
            for e in self.subsystem_graph.edges():
                # skip if one of the subsystems is empty
                if e[0] not in clusternodes or e[1] not in clusternodes:
                    continue
                style = self.edge_type_styles['subsystem']
                dotfile.write("  %s -> %s [ltail=%s, lhead=%s, %s];\n" % (clusternodes[e[0]],
                                                      clusternodes[e[1]],
                                                      self.subsystem_graph.node[e[0]]['id'],
                                                      self.subsystem_graph.node[e[1]]['id'],
                                                      style))

            # add child dependencies between subsystems
            for edge in self.component_edges():
                sub1 = self._get_subsystem(edge.source)
                sub2 = self._get_subsystem(edge.target)
                if sub1 != sub2:
                    self.write_component_edge(dotfile, edge.source, edge.target, edge.attr)

            dotfile.write("}\n")

    def add_proxy(self, proxy, edge):
        # remark: This is a good example why it is better to have another modelling layer (i.e. functional communication
        #         layer) as inserting a proxy obfuscated functional dependencies and the actual query.

        # remove edge between source and target
        self.remove_query_edge(edge)

        # add proxy node (create XML node)
        xml = ET.Element('child')
        xml.set('composite', proxy.get('name'))

        self.query_graph.add_node(xml, {'chosen' : proxy, 'options' : set(proxy), 'dismissed' : set()})
        self.query_graph.node[xml]['patterns'] = PatternManager(proxy, self.repo)

        # remark: the proxy cannot be mapped to a single subsystem
        self.mapping_query2subsystem[xml] = None

        # add edge from proxy to target
        self.add_query_edge(xml, edge.target, edge.attr)

        # add edge from source to proxy
        if 'function' in edge.attr.keys():
            del edge.attr['function']
        self.add_query_edge(edge.source, xml, edge.attr)

        return True

    def add_mux(self, mux, edge):
        # remove edge between source and target
        self.remove_component_edge(edge)

        # add mux node
        node = Component(mux)
        self.component_graph.add_node(node)

        # add dummy mapping
        self.mapping_component2query[node] = node
        self.mapping_query2subsystem[node] = None

        # add edge from mux to target
        self.add_component_edge(node, edge.target, edge.attr)

        # add edge from source to mux
        self.add_component_edge(edge.source, node, edge.attr)

        # change all other connections
        for e in self.component_in_edges(edge.target):
            if e.source is not node and e.attr['service'] == edge.attr['service']:
                self.remove_component_edge(e)
                self.add_component_edge(e.source, node, e.attr)

        return True

    def insert_muxers(self):
        for edge in self.component_edges():
            service = edge.attr['service']
            source_sys = self.mapping_query2subsystem[self.mapping_component2query[edge.source]]
            target_sys = self.mapping_query2subsystem[self.mapping_component2query[edge.target]]

            # check max_clients
            if edge.target.max_clients(service) < edge.target.connections(self, service):
                logging.info("Multiplexer required for service '%s' of component '%s'." % (service, edge.target.xml.get('name')))
                found = False
                for comp in self.repo._find_component_by_class("mux"):
                    if found:
                        break
                    for mux in comp.findall('mux'):
                        if mux.get('service') == service:
                            if (source_sys is not None and source_sys.is_compatible(comp)) or (target_sys is not None and target_sys.is_compatible(comp)):
                                found = self.add_mux(comp, edge)
                                break

                if not found:
                    logging.critical("No compatible mux found.")
                    return False

        return True

    def insert_proxies(self):
        for edge in self.query_edges():
            # check reachability
            source_sys = self.mapping_query2subsystem[edge.source]
            target_sys = self.mapping_query2subsystem[edge.target]

            # provider must be a parent
            if not nx.has_path(self.subsystem_graph, target_sys, source_sys):
                logging.info("Connecting '%s' to '%s' via service '%s' requires a proxy." % (edge.source.attrib, edge.target.attrib, edge.attr['service']))
                for proxy in self.repo._find_proxies(edge.attr['service']):
                    carrier = proxy.find('proxy').get('carrier')
                    # check that carrier is provided by both subsystems
                    if carrier in source_sys.services() and carrier in target_sys.services():
                        if source_sys.is_compatible(proxy) and target_sys.is_compatible(proxy):
                            return self.add_proxy(proxy, edge)
                    else:
                        logging.info("Cannot find carrier for proxy '%s' in all subsystems." % proxy.get('name'))

                logging.critical("No compatible proxy found.")
                return False

        return True

    def _get_subsystems_recursive(self, subsystem):
        unprocessed = set([subsystem])
        subsystems = list()
        while len(unprocessed):
            current = unprocessed.pop()
            current_subsystems = self.subsystem_graph.successors(current)
            subsystems = subsystems + current_subsystems
            unprocessed.update(current_subsystems)

        return subsystems

    def _get_parents_recursive(self, subsystem):
        unprocessed = set([subsystem])
        parents = list()
        while len(unprocessed):
            current = unprocessed.pop()
            current_parents = self.subsystem_graph.predecessors(current)
            parents = parents + current_parents
            unprocessed.update(current_parents)

        return parents

    def map_unmapped_components(self):
        for comp in self.component_graph.nodes():
            if self._get_subsystem(comp) is None:
                logging.info("mapping unmapped component '%s' to 'lowest' possible subsystem" % comp.xml.get('name'))
                candidates = set(self.subsystem_graph.nodes())

                # a) if component provides a service it must not be on a lower subsystem than its clients
                for (client, x) in self.component_graph.in_edges(comp, data=False):
                    # get subsystem of this client
                    sys = self._get_subsystem(client)
                    if sys is None:   # skip unmapped
                        continue

                    # skip parent
                    if self.subsystem_graph.in_degree(sys) == 0:
                        continue

                    # remove subsystems of client's subsystem from candidates
                    candidates = candidates & set([sys] + self._get_parents_recursive(sys))

                # b) if component requires a service it must be on the same or lower subsystem than its servers
                for (x, server) in self.component_graph.out_edges(comp, data=False):
                    # get subsystem of this server
                    sys = self._get_subsystem(server)
                    if sys is None:   # skip unmapped
                        continue

                    # remove subsystems of client's subsystem from candidates
                    candidates = candidates & set([sys] + self._get_subsystems_recursive(sys))

                # c) the subsystem must satisfy the RTE and spec requirements of the component
                for candidate in candidates:
                    if not candidate.is_compatible(comp.component()):
                        candidates.remove(candidate)

                if len(candidates) == 0:
                    logging.error("Cannot find compatible subsystem for unmapped component '%s'." % (comp.xml.get('name')))
                    return False

                best = candidates.pop()
                hierarchy = [self.subsystem_root] + self._get_subsystems_recursive(self.subsystem_root)
                if len(candidates) > 0:
                    # select lowest candidate subsystem in the hierarchy of subsystems
                    best_index = hierarchy.index(best)

                    for candidate in candidates:
                        index = hierarchy.index(candidate)
                        if index > best_index:
                            best_index = index
                            best = candidate

                if comp in self.mapping_proxy2subsystem:
                    self.mapping_proxy2subsystem[comp] = best
                else:
                    self.mapping_query2subsystem[self.mapping_component2query[comp]] = best

        return True

    def _merge_component(self, c1, c2):
        sub1 = self.mapping_query2subsystem[self.mapping_component2query[c1]]
        sub2 = self.mapping_query2subsystem[self.mapping_component2query[c2]]
        if sub1 == sub2:

            # redirect edges of c2
            for edge in self.component_in_edges(c2):
                if c1.max_clients(edge.attr['service']) <= c1.connections(self, edge.attr['service']):
                    logging.info("Merging components '%s' because of max_clients restriction." % c1.xml.get('name'))
                    return True

                self.component_graph.remove_edge(edge.source, edge.target)
                newedge = self.add_component_edge(edge.source, c1, edge.attr)
                if edge in self.mapping_session2query:
                    self.mapping_session2query[newedge] = self.mapping_session2query[edge]
                    del self.mapping_session2query[edge]

            logging.info("Merging components '%s'." % c1.xml.get('name'))

            # remove node
            self.component_graph.remove_node(c2)
            # remark: this actually removes information about from which query this component resulted
            del self.mapping_component2query[c2]
        else:
            logging.info("Not merging component '%s' because is present in different subsystems." % c1.xml.get('name'))

        return True

    def merge_components(self, singleton=True):

        # find duplicates
        processed = set()
        for comp in nx.topological_sort(self.component_graph, reverse=True):
            if comp in processed:
                continue

            # skip non-singleton components if we only operate on singletons
            if singleton and ('singleton' not in comp.xml.keys() or comp.xml.get('singleton').lower() != "true"):
                continue

            for dup in self.component_graph.nodes():
                if dup is not comp and dup.is_comp(comp.component()):
                    # duplicates must only be replaced if they connect to the same services
                    # -> as a result we need to iterate the nodes in reverse topological order
                    if self.component_graph.successors(comp) == self.component_graph.successors(dup):
                        processed.add(dup)
                        if not self._merge_component(comp, dup):
                            return False

        return True

class Mcc:

    def __init__(self):
        self.model = SystemModel()

    def search_config(self):
        # check function/composite/component references, compatibility and routes in system and subsystems

        # 1) we create a new system model
        self.model.reset()

        # 2) we parse the platform model (here: subsystem structure)
        # 3) we parse the queried components/functions from the subsystem structure
        config = SystemConfig(self._root.find("system"), self.model)
        config.parse()

        # TODO output parsed config

        # FIXME (continue refactoring)

        if not system.match_specs():
            logging.critical("abort")
            return False

        if not system.select_rte():
            logging.critical("abort")
            return False

        if not system.filter_by_function_requirements():
            logging.critical("abort")
            return False

        # connect functions
        if not system.connect_functions():
            logging.critical("abort")
            return False

        # draw query_graph (for devel/debugging/validation)
        if args.dotpath is not None:
            system.graph().write_query_dot(args.dotpath+"query_graph.dot")

        if not system.solve_dependencies():
            logging.critical("abort")
            return False

        if args.dotpath is not None:
            system.graph().write_component_dot(args.dotpath+"component_graph.dot")
            system.graph().write_subsystem_dot(args.dotpath+"subsystem_graph.dot")

        return True


