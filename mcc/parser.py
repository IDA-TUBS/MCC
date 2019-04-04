"""
Description
-----------

Implements XML parser classes for the component repository.

:Authors:
    - Johannes Schlatow

"""
try:
    from lxml import etree as ET
except ImportError:
    from xml.etree import ElementTree as ET

import logging

from mcc.graph import GraphObj, Edge
from mcc.taskmodel import *

class XMLParser:
    def __init__(self, xml_file, xsd_file=None):
        self._file = xml_file
        if self._file is not None:
            if hasattr(ET, "XMLSchema"):
                schema = None
                if xsd_file is not None:
                    schema = ET.XMLSchema(file=xsd_file)
                parser = ET.XMLParser(schema=schema)
            else:
                parser = ET.XMLParser()

            self._tree = ET.parse(self._file, parser=parser)
            self._root = self._tree.getroot()

class AggregateRepository:
    def __init__(self, *args):
        self.repos = list()
        for arg in args:
            if isinstance(arg, list):
                self.repos.extend(arg)
            else:
                self.repos.append(arg)

    def _iterate_repos_and_find(self, func):
        result = list()
        for repo in self.repos:
            result.extend(func(repo))

        return result

    def find_components_by_type(self, query, querytype):
        return self._iterate_repos_and_find(lambda repo: repo.find_components_by_type(query, querytype))

class Repository(XMLParser):

    class ElementWrapper:
        def __init__(self, xml_node):
            self.xml_node = xml_node

        def xml(self):
            return self.xml_node

        def __getstate__(self):
            return '<%s>' % self.xml_node.tag


    class ServiceIdentifier:
        def __init__(self, xml_node, ref=None):
            self.name = xml_node.get('name')

            if ref is not None:
                self.ref = ref
            else:
                self.ref  = xml_node.get('ref')

        def match_all(self, candidates):
            result = set()
            for cand in candidates:
                if self.ref is None:
                    if self.name == cand.name:
                        result.add(cand)
                elif cand == self:
                    result.add(cand)

            return result

        def find_match(self, repo, root):
            if self.ref is None:
                return repo._find_element_by_attribute("service", { "name" : self.name }, root)
            else:
                return repo._find_element_by_attribute("service", { "ref" : self.ref }, root)

        def __eq__(self, rhs):
            if rhs.ref == self.ref:
                if self.ref is None:
                    return self.name == rhs.name

                return True

            return False

        def __hash__(self):
            return hash('%s#%s' % (self.name, self.ref))

        def __repr__(self):
            return '%s#%s' % (self.name, self.ref)


    class Service:
        def __init__(self, xml_node):
            self.xml_node = xml_node

        def max_clients(self):
            return self.xml_node.get('max_clients')

        def label(self):
            return self.xml_node.get('label')

        def function(self):
            return self.xml_node.get('function')

        def name(self):
            return self.xml_node.get('name')

        def ref(self):
            return self.xml_node.get('ref');

        def matches(self, rhs):
            return self.name() == rhs.name()

        def out_traffic(self):
            traffic = self.xml_node.find('out-traffic')
            size = None
            msec = None
            pksz = None
            if traffic is not None:
                size = self._parse_size(traffic.get('size'))
                msec = int(traffic.get('interval_ms'))
                pksz = self._parse_size(traffic.get('package_size'))

            return size, msec, pksz

        def _parse_size(self, size):
            if size is None:
                return None
            if size[-1] == 'K':
                return int(size[:-1]) * 1024
            if size[-1] == 'M':
                return int(size[:-1]) * 1024 * 1024
            if size[-1] == 'G':
                return int(size[:-1]) * 1024 * 1024 * 1024
            if size[-1] == 'B':
                return int(size[:-1])

            return int(size)

        def __eq__(self, rhs):
            return self.xml_node == rhs.xml_node

        def __hash__(self):
            return hash(self.xml_node)

        def __repr__(self):
            f = '' if self.function() is None else '%s ' % self.function()
            n = '' if self.name() is None else 'via %s' % self.name()
            l = '' if self.label() is None else '.%s' % self.label()
            r = '' if self.ref() is None else ' as %s' % self.ref()

            return '%s%s%s%s' % (f, n, l, r)

        def __getstate__(self):
            return (self.function(),
                    self.name(),
                    self.label(),
                    self.ref(),
                    self.max_clients())

    class Component:
        def __init__(self, xml_node, repo):
            self.repo = repo
            self.xml_node = xml_node

        def uid(self):
            # if singleton, return (binary) name
            if self.singleton():
                return self.repo.get_binary_name(self.label())

            # else:
            return self.xml_node

        def binary_name(self):
            if self.xml_node.tag == 'composite':
                return None

            return self.repo.get_binary_name(self.label())

        def singleton(self):
            return self.xml_node.get('singleton')

        def dedicated(self):
            return not self.xml_node.get('shareable')

        def requires_quantum(self, name):
            quantum = self.xml_node.find('./requires/%s' % name)
            if quantum is not None:
                return int(quantum.get('quantum'))
            else:
                return 0

        def requires_rte(self):
            rte = self.xml_node.find('./requires/rte')
            if rte is not None:
                return rte.get('name')
            else:
                return 'native'

        def requires_specs(self):
            specs = set()
            for spec in self.xml_node.findall('./requires/spec'):
                specs.add(spec.get('name'))

            return specs

        def requires_functions(self):
            functions = set()
            if self.xml_node.tag == "composite":
                for s in self.xml_node.findall("./requires/service[@function]"):
                    functions.add(s.get("function"))

            return functions

        def requires_services(self, name=None, ref=None):
            services = list()
            for s in self.xml_node.findall("./requires/service"):
                if name is None or s.get('name') == name:
                    if ref is None or s.get('ref') == ref:
                        services.append(Repository.Service(s))

            return services

        def provides_services(self, name=None, ref=None, function=None):
            services = list()
            for s in self.xml_node.findall("./provides/service"):
                if name is None or s.get('name') == name:
                    if ref is None or s.get('ref') == ref:
                        services.append(Repository.Service(s))

            return services

        def _function(self):
            if self.xml_node.find('function') is not None:
                return self.xml_node.find('function').get('name')

            return None

        def functions(self):
            funcs = set()
            for f in self.xml_node.findall('function'):
                funcs.add(f.get('name'))

            return funcs

        def type(self):
            classes = self.repo._get_component_classes(self.xml_node)
            assert(len(classes) <= 1)
            if len(classes) == 1:
                return list(classes)[0]
            else:
                return None

        def service_for_function(self, function):
            for s in self.xml_node.findall("./requires/service[@function]"):
                if s.get('function') == function:
                    return Repository.Service(s)

        def label(self):
            name = self.xml_node.get('name')
            if name is not None:
                return name
            else:
                return 'anonymous'

        def defaults(self):
            return self.xml_node.find('./defaults')

        def unique_label(self):
            label  = self.label()
            binary = self.binary_name()
            if binary is not None and label != binary:
                return "%s-%s" % (label, binary)
            else:
                return label

        def patterns(self):
            result = set()
            if self.xml_node.tag == 'composite':
                for pat in self.xml_node.findall("./pattern"):
                    result.add(Repository.ComponentPattern(self, pat))
            else:
                result.add(self)

            return result

        def providing_component(self, service, function=None, to_ref=None):
            assert(service is None or len(self.provides_services(service)))
            return self, to_ref

        def requiring_component(self, service, function=None, to_ref=None):
            assert(service is None or len(self.requires_services(service)))
            return self, to_ref

        def flatten(self):
            # for composites, we must select a pattern first
            assert(self.xml_node.tag != 'composite')

            return set([self])

        def _taskgraph_objects(self, root, expect, **kwargs):
            # return tasks and tasklinks within given node
            objects = list()
            for node in root:
                if node.tag == 'task':
                    newtask = Task(name=node.get('name'),
                                   wcet=int(node.get('wcet')),
                                   bcet=int(node.get('bcet')),
                                   thread=self)
                    if len(objects):
                        if objects[-1].expect_out == 'server':
                            newtask.set_placeholder_in('server',
                                                       callertask=objects[-1])
                        else:
                            objects.append(Tasklink(objects[-1], newtask))
                    else:
                        newtask.set_placeholder_in(expect, **kwargs)

                    objects.append(newtask)

                elif node.tag == 'signal':
                    if node.get('junction'):
                        objects[-1].set_placeholder_out('junction',
                                                        name=node.get('junction'))
                    else:
                        objects[-1].set_placeholder_out('receiver',
                                                        to_ref=node.get('to_ref'))

                elif node.tag == 'call':
                    objects[-1].set_placeholder_out('server',
                                                    to_ref=node.get('to_ref'),
                                                    method=node.get('method'))

            if objects[0].expect_in == 'client':
                objects[-1].expect_out == 'client'

            return set(objects)

        def taskgraph_objects(self, rpc=None, method=None, signal=None):
            # find <timing>
            timing = self.xml_node.find('./timing')
            if timing is None:
                return set()

            if rpc is not None:
                if method is None:
                    node = timing.find('./on-rpc[@from_ref="%s"]' % rpc)
                else:
                    node = timing.find('./on-rpc[@from_ref="%s",@method="%s"]' % (rpc, method))

                assert node is not None, '<on-rpc from_ref="%s" method="%s"> not present' % (rpc, method)

                # TODO remember to connect junction placeholders (caller)
                # TODO remember to connect server placeholders
                return self._taskgraph_objects(node, 'client', from_ref=rpc, method=method)

            elif signal is not None:
                node = timing.find('./on-signal[@from_ref="%s"]' % signal)
                if node is not None:
                    return self._taskgraph_objects(node, 'sender', from_ref=signal)

                return set()

                # TODO remember to connect junction placeholders (caller)
                # TODO remember to connect server placeholders
            else:
                junction_objects = set()
                for junction_node in timing.findall('junction'):
                    junction_objects.update(self._taskgraph_objects(junction_node,
                                                                    'junction',
                                                                    junction_name=junction_node.get('name'),
                                                                    junction_type=junction_node.get('type')))

                objects = set()
                for time_node in timing.findall('on-time'):
                    objects.update(self._taskgraph_objects(time_node, None,
                                                           period=time_node.get('period')))

                # on-interrupt
                for interrupt_node in timing.findall('on-interrupt'):
                    objects.update(self._taskgraph_objects(interrupt_node, 'interrupt'))

#                # link to junctions
#                for task in objects:
#                    if task.expect_out == 'junction':
#                        for junction in junction_objects:
#                            if junction.expect_in == 'junction':
#                                objects.add(Tasklink(task, junction))
#                                task.set_placeholder_out(None)
#                        assert task.expect_out is None

                objects.update(junction_objects)

                # TODO remember to connect junction placeholders (caller)
                # TODO remember to connect server placeholders
                return objects

        def __repr__(self):
            return self.label()

        def __getstate__(self):
            return ( self.label(),
                     self.unique_label() )

    class ComponentPattern():
        def __init__(self, component, xml_node):
            self.repo = component.repo
            self.component = component
            self.xml_node = xml_node

        def label(self):
            return self.component.label()

        def requires_specs(self):
            return self.component.requires_specs

        def requires_rte(self):
            return self.component.requires_rte

        def providing_component(self, service, function=None, to_ref=None):
            result = set()
            ref = None
            for c in self.xml_node.findall("component"):
                for e in c.findall('./expose'):
                    if to_ref is None or e.get('ref') == to_ref:
                        for s in e.findall('./service'):
                            if service is not None and s.get('name') != service:
                                continue
                            if function is not None and c.find('function').get('name') != function:
                                continue

                            components = self.repo.find_components_by_type(c.get('name'), querytype='component')
                            assert(len(components) == 1)
                            result.add(components[0])
                            ref = s.get('ref')

            if len(result) == 0:
                logging.error("Service '%s' is not exposed in %s (Function %s, to_ref %s)." % (service, self.component, function, to_ref))
            elif len(result) > 1:
                logging.error("Service '%s' is exposed by multiple components (Function %s, to_ref %s)." % (service, function, to_ref))
            else:
                return list(result)[0], ref

            return None, None

        def requiring_component(self, service, function=None, to_ref=None):
            result = set()
            ref = None
            for c in self.xml_node.findall("component"):
                for s in c.findall('./route/service'):
                    if s.find('external') is not None:
                        if service is not None and s.get('name') != service:
                            continue

                        if to_ref is None or s.find('external').get('ref') == to_ref:
                            components = self.repo.find_components_by_type(c.get('name'), querytype='component')
                            assert(len(components) == 1)
                            result.add(components[0])
                            ref = s.get('ref')

            if len(result) == 0:
                logging.error("Service '%s' is not required by component pattern for '%s'." % (service, self.component.label()))
                logging.error("  (Function %s, to_ref %s)" % (function, to_ref))
            elif len(result) > 1:
                logging.error("Service '%s' (ref=%s) is required by multiple components." % (service, to_ref))
            else:
                return list(result)[0], ref

            return None, None

        def config(self):
            return self.xml_node.find('config')

        def flatten(self):
            # fill set with atomic components and their edges as specified in the pattern
            flattened = set()

            child_lookup = dict()
            name_lookup = dict()
            # first, add all components and create lookup table by child name
            for c in self.xml_node.findall("component"):
                components = self.repo.find_components_by_type(c.get('name'), querytype='component')
                name_lookup[c.get('name')] = components[0]
                # FIXME, we might have multiple options here
                assert len(components) == 1, 'Cannot resolve component in pattern unambiguously'

                child_lookup[c] = components[0]
                params = dict()
                config = c.find('./config')
                if config is not None:
                    params['pattern-config'] = Repository.ElementWrapper(config)
                flattened.add(GraphObj(components[0], params))

            # second, add connections
            for c in self.xml_node.findall("component"):
                for s in c.findall('./route/service'):
                    services = child_lookup[c].requires_services(s.get('name'), ref=s.get('ref'))
                    assert len(services) == 1, \
                        "Cannot unambigously determine composite-internal connection of service name %s, ref %s from component %s in composite %s" % (s.get('name'), s.get('ref'), c.get('name'), self.label())
                    source_service = services[0]

                    if s.find('child') is not None:
                        name = s.find('child').get('name')
                        if name not in name_lookup:
                            logging.critical("Cannot satisfy internal route to child '%s' of pattern." % name)
                        else:
                            provided = name_lookup[name].provides_services(name=s.get('name'))
                            assert(len(provided) == 1)
                            params = { 'source-service' : source_service, 'target-service' : provided[0]}
                            flattened.add(GraphObj(Edge(child_lookup[c], name_lookup[name]), params))

            return flattened

        def __getstate__(self):
            return self.label()

    class NodeNotFoundError(Exception):
        pass

    def __init__(self, config_model_file, xsd_file=None):
        XMLParser.__init__(self, config_model_file, xsd_file)

        if self._file is not None:
            # find <repository>
            if self._root.tag != "repository":
                self._root = self._root.find("repository")
                if self._root == None:
                    raise self.NodeNotFoundError("Cannot find <repository> node.")

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

    def find_proxies(self, service=None, carrier=None, query=None):
        carrier = None
        if query is not None:
            service = query['service']
            carrier = query['carrier']

        result = set()
        for p in self._find_component_by_class('proxy'):
            if service is None or p.find('provides').find('service').get('name') == service:
                if carrier is None or p.find('proxy').get('carrier') == carrier:
                    result.add(p)

        return result

    def find_muxers(self, service=None, query=None):
        service = None
        if query is not None:
            service = query['service']

        result = set()
        for m in self._find_component_by_class('mux'):
            if m.find('mux').get('service') == service:
                result.add(m)

        return result

    def find_protocolstacks(self, from_service=None, to_service=None, query=None):
        if query is not None:
            from_service = query['from_service']
            to_service   = query['to_service']

        result = set()
        for p in self._find_component_by_class('protocol'):
            if p.find('protocol').get('from') == from_service and p.find('protocol').get('to') == to_service:
                result.add(p)

        return result

    def find_components_by_type(self, query, querytype):
        if querytype == 'function':
            components = self._find_function_by_name(query)
        elif querytype == 'proxy':
            components = self.find_proxies(query=query)
        elif querytype == 'mux':
            components = self.find_muxers(query=query)
        elif querytype == 'proto':
            components = self.find_protocolstacks(query=query)
        else: # 'component' or 'composite'
            components = self._find_element_by_attribute('component', { "name" : query }) + \
                         self._find_element_by_attribute('composite', { "name" : query })

        return [Repository.Component(c, self) for c in components]

    def get_binary_name(self, component_name):
        cand = self._root.find("binary[@name='%s']" % component_name)
        if cand is not None:
            return cand.get('name')

        cand = self._root.find("binary/component[@name='%s']/.." % component_name)
        if cand is not None:
            return cand.get('name')

        logging.error("No binary found for component '%s'" % component_name)
        return None

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
            identifier = '%s#%s' % (p.get("name"), p.get("ref"))
            # the same service cannot be provided twice
            if identifier in provides:
                logging.error("Found multiple provision of service '%s'." % (identifier))
            else:
                provides.add(identifier)

    def _check_requirements(self, component):
        if component.find("requires") is None:
            return

        services = set()
        functions = set()
        for r in component.findall("./requires/service"):
            # service required twice must be distinguished by label or ref
            if r.get("name") in services:
                if "label" not in r.keys() and "ref" not in r.keys():
                    logging.error("Requirement <service name=\"%s\" /> is ambiguous and must therefore specify a label or ref." %(r.get("name")))
            else:
                services.add(r.get("name"))

            if 'function' in r.keys():
                functions.add(r.get('function'))

        # required services must be available
        for s in services:
            provisions = self._find_provisions("service", s)
            if len(provisions) == 0:
                logging.error("Requirement <service name=\"%s\" /> cannot be satisfied." % s)

        # required functions must be available
        for f in functions:
            provisions = self._find_function_by_name(f)
            if len(provisions) == 0:
                logging.error("Requirement <function name=\"%s\" /> cannot be satisfied." % f)

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
                for s in cspec.findall("./requires/service"):
                    tmp.add(Repository.ServiceIdentifier(s))
                required_services[cname]["specified"].update(tmp)

                tmp = set()
                for s in cspec.findall("./provides/service"):
                    tmp.add(Repository.ServiceIdentifier(s))
                provided_services[cname]["specified"].update(tmp)

            # additional requirements in composite spec
            for s in c.findall("./requires/service"):
                sname = Repository.ServiceIdentifier(s)
                required_services[cname]['specified'].add(sname)

            # references in <route> must be specified
            for s in c.findall("./route/service"):
                sname = Repository.ServiceIdentifier(s)
                required_services[cname]["used"].add(sname)

                if len(sname.match_all(required_services[cname]['specified'])) != 1:
                    logging.error("Routing of unknown/underspecified service requirement to '%s' found for component '%s' in composite '%s'." % (sname, cname, composite.get("name")))

                if s.find("child") != None:
                    chname = s.find("child").get("name")
                    if len(self._find_element_by_attribute("component", { "name" : chname }, pattern)) == 0:
                        logging.error("Routing of service '%s' to child '%s' of composite '%s' not possible." % (sname, chname, composite.get("name")))
                    else:
                        provided_services[chname]["used"].add(sname)

                external = s.find('external')
                if external != None:
                    required_services[cname]["external"].add(Repository.ServiceIdentifier(s, external.get('ref')))

            # references in <expose> must be specified
            for e in c.findall('expose'):
                for s in e.findall("service"):
                    sname = Repository.ServiceIdentifier(s, e.get('ref'))
                    provided_services[cname]["used"].add(sname)
                    provided_services[cname]["exposed"].add(sname)
                    if (sname.find_match(self, composite.find("provides"))) == 0:
                        logging.error("Exposed service '%s' does not match composite spec '%s'." % (sname, composite.get("name")))

        # required external service must be pending exactly once
        # or explicitly routed to external service
        for s in composite.findall("./requires/service"):
            sname = Repository.ServiceIdentifier(s)
            pending_count = 0
            for r in required_services.values():
                externalmatch = sname.match_all(r['external'])
                if len(externalmatch):
                    pending_count = len(externalmatch)
                    break

                pending_count += len(sname.match_all(r["specified"] - r["used"]))

            if pending_count != 1:
                print(r['external'])
                logging.error("Service '%s' required by composite '%s' cannot be identified in pattern." % (sname, composite.get("name")))

        # provided external service must be either exposed or pending exactly once
        for s in composite.find("provides").findall("service"):
            sname = self.ServiceIdentifier(s)
            exposed_count = 0
            pending_count = 0
            for p in provided_services.values():
                exposed_count += len(sname.match_all(p['exposed']))
                pending_count += len(sname.match_all(p['specified'] - p['used']))

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

class ChildQuery:
    def __init__(self, xml_node):
        self._root      = xml_node

        self._parse()

    def _parse(self):
        self._type = None

        for t in [ "function", "component" ]:
            if self._root.find(t) is not None:
                self._type = t
                self._identifier = self._root.get('name')
                self._queryname  = self._root.find(t).get('name')
                break

        assert(self._type is not None)

    def identifier(self):
        return self._identifier

    def label(self):
        if self._identifier is not None:
            return self._identifier
        else:
            return self._queryname

    def query(self):
        return self._queryname

    def type(self):
        return self._type

    def functions(self):
        if self.type() == 'function':
            return set([self.query()])

        return set()

    def components(self):
        if self.type() == 'component':
            return set([self.query()])

        return set()

    def dependencies(self, dtype='child'):
        assert dtype == 'child' or dtype == 'function'

        routes = list()

        dependency = self._root.find("dependency")
        if dependency is not None:
            for c in self._root.find("dependency").findall(dtype):
                attribs = { dtype : c.get("name") }
                routes.append(attribs)

        return routes


    def subsystem(self):
        return self._root.get('subsystem')

    def __repr__(self):
        return self.label()

    def __getstate__(self):
        return ( self._type,
                 self._identifier,
                 self._queryname )

    def __setstate__(self, state):
        self._type, self._identifier, self._queryname = state


class SystemParser:
    class NodeNotFoundError(Exception):
        pass

    def __init__(self, xml_file, xsd_file=None):
        XMLParser.__init__(self, xml_file, xsd_file)

        if self._file is not None:
            # find <system>
            if self._root.tag != "system":
                self._root = self._root.find("system")
                if self._root == None:
                    raise self.NodeNotFoundError("Cannot find <system> node.")

    def name(self):
        res = self._root.get('name')
        if res is None:
            res = ''

        return res

    def children(self):
        result = set()
        for c in self._root.findall('child'):
            result.add(ChildQuery(c))

        return result

class AggregateSystemParser:

    def __init__(self):
        self._parsers = list()

    def append(self, parser):
        self._parsers.append(parser)

    def name(self):
        names = list()
        for parser in self._parsers:
            names.append(parser.name())

        return '+'.join(names)

    def children(self):
        result = set()
        for parser in self._parsers:
            result.update(parser.children())

        return result

class PlatformParser:
    class PfComponent:
        def __init__(self, xml_node, parent=None):
            self._root = xml_node
            self._parent = parent
            self._state = dict()

        def _domain(self):
            domain = { self }
            if self._parent is not None:
                if hasattr(self._parent, '_domain'):
                    domain.update(self._parent._domain())
                else:
                    domain.add(self._parent)

            return domain

        def name(self):
            return self._root.get('name')

        def config(self):
            node = self._root.find('config')
            if node is not None:
                return node.get('name')

            return None

        def static(self):
            return self.config() is None

        def comms(self):
            names = set()
            for r in self._root.findall('requires/comm'):
                names.add(r.get('name'))

            return names

        def specs(self):
            names = set()
            for r in self._root.findall('provides/spec'):
                names.add(r.get('name'))

            return names

        def rte(self):
            r = self._root.find('provides/rte')
            if r is not None:
                return r.get('name')
            else:
                return 'native'

        def quantum(self, name):
            q = self._root.find('provides/%s' % name)
            if q is not None:
                return int(q.get('quantum'))
            else:
                return 0

        def set_state(self, name, value):
            self._state[name] = value

        def state(self, name):
            return self._state[name]

        def same_singleton_domain(self, rhs):
            return len(self._domain() & rhs._domain()) > 0

        def in_native_domain(self, rhs):
            return len(self._domain() & rhs._domain()) > 0

        def __repr__(self):
            return self.name()

        def __getstate__(self):
            return ( self.name() )

    class NodeNotFoundError(Exception):
        pass

    def __init__(self, xml_file, xsd_file=None):
        XMLParser.__init__(self, xml_file, xsd_file)

        if self._file is not None:
            # find <platform>
            if self._root.tag != "platform":
                self._root = self._root.find("platform")
                if self._root == None:
                    raise self.NodeNotFoundError("Cannot find <platform> node.")

        self._check()

    def _check(self):
        comms_avail = self.comm_names()
        for c in self.pf_components():
            for comm in c.comms():
                assert comm in comms_avail, "requirement <comm name=\"%s\"> not available" % comm

    def pf_components(self):
        result = set()
        for c in self._root.findall("component"):
            for s in c.findall("subsystem"):
                result.add(self.PfComponent(s, parent=c))

        return result

    def comm_names(self):
        names = set()

        for c in self._root.findall("comm"):
            names.add(c.get('name'))

        return names

