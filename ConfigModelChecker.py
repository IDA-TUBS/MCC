#!/usr/bin/env python

import xml.etree.ElementTree as ET

import networkx as nx

import logging
import argparse

parser = argparse.ArgumentParser(description='Check config model XML.')
parser.add_argument('file', metavar='xml_file', type=str, 
        help='XML file to be processed')
parser.add_argument('--dotpath', type=str,
        help='Write graphs to DOT files in this path.')

args = parser.parse_args()

################
# main section #
################

class Edge:
    def __init__(self, source, target, attr):
        self.source = source
        self.target = target
        self.attr   = attr

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

class PatternManager:
    def __init__(self, composite, repo):
        self.patterns = dict()
        self.repo = repo

        self.parse_patterns(composite)

    def parse_patterns(self, composite):
        if composite in self.patterns.keys():
            return

        patterns = { "dismissed" : set(), "options" : set() }
        for p in composite.findall("pattern"):
            if "chosen" not in patterns.keys():
                patterns["chosen"] = p

            patterns["options"].add(p)

        self.patterns[composite] = patterns

    def get_alternatives(self, composite):
        self.parse_patterns(composite)
        return self.patterns[composite]['options'] - self.patterns[composite]['dismissed']

    def find_compatible(self, composite, callback):
        self.parse_patterns(composite)

        found = False
        for alt in self.get_alternatives(composite):
            if self.compatible(alt, callback):
                if not found:
                    self.patterns[composite]['chosen'] = alt
                    found = True
            else:
                self.patterns[composite]['dismissed'].add(alt)

        return found

    def compatible(self, pattern, callback):
        # find components, error if not unambiguous
        for c in pattern.findall("component"):
            if not callback(self._get_component_from_repo(c)):
                logging.info("Pattern incompatible")
                return False

        return True

    def _get_component_from_repo(self, c):
        matches = self.repo._find_element_by_attribute("component", { "name" : c.get("name") })
        if len(matches) > 1:
            logging.critical("Pattern references ambiguous component '%s'." % c.get("name"))

        return matches[0]

    def components(self, composite):
        components = set()
        for c in self.patterns[composite]['chosen'].findall("component"):
            components.add(self._get_component_from_repo(c))

        return components

    def component_exposing_service(self, composite, servicename):
        result = set()
        for c in self.patterns[composite]['chosen'].findall('component'):
            if c.find('expose') is not None:
                for s in c.find('expose').findall('service'):
                    if s.get('name') == servicename:
                        result.add(self._get_component_from_repo(c))

        if len(result) == 0:
            logging.error("Service '%s' is not exposed by pattern." % servicename)

        elif len(result) > 1:
            logging.error("Service '%s' is exposed multiple times by pattern." % servicename)

        return result.pop()

    def components_requiring_external_service(self, composite, functionname, servicename, label=None):
        result = set()
        for c in self.patterns[composite]['chosen'].findall('component'):
            if c.find('route') is not None:
                for s in c.find('route').findall('service'):
                    if s.get('name') == servicename:
                        slabel = None
                        if 'label' in s.keys():
                            slabel = s.get('label')

                        if label is None or slabel == label:
                            if s.find('external') is not None:
                                if functionname is not None:
                                    if 'function' in s.find('external').keys() and s.find('external').get('function') == functionname:
                                        result.add((self._get_component_from_repo(c), slabel))
                                else:
                                    result.add((self._get_component_from_repo(c), slabel))
                        else:
                            logging.info("label mismatch %s != %s" % (slabel, label))

        return result

    def add_to_graph(self, composite, system_graph):
        child_lookup = dict()
        name_lookup = dict()
        # first, add all components and create lookup table by child name
        for c in self.patterns[composite]['chosen'].findall("component"):
            component = system_graph.add_component(self._get_component_from_repo(c))
            name_lookup[c.get('name')] = component
            child_lookup[c] = component

        # second, add connections
        for c in self.patterns[composite]['chosen'].findall("component"):
            if c.find('route') is not None:
                for s in c.find('route').findall('service'):
                    if s.find('child') is not None:
                        name = s.find('child').get('name')
                        if name not in name_lookup:
                            logging.critical("Cannot satisfy internal route to child '%s' of pattern." % name)
                        else:
                            child_lookup[c].route_to(system_graph, s.get('name'), name_lookup[name], s.get('label'))

        # return set of added nodes
        return child_lookup.values()

class SystemGraph:
    def __init__(self, repo):
        # the query graph contains the requested functions/composites/components (as nodes) and their explicit routes (edges)
        self.query_graph = nx.DiGraph()

        # the component graph models the selected atomic components (as nodes) and their service routes (as edges)
        self.component_graph = nx.DiGraph()
        self.mapping_component2query = dict() # map nodes to nodes in query graph
        self.mapping_session2query = dict()   # map edges to edges in query graph

        # the subsystem graph models the hierarchical structure of the subsystems
        self.subsystem_graph = nx.DiGraph()
        self.mapping_query2subsystem = dict() # map nodes in query graph to nodes
        self.subsystem_root = None

        self.mapping_proxy2subsystem = dict()

        self.repo = repo

        self.functions = dict()

        self.node_type_styles = { "subsystem" : ["shape=tab", "colorscheme=set39", "fillcolor=2", "style=filled"],
                                  "function"  : "shape=rectangle, colorscheme=set39, fillcolor=5, style=filled",
                                  "composite" : "shape=component, colorscheme=set39, fillcolor=9, style=filled",
                                  "component" : "shape=component, colorscheme=set39, fillcolor=6, style=filled" }
        
        self.edge_type_styles = { "subsystem"   : "",
                                  "service"     : "arrowhead=normal",
                                  "function"    : "arrowhead=normal, style=dotted, colorscheme=set39, color=3",
                                  "mapping"     : "arrowhead=none, style=dashed, color=dimgray" }

    def add_subsystem(self, subsystem, parent=None):
        self.subsystem_graph.add_node(subsystem)

        if parent is not None:
            if parent not in self.subsystem_graph:
                raise Exception("Cannot find parent '%s' in subsystem graph." % parent)
            self.subsystem_graph.add_edge(parent, subsystem)
        else:
            self.subsystem_root = subsystem

    def add_query(self, child, subsystem):
        # FIXME reset/invalidate component graph
        assert(len(self.component_graph) == 0)

        self.query_graph.add_node(child, dismissed=set())
        self.mapping_query2subsystem[child] = subsystem

        if "component" in child.keys():
            components = self.repo._find_element_by_attribute("component", { "name" : child.get("component") })
            if len(components) == 0:
                logging.error("Cannot find referenced child component '%s'." % child.get("component"))
            else:
                if len(components) > 1:
                    logging.info("Multiple candidates found for child component '%s'." % child.get("component"))

                self.query_graph.node[child]['chosen']    = components[0]
                self.query_graph.node[child]['options']   = set(components)

        elif "composite" in child.keys():
            components = self.repo._find_element_by_attribute("composite", { "name" : child.get("composite") })
            if len(components) == 0:
                logging.error("Cannot find referenced child composite '%s'." % child.get("composite"))
            else:
                if len(components) > 1:
                    logging.info("Multiple candidates found for child composite '%s'." % child.get("composite"))

                self.query_graph.node[child]['chosen']    = components[0]
                self.query_graph.node[child]['options']   = set(components)
                self.query_graph.node[child]['patterns']  = PatternManager(components[0], self.repo)

        elif "function" in child.keys():
            functions = self.repo._find_function_by_name(child.get("function"))
            
            if len(functions) == 0:
                logging.error("Cannot find referenced child function '%s'." % child.get("function"))
            else:
                if len(functions) > 1:
                    logging.info("Multiple candidates found for child function '%s'." % child.get("function"))

                self.query_graph.node[child]['chosen']    = functions[0]
                self.query_graph.node[child]['options']   = set(functions)
                if functions[0].tag == "composite":
                    self.query_graph.node[child]['patterns']  = PatternManager(functions[0], self.repo)
                self.add_function(child.get("function"), child)

    def parse_routes(self):
        # parse routes between children
        for child in self.query_graph.nodes():
            if child.find("route") is not None:
                for s in child.find("route").findall("service"):
                    if s.find("child") is not None:
                        for target in self.query_graph.nodes():
                            if target.get("name") == s.find("child").get("name"):
                                # we check later whether the target component actually provides this service
                                edge = self.add_query_edge(child, target, {'service' : s.get("name")})
                                if 'label' in s.keys():
                                    edge.attr['label'] = s.get('label')
                                break
                            elif target.get("function") == s.find("child").get("name"):
                                # we check later whether the target component actually provides this service
                                edge = self.add_query_edge(child, target, {'service' : s.get("name"), 'function' : target.get('function')})
                                if 'label' in s.keys():
                                    edge.attr['label'] = s.get('label')
                                break
                    else:
                        raise Exception("ERROR")
        return

    def add_function(self, name, child):
        if name in self.functions.keys():
            loggging.error("Function '%s' cannot be present multiple times." % name) 
        else:
            self.functions[name] = child

    def subsystems(self, subsystem):
        return self.subsystem_graph.successors(subsystem)

    def children(self, subsystem):
        if subsystem is None:
            return self.query_graph.nodes()

        children = set()
        for child in self.mapping_query2subsystem.keys():
            if self.mapping_query2subsystem[child] == subsystem:
                children.add(child)

        return children

    def explicit_routes(self, child):
        res_in = list()
        for e in self.query_in_edges(child):
            res_in.append(e.attr)

        res_out = list()
        for e in self.query_out_edges(child):
            res_out.append(e.attr)

        return res_in, res_out

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
            patternmanager = None if 'patterns' not in self.query_graph.node[child] else self.query_graph.node[child]['patterns']
            if patternmanager is not None:
                for c in patternmanager.patterns[chosen]['chosen'].findall('component'):
                    if c.find('route') is not None:
                        for s in c.find('route').findall('service'):
                            if s.find('external') is not None and s.find('external').get('function') is not None:
                                fname = s.find('external').get('function')
                                provider = self.functions[fname]

                                slabel = None
                                if 'label' in s.keys():
                                    slabel = s.get('label')

                                sname = s.get('name')

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

    def query_in_edges(self, node):
        edges = list()
        for (s, t, d) in self.query_graph.in_edges(node, data=True):
            edges = edges + d['container']

        return edges

    def query_out_edges(self, node):
        edges = list()
        for (s, t, d) in self.query_graph.out_edges(node, data=True):
            edges = edges + d['container']

        return edges

    def query_edges(self, nbunch=None):
        edges = list()
        for (s, t, d) in self.query_graph.edges(nbunch=nbunch, data=True):
            edges = edges + d['container']

        return edges

    def add_query_edge(self, s, t, attr):
        edge = Edge(s, t, attr)
        if self.query_graph.has_edge(s, t):
            self.query_graph.edge[s][t]['container'].append(edge)
        else:
            self.query_graph.add_edge(s, t, { 'container' : [edge] })

        return edge

    def remove_query_edge(self, edge):
        if self.query_graph.has_edge(edge.source, edge.target):
            self.query_graph.edge[edge.source][edge.target]['container'].remove(edge)
            if len(self.query_graph.edge[edge.source][edge.target]['container']) == 0:
                self.query_graph.remove_edge(edge.source, edge.target)
        else:
            raise Exception("trying to remove non-existing edge")

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


class SubsystemConfig:
    def __init__(self, root_node, parent, model):
        self.root = root_node
        self.parent = parent
        self.model = model
        self.rte = None
        self.specs = set()

    def parse(self):
        # add subsystem to graph
        self.graph().add_subsystem(self, self.parent)

        for sub in self.root.findall("subsystem"):
            name = sub.get("name")
            subsystem = SubsystemConfig(sub, self, self.model)
            subsystem.parse()

        # parse <specs>
        for s in self.root.findall("spec"):
            self.specs.add(s.get("name"))


        # parse <child> nodes
        for c in self.root.findall("child"):
            self.graph().add_query(c, self)

    def _check_specs(self, component, child=None):
        if component.tag == "composite":
            return True

        system_specs = self.system_specs()

        component_specs = set()
        if component.find("requires") is not None:
            for spec in component.find("requires").findall("spec"):
                component_specs.add(spec.get("name"))


        for spec in component_specs:
            if spec not in system_specs:
                logging.info("Component '%s' incompatible because of spec requirement '%s'." % (component.get("name"), spec))
                return False

        return True

    def _check_rte(self, component, child=None):
        if component.tag == "composite":
            return True

        rtename = self.rte.find("provides").find("rte").get("name")

        if self.get_rte(component) != rtename:
            logging.info("Component '%s' is incompatible because of RTE requirement '%s' does not match '%s'." % (self.get_rte(component), rtename))
            return False

        return True

    def is_compatible(self, component):
        if not self._check_specs(component):
            return False

        if not self._check_rte(component):
            return False

        return True

    def _check_function_requirement(self, component, child=None):
        if component.find("requires") is not None:
            for f in component.find("requires").findall("function"):
                if f.get("name") not in self.provided_functions():
                    logging.error("Function '%s' required by '%s' is not explicitly instantiated." % (f.get("name"), component.get("name")))
                    return False

        return True

    def _choose_compatible(self, callback, check_pattern=True):
        for c in self.graph().children(self):
            if not self.graph().find_compatible_component(c, callback, check_pattern):
                return False

        return True

    # check and select compatible components (regarding to specs)
    def match_specs(self):
        for sub in self.graph().subsystems(self):
            if not sub.match_specs():
                return False

        return self._choose_compatible(self._check_specs)

    def get_rte(self, component):
        if component.find("requires") is not None:
            rte = component.find("requires").find("rte")
            if rte is not None:
                return rte.get("name")

        return "native"

    def select_rte(self):
        for sub in self.graph().subsystems(self):
            if not sub.select_rte():
                return False

        # build set of required RTEs
        required_rtes = set()
        for c in self.graph().children(self):
            for comp in self.graph().components(c):
                required_rtes.add(self.get_rte(comp))

        if len(required_rtes) == 0:
            required_rtes.add("native")

        if len(required_rtes) > 1:
            # FIXME find alternatives and patterns for each candidate rte
            logging.critical("RTE undecidable: %s. (TO BE IMPLEMENTED)" % required_rtes)
            return False
        else:
            # find component which provides this rte
            for p in self.model._root.iter("provides"):
                for r in p.findall("rte"):
                    if r.get("name") in required_rtes:
                        if self.rte is None:
                            self.rte = [x for x in self.model._root.iter("component") if x.find("provides") is p][0]
                        else:
                            logging.warn("Multiple provider of RTE '%s' found. (TO BE IMPLEMENTED)" % r.get("name")) 

            if self.rte is None:
                logging.critical("Cannot find provider for RTE '%s'." % required_rtes.pop())
                return False

        # dismiss all components in conflict with selected RTE
        return self._choose_compatible(self._check_rte)

    def filter_by_function_requirements(self):
        for sub in self.graph().subsystems(self):
            if not sub.filter_by_function_requirements():
                return False

        return self._choose_compatible(self._check_function_requirement, check_pattern=False)

    def parent_services(self):
        return self.parent.services()

    def child_services(self):
        # return child services
        services = set()
        for c in self.graph().children(self):
            services.update(self.graph().provisions(c))

        return services

    def system_specs(self):
        return self.parent.system_specs() | self.specs

    def services(self):
        return self.parent_services() | self.child_services()

    def provided_functions(self):
        return self.parent.provided_functions()

    def graph(self):
        return self.parent.graph()

class SystemConfig(SubsystemConfig):
    def __init__(self, root_node, model):
        SubsystemConfig.__init__(self, root_node, None, model)
        self.specs = set()
        self.system_graph = SystemGraph(model)

    def graph(self):
        return self.system_graph

    def parse(self):
        SubsystemConfig.parse(self)

        # parse routes
        self.graph().parse_routes()

    def select_rte(self):
        result = SubsystemConfig.select_rte(self)

        if result:
            if self.rte.find('provides').find('rte').get('name') != "native":
                logging.error("Top-level RTE must be 'native' (found: %s)." % (self.rte.find('provides').find('rte').get('name')))

        return result

    def _check_explicit_routes(self, component, child):
        # check provisions for each incoming edge
        provides, requires = self.graph().explicit_routes(child)
        for p in provides:
            if 'function' in p:
                found = False
                if component.find('provides') is not None:
                    if len(self.model._find_element_by_attribute('function', { 'name' : p['function'] }, component)):
                        found = True

                if not found:
                    logging.info("Child component '%s' does not provide function '%s'." % (component.get('name'), p['function']))
                    return False

            else: # service
                found = False
                if component.find('provides') is not None:
                    if len(self.model._find_element_by_attribute('service', { 'name' : p['service'] }, component.find('provides'))):
                        found = True
                if not found:
                    logging.info("Child component '%s' does not provide service '%s'." % (component.get('name'), p['service']))
                    return False

        # check requirements for each outgoing edge
        for r in requires:
            found = False
            if component.find('requires') is not None:
                if len(self.model._find_element_by_attribute('service', { 'name' : r['service'] }, component.find('requires'))):
                    found = True
            if not found:
                logging.info("Child component '%s' does not require routed service '%s'." % (component.get('name'), r['service']))
                return False

        return True

    def connect_functions(self):
        # choose compatible components based on explicit routes
        for c in self.graph().children(None):
            if not self.graph().find_compatible_component(c, self._check_explicit_routes, check_pattern=False):
                logging.critical("Failed to satisfy explicit routes for child '%s'." % c.attrib)
                return False

        if not self.graph().connect_functions():
            return False

        # solve reachability
        if not self.graph().insert_proxies():
            logging.critical("Cannot insert proxies.")
            return False

        # connect function requirements of proxies
        if not self.graph().connect_functions():
            return False

        return True

    def solve_dependencies(self):

        self.graph().build_component_graph()

        # check/expand explicit routes (uses protocol to solve compatibility problems)
        if not self.graph().solve_routes():
            return False

        # solve pending requirements
        # warn if multiple candidates exist and dependencies are not decidable
        if not self.graph().solve_pending():
            return False

        if not self.graph().insert_muxers():
            return False

        # (heuristically) map unmapped components to lowest subsystem
        if not self.graph().map_unmapped_components():
            return False

        # merge non-singleton components
        self.graph().merge_components(singleton=False)

        return True

    def parent_services(self):
        parent_services = set()

        if self.root.find("parent-provides") is not None:
            for p in self.root.find("parent-provides").findall("service"):
                parent_services.add(p.get("name"))

        return parent_services

    def system_specs(self):
        return self.specs

    def provided_functions(self):
        return self.graph().functions

class ConfigModelParser:

    def __init__(self, config_model_file):
        self._file = config_model_file
        self._tree = ET.parse(self._file)
        self._root = self._tree.getroot()

        self._structure = { "binary" : { "required-attrs" : ["name"], "children" : { "component" : { "min" : 0,
                                                                                                     "required-attrs" : ["name"],
                                                                                                     "optional-attrs" : ["version"]
                                                                                                   } }
                            },
                            "component" : { "required-attrs" : ["name"], "optional-attrs" : ["singleton", "version"], "children" : {
                                "provides" : { "children" : { "service" : { "required-attrs" : ["name"],
                                                                            "optional-attrs" : ["max_clients", "filter"], },
                                                              "rte"     : { "required-attrs" : ["name"] } } },
                                "requires" : { "children" : { "service" : { "required-attrs" : ["name"],
                                                                            "optional-attrs" : ["label", "filter"],
                                                                            "children" : {
                                                                                "exclude-component" : { 
                                                                                    "required-attrs" : ["name"],
                                                                                    "optional-attrs" : ["version_above", "version_below"]
                                                                                    }
                                                                                }},
                                                              "rte"     : { "max" : 1, "required-attrs" : ["name"] },
                                                              "spec"    : { "required-attrs" : ["name"] } } },
                                "proxy"    : { "required-attrs" : ["carrier"] },
                                "function"    : { "required-attrs" : ["name"] },
                                "filter"   : { "max" : 1, "optional-attrs" : ["alias"], "children" : {
                                    "add"    : { "required-attrs" : ["tag"] },
                                    "remove" : { "required-attrs" : ["tag"] },
                                    "reset"  : { "required-attrs" : ["tag"] },
                                    }
                                },
                                "mux"      : { "required-attrs" : ["service"] },
                                "protocol" : { "required-attrs" : ["from", "to"] },
                                "defaults" : { "leaf" : False },
                                }
                            },
                            "composite" : { "optional-attrs" : ["name"], "children" : {
                                "provides" : { "children" : { "service" : { "required-attrs" : ["name"],
                                                                            "optional-attrs" : ["max_clients"] } } },
                                "requires" : { "children" : { "service" : { "required-attrs" : ["name"],
                                                                            "optional-attrs" : ["label", "filter", "function"] } } },
                                "proxy"    : { "required-attrs" : ["carrier"] },
                                "function"    : { "required-attrs" : ["name"] },
                                "filter"   : { "max" : 1, "children" : {
                                    "add"    : { "required-attrs" : ["tag"] },
                                    "remove" : { "required-attrs" : ["tag"] },
                                    "reset"  : { "required-attrs" : ["tag"] },
                                    }
                                },
                                "mux"      : { "required-attrs" : ["service"] },
                                "protocol" : { "required-attrs" : ["from", "to"] },
                                "pattern"  : { "min" : 1, "children" : {
                                    "component" : { "min" : 1, "required-attrs" : ["name"], "children" : {
                                        "route" : { "max" : 1, "children" : {
                                            "service" :  { "required-attrs" : ["name"], "optional-attrs" : ["label"],  "children" : {
                                                "external"  : { "optional-attrs" : ["function"] },
                                                "child"    : { "required-attrs" : ["name"] }
                                                }}
                                            }},
                                        "expose" : { "max" : 1, "children" : {
                                            "service" : { "required-attrs" : ["name"] }
                                            }},
                                        "config" : { "leaf" : False }
                                        }}
                                    }}
                                }
                            },
                            "system" : { "max" : 1, "children" : {
                                "spec"      : { "required-attrs" : ["name"] },
                                "parent-provides" : { "max" : 1, "children" : {
                                    "service" : { "required-attrs" : ["name"] }
                                    }},
                                "child"     : { "optional-attrs" : ["function","component","composite","name"], "children" : {
                                    "route" : { "max" : 1, "children" : {
                                        "service" :  { "required-attrs" : ["name"], "optional-attrs" : ["label"],  "children" : {
                                            "child"    : { "required-attrs" : ["name"] }
                                            }}
                                        }},
                                    "config"   : { "leaf" : False },
                                    "resource" : { "required-attrs" : ["name", "quantum"] },
                                    }},
                                "default-routes" : { "leaf" : False },
                                "subsystem" : { "required-attrs" : ["name"], "recursive-children" : True }
                                }},
                          }

        # find <config_model>
        if self._root.tag != "config_model":
            self._root = self._root.find("config_model")
            if self._root == None:
                raise Exception("Cannot find <config_model> node.")

    def _find_function_by_name(self, name):
        function_providers = list()
        # iterate components
        for c in self._root.findall("component"):
            for f in self._find_element_by_attribute("function", { "name" : name }, root=c):
                function_providers.append(c)

        # iterate composites
        for c in self._root.findall("composite"):
            for f in self._find_element_by_attribute("function", { "name" : name }, root=c):
                function_providers.append(c)

        return function_providers

    def _find_element_by_attribute(self, elementname, attrs=dict(), root=None):
        if root is None:
            root = self._root

        # non-recursively iterate nodes <'elementname'>
        elements = list()
        for e in root.findall(elementname):
            match = True
            for attr in attrs.keys():
                if e.get(attr) != attrs[attr]:
                    match = False
                    break

            if match:
                elements.append(e)

        return elements

    def _get_component_classes(self, component_node):
        classes = set()
        if component_node.find("protocol") is not None:
            classes.add("protocol")

        if component_node.find("proxy") is not None:
            classes.add("proxy")

        if component_node.find("filter") is not None:
            classes.add("filter")

        if component_node.find("mux") is not None:
            classes.add("mux")

        if component_node.find("provides") is not None:
            if component_node.find("function") is not None:
                classes.add("function")

        return classes

    def _find_component_by_class(self, classification=None):
        components = list()

        for c in self._root.findall("component"):
            classes = self._get_component_classes(c)
            if classification is None and len(classes) == 0:
                components.append(c)
            elif classification is not None and classification in classes:
                components.append(c)

        for c in self._root.findall("composite"):
            classes = self._get_component_classes(c)
            if classification is None and len(classes) == 0:
                components.append(c)
            elif classification is not None and classification in classes:
                components.append(c)

        return components

    def _find_provisions(self, node="service", name=None):
        provisions = list()
        for p in self._root.iter("provides"):
            for s in p.findall(node):
                if name is None or s.get("name") == name:
                    provisions.append(s)

        # also get provisions from <parent-provides> in <system>
        for p in self._root.iter("parent-provides"):
            for s in p.findall(node):
                if name is None or s.get("name") == name:
                    provisions.append(s)

        return provisions

    def _find_proxies(self, service):
        result = set()
        for p in self._find_component_by_class('proxy'):
            if p.find('provides').find('service').get('name') == service:
                result.add(p)

        return result

    # check whether all function names are only provided once
    def check_functions_unambiguous(self):
        # set of known function names
        functionnames = set()

        # iterate all provisions and function names
        for p in self._root.iter("provides"):
            for f in p.findall("function"):
                if f.get("name") in functionnames:
                    logging.info("Function '%s' is not unambiguous." % f.get("name"))
                else:
                    functionnames.add(f.get("name"))

    # check whether all component names are only defined once
    def check_components_unambiguous(self):
        # set of known component names
        names = set()
        versioned_names_checked = set()

        # iterate atomic components
        for c in self._root.findall("component"):
            if c.get("name") in names:
                if c.get("name") not in versioned_names_checked:
                    # only check once whether all components with this name have a version
                    components = self._find_element_by_attribute("component", {"name" : c.get("name")})
                    versions = set()
                    for comp in components:
                        if "version" not in comp.keys():
                            logging.error("Component '%s' is not unambiguous and has no version." % c.get("name"))
                        elif comp.get("version") in versions:
                            logging.error("Component '%s' with version '%s' is ambiguous." % (c.get("name"), comp.get("version")))
                        else:
                            versions.add(comp.get("version"))

                    versioned_names_checked.add(c.get("name"))
            else:
                names.add(c.get("name"))

    # check whether components are unambiguously classified as function, filter, mux, proxy, protocol or None
    def check_classification_unambiguous(self):
        for c in self._root.findall("component"):
            classes = self._get_component_classes(c)
            if len(classes) > 1:
                logging.warn("Component '%s' is ambiguously classified as: %s" % (c.get("name"), classes))

        for c in self._root.findall("composite"):
            classes = self._get_component_classes(c)
            if len(classes) > 1:
                logging.warn("Composite '%s' is ambiguously classified as: %s" % (c.get("name"), classes))

    def _check_provisions(self, component):
        if component.find("provides") is None:
            return

        provides = set()
        for p in component.find("provides").findall("service"):
            # the same service cannot be provided twice
            if p.get("name") in provides:
                logging.error("Found multiple provision of service '%s'." % (p.get("name")))
            else:
                provides.add(p.get("name"))

    def _check_requirements(self, component):
        if component.find("requires") is None:
            return

        services = set()
        for r in component.find("requires").findall("service"):
            # service required twice must be distinguished by label
            if r.get("name") in services:
                labels = set()
                functions = set()
                if "label" not in r.keys() and "function" not in r.keys():
                    logging.error("Requirement <service name=\"%s\" /> is ambiguous and must therefore specify a label." %(r.get("name")))
                elif r.get("label") in labels:
                    logging.error("Requirement <service name=\"%s\" label=\"%s\" /> is ambiguous" % (r.get("name"), r.get("label")))
                elif r.get("function") in functions:
                    logging.error("Requirement <service name=\"%s\" function=\"%s\" /> is ambiguous" % (r.get("name"), r.get("function")))
                elif "label" in r.keys():
                    labels.add(r.get("label"))
                elif "function" in r.keys():
                    functions.add(r.get("function"))
            else:
                services.add(r.get("name"))

            # referenced filter must be defined
            # FIXME check in a later stage that filter tags of connected component are correct (analysis engine)

        # functions must not be required twice
        functions = set()
        for f in component.find("requires").findall("function"):
            if f.get("name") in functions:
                logging.error("Requirement <function name=\"%s\" /> is ambiguous." %(f.get("name")))
            else:
                functions.add(f.get("name"))

        # required services must be available
        for s in services:
            provisions = self._find_provisions("service", s)
            if len(provisions) == 0:
                logging.error("Requirement <service name=\"%s\" /> cannot be satisfied." % s)

        # required functions must be available
        for f in functions:
            provisions = self._find_provisions("function", f)
            if len(provisions) == 0:
                logging.error("Requirement <function name=\"%s\" /> cannot be satisfied." % f)

        # required rte must be available
        for r in component.find("requires").findall("rte"):
            provisions = self._find_provisions("rte", r.get("name"))
            if len(provisions) == 0:
                logging.error("Requirement <rte name=\"%s\" /> cannot be satisfied." % r.get("name"))

    def _check_proxy(self, component, proxy):
        carrier = proxy.get("carrier")

        provideproxy = None
        for p in component.find("provides").findall("service"):
            if p.get("name") != carrier:
                if provideproxy is None:
                    provideproxy = p.get("name")
                else:
                    logging.error("Proxy '%s' provides multiple services." % (component.get("name")))

        requireproxy = None
        for r in component.find("requires").findall("service"):
            if r.get("name") != carrier:
                if requireproxy is None:
                    requireproxy = r.get("name")
                else:
                    logging.error("Proxy '%s' requires multiple services." % (component.get("name")))

        # only a single (and the same) service must be provided and required
        if provideproxy != requireproxy:
            logging.warning("Proxy '%s' does not provide and require the same service." % component.get("name"))

    def _check_protocol(self, component, protocol):
        required = protocol.get("from")
        provided = protocol.get("to")

        if len(self._find_element_by_attribute("service", { "name" : required }, component.find("requires"))) == 0:
            logging.error("Protocol from service '%s' cannot be implemented by component '%s' due to missing service requirement." % (required, component.get("name")))

        if len(self._find_element_by_attribute("service", { "name" : provided }, component.find("provides"))) == 0:
            logging.error("Protocol to service '%s' cannot be implemented by component '%s' due to missing service provision." % (provided, component.get("name")))

    def _check_mux(self, component, mux):
        service = mux.get("service")
        if len(self._find_element_by_attribute("service", { "name" : service }, component.find("requires"))) == 0:
            logging.error("Mux of service '%s' cannot be implemented by component '%s' due to missing service requirement." % (service, component.get("name")))

        if len(self._find_element_by_attribute("service", { "name" : service }, component.find("provides"))) == 0:
            logging.error("Mux of service '%s' cannot be implemented by component '%s' due to missing service provision." % (service, component.get("name")))

    def _check_filter(self, component, filter):
        # nothing to be done (yet)
        return

    def _check_pattern(self, composite, pattern):

        required_services = dict()
        provided_services = dict()

        for c in pattern.findall("component"):
            cname = c.get("name")

            required_services[cname] = { "specified" : set(), "used" : set(), "external" : set() }
            provided_services[cname] = { "specified" : set(), "used" : set(), "exposed" : set() }

            # referenced components must be specified 
            cspecs = self._find_element_by_attribute("component", { "name" : cname })
            if len(cspecs) == 0:
                logging.error("Pattern of composite '%s' references unspecified component '%s'." %
                        (composite.get("name"), cname))

            # store specified service requirements/provisions
            for cspec in cspecs:
                tmp = set()
                if cspec.find("requires") is not None:
                    for s in cspec.find("requires").findall("service"):
                        tmp.add(s.get("name"))
                required_services[cname]["specified"].update(tmp)

                tmp = set()
                if cspec.find("provides") is not None:
                    for s in cspec.find("provides").findall("service"):
                        tmp.add(s.get("name"))
                provided_services[cname]["specified"].update(tmp)

            # references in <route> must be specified
            if c.find("route") is not None:
                for s in c.find("route").findall("service"):
                    sname = s.get("name")
                    required_services[cname]["used"].add(sname)

                    for cspec in cspecs:
                        if len(self._find_element_by_attribute("service", { "name" : sname }, cspec.find("requires"))) == 0:
                            logging.error("Routing of unknown service requirement to '%s' found for component '%s' in composite '%s'." % (sname, cname, composite.get("name")))

#                    if s.find("function") != None:
#                        fname = s.find("function").get("name")
#                        if len(self._find_element_by_attribute("function", { "name" : fname }, composite.find("requires"))) == 0:
#                            logging.error("Routing of service '%s' to function '%s' does not match composite spec '%s'." % (sname, fname, composite.get("name")))

                    if s.find("child") != None:
                        chname = s.find("child").get("name")
                        if len(self._find_element_by_attribute("component", { "name" : chname }, pattern)) == 0:
                            logging.error("Routing of service '%s' to child '%s' of composite '%s' not possible." % (sname, chname, composite.get("name")))
                        else:
                            provided_services[chname]["used"].add(sname)

                    if s.find("external") != None:
                        required_services[cname]["external"].add(sname)

            # references in <expose> must be specified
            if c.find("expose") is not None:
                for s in c.find("expose").findall("service"):
                    sname = s.get("name")
                    provided_services[cname]["used"].add(sname)
                    provided_services[cname]["exposed"].add(sname)
                    if len(self._find_element_by_attribute("service", { "name" : sname }, composite.find("provides"))) == 0:
                        logging.error("Exposed service '%s' does not match composite spec '%s'." % (sname, composite.get("name")))

        # required external service must be pending exactly once
        # or explicitly routed to external service
        if composite.find("requires") is not None:
            for s in composite.find("requires").findall("service"):
                sname = s.get("name")
                pending_count = 0
                for r in required_services.values():
                    if sname in r['external']:
                        pending_count = 1
                        break

                    if sname in r["specified"] - r["used"]:
                        pending_count += 1

                if pending_count != 1:
                    logging.error("Service '%s' required by composite '%s' cannot be identified in pattern." % (sname, composite.get("name")))

        # provided external service must be either exposed or pending exactly once
        if composite.find("provides") is not None:
            for s in composite.find("provides").findall("service"):
                sname = s.get("name")
                exposed_count = 0
                pending_count = 0
                for p in provided_services.values():
                    if sname in p["exposed"]:
                        exposed_count += 1
                    if sname in p["specified"] - p["used"]:
                        pending_count += 1

                if exposed_count > 1:
                    logging.error("Service '%s' exposed multiple times in composite '%s'." % (sname, composite.get("name")))
                elif exposed_count == 0 and pending_count != 1:
                    logging.error("Service '%s' provided by composite '%s' cannot be identified in pattern." % (sname, composite.get("name")))

    # perform model check for <component> nodes: 
    def check_atomic_components(self):
        for c in self._root.findall("component"):
            self._check_provisions(c)
            self._check_requirements(c)

            # check <proxy>
            for p in c.findall("proxy"):
                self._check_proxy(c, p)

            # check <protocol>
            for p in c.findall("protocol"):
                self._check_protocol(c, p)

            # check <mux>
            for m in c.findall("mux"):
                self._check_mux(c, m)

            # check <filter>
            for f in c.findall("filter"):
                self._check_filter(c, f)

    # perform model check for <composite> nodes: 
    def check_composite_components(self):
        for c in self._root.findall("composite"):
            self._check_provisions(c)
            self._check_requirements(c)

            # check <proxy>
            for p in c.findall("proxy"):
                self._check_proxy(c, p)

            # check <protocol>
            for p in c.findall("protocol"):
                self._check_protocol(c, p)

            # check <mux>
            for m in c.findall("mux"):
                self._check_mux(c, m)

            # check <filter>
            for f in c.findall("filter"):
                self._check_filter(c, f)

            # check <pattern>
            for p in c.findall("pattern"):
                self._check_pattern(c, p)

    def check_system(self):
        # check function/composite/component references, compatibility and routes in system and subsystems

        system = SystemConfig(self._root.find("system"), self)
        system.parse()

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

    # check whether binaries are pointing to specified components
    def check_binaries(self):
        for b in self._root.findall("binary"):
            components = b.findall("component")
            if len(components) > 0:
                for c in components:
                    # find component by name
                    if len(self._find_element_by_attribute("component", { "name" : c.get("name") })) == 0:
                        logging.error("Binary '%s' refers to non-existent component '%s'." %(b.get("name"), c.get("name")))
            else:
                # find component by binary name
                if len(self._find_element_by_attribute("component", { "name" : b.get("name") })) == 0:
                    logging.error("Binary '%s' refers to non-existent component '%s'." %(b.get("name"), b.get("name")))

    # check XML structure
    def check_structure(self, root=None, structure=None):
        if root is None:
            root = self._root
        if structure is None:
            structure = self._structure

        node_count = dict()
        # iterate direct child nodes
        for node in root:
            if node.tag in structure.keys():
                # count number of appearances
                if node.tag in node_count:
                    node_count[node.tag] += 1
                else:
                    node_count[node.tag] = 1

                # check node attributes
                attr_present = node.keys()
                attr_required = list()
                attr_optional = list()
                if "required-attrs" in structure[node.tag]:
                    attr_required = structure[node.tag]["required-attrs"]
                if "optional-attrs" in structure[node.tag]:
                    attr_optional = structure[node.tag]["optional-attrs"]
                attr_allowed  = attr_required + attr_optional

                for attr in attr_present:
                    if attr not in attr_allowed:
                        logging.error("Unexpected attribute '%s' of node '<%s>'." % (attr, node.tag))

                for attr in attr_required:
                    if attr not in attr_present:
                        logging.error("Required attribute '%s' not found for node '<%s>'." % (attr, node.tag))

                # check children
                leaf = True
                if "leaf" in structure[node.tag]:
                    leaf = structure[node.tag]["leaf"]

                if "children" in structure[node.tag]:
                    self.check_structure(node, structure[node.tag]["children"])
                elif "recursive-children" in structure[node.tag] and structure[node.tag]["recursive-children"]:
                    self.check_structure(node, structure)
                elif leaf:
                    self.check_structure(node, dict())
                
            else:
                logging.error("Unexpected node '<%s>' below '<%s>'." % (node.tag, root.tag))

        # check node_count
        for tag in structure.keys():
            found = 0
            if tag in node_count:
                found = node_count[tag]

            if "min" in structure[tag]:
                if found < structure[tag]["min"]:
                    logging.error("Node '<%s>' must be present %d times below '<%s>' (found %d)." % 
                            (tag, structure[tag]["min"], root.tag, found))
            if "max" in structure[tag]:
                if found > structure[tag]["max"]:
                    logging.error("Node '<%s>' must not be present more than %d times below '<%s>' (found %d)." % 
                            (tag, structure[tag]["max"], root.tag, found))
                


if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    parser = ConfigModelParser(args.file)

    parser.check_structure()
    parser.check_functions_unambiguous()
    parser.check_components_unambiguous()
    parser.check_classification_unambiguous()
    parser.check_binaries()
    parser.check_atomic_components()
    parser.check_composite_components()
    parser.check_system()
