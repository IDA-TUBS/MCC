"""
Description
-----------

Implements XML parser classes for the component repository.

:Authors:
    - Johannes Schlatow

"""
from lxml import objectify
from lxml import etree as ET
from lxml.etree import XMLSyntaxError
import logging

from mcc.graph import GraphObj, Edge

class XMLParser:
    def __init__(self, xml_file, xsd_file):
        self._file = xml_file
        if self._file is not None:
            schema = ET.XMLSchema(file=xsd_file)
            parser = ET.XMLParser(schema=schema)

            self._tree = ET.parse(self._file, parser=parser)
            self._root = self._tree.getroot()

        self._structure = dict()

class Repository(XMLParser):

    class Component:
        def __init__(self, xml_node, repo):
            self.repo = repo
            self.xml_node = xml_node

        def uid(self):
            return self.xml_node

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

        def requires_services(self):
            services = list()
            for s in self.xml_node.findall("./requires/service"):
                services.append(s.get("name"))

            return services

        def provides_services(self):
            services = list()
            for s in self.xml_node.findall("./provides/service"):
                services.append(s.get("name"))

            return services

        def function(self):
            if self.xml_node.find('function') is not None:
                return self.xml_node.find('function').get('name')

            return None

        def service_for_function(self, function):
            for s in self.xml_node.findall("./requires/service[@function]"):
                if s.get('function') == function:
                    return s.get('name')

        def label(self):
            name = self.xml_node.get('name')
            if name is not None:
                return name
            else:
                return 'anonymous'

        def patterns(self):
            result = set()
            if self.xml_node.tag == 'composite':
                for pat in self.xml_node.findall("./pattern"):
                    result.add(Repository.ComponentPattern(self, pat))
            else:
                result.add(self)

            return result

        def providing_component(self, service):
            assert(service in self.provides_services())
            return self

        def requiring_components(self, service, function=None):
            assert(service in self.requires_services())
            return set([self])

        def flatten(self):
            # for composites, we must select a pattern first
            assert(self.xml_node.tag != 'composite')

            return set([self])
        
        def __repr__(self):
            return self.label()

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

        def providing_component(self, service):
            for c in self.xml_node.findall("component"):
                for s in c.findall('./expose/service'):
                    if s.get('name') == service:
                        component = self.repo.find_components_by_type(c.get('name'), querytype='component')
                        # FIXME we might have multiple options here
                        return component[0]

            logging.error("Service '%s' is not exposed." % service)
            return None

        def requiring_components(self, service, function=None):
            result = set()
            for c in self.xml_node.findall("component"):
                for s in c.findall('./route/service'):
                    if s.get('name') == service and s.find('external') is not None:
                        if s.find('external').get('function') is None or function is None or s.find('external').get('function') == function:
                            components = self.repo.find_components_by_type(c.get('name'), querytype='component')
                            result.update(components)

            if len(result) == 0:
                logging.error("Service '%s' is not required by component pattern for '%s'." % (service, self.component.label()))
            return result

        def flatten(self):
            # fill set with atomic components and their edges as specified in the pattern
            flattened = set()

            child_lookup = dict()
            name_lookup = dict()
            # first, add all components and create lookup table by child name
            for c in self.xml_node.findall("component"):
                components = self.repo.find_components_by_type(c.get('name'), querytype='component')
                name_lookup[c.get('name')] = components[0]
                child_lookup[c] = components[0]
                # FIXME, we might have multiple options here
                flattened.add(GraphObj(components[0]))

            # second, add connections
            for c in self.xml_node.findall("component"):
                for s in c.findall('./route/service'):
                    if s.find('child') is not None:
                        name = s.find('child').get('name')
                        if name not in name_lookup:
                            logging.critical("Cannot satisfy internal route to child '%s' of pattern." % name)
                        else:
                            params = { 'label' : s.get('label'), 'service' : s.get('name') }
                            flattened.add(GraphObj(Edge(child_lookup[c], name_lookup[name]), params))

            return flattened

    def __init__(self, config_model_file, xsd_file):
        XMLParser.__init__(self, config_model_file, xsd_file)

        if self._file is not None:
            # find <repository>
            if self._root.tag != "repository":
                self._root = self._root.find("repository")
                if self._root == None:
                    raise Exception("Cannot find <repository> node.")

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
            raise NotImplementedError()
        elif querytype == 'proto':
            components = self.find_protocolstacks(query=query)
        else: # 'component' or 'composite'
            components = self._find_element_by_attribute('component', { "name" : query }) + \
                         self._find_element_by_attribute('composite', { "name" : query })

        return [Repository.Component(c, self) for c in components]

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
        functions = set()
        for r in component.findall("./requires/service"):
            # service required twice must be distinguished by label
            if r.get("name") in services:
                labels = set()
                if "label" not in r.keys():
                    logging.error("Requirement <service name=\"%s\" /> is ambiguous and must therefore specify a label." %(r.get("name")))
                elif r.get("label") in labels:
                    logging.error("Requirement <service name=\"%s\" label=\"%s\" /> is ambiguous" % (r.get("name"), r.get("label")))
                else:
                    labels.add(r.get("label"))
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
                    tmp.add(s.get("name"))
                required_services[cname]["specified"].update(tmp)

                tmp = set()
                for s in cspec.findall("./provides/service"):
                    tmp.add(s.get("name"))
                provided_services[cname]["specified"].update(tmp)

            # additional requirements in composite spec
            for s in c.findall("./requires/service"):
                sname = s.get('name')
                required_services[cname]['specified'].add(sname)

            # references in <route> must be specified
            for s in c.findall("./route/service"):
                sname = s.get("name")
                required_services[cname]["used"].add(sname)

                if sname not in required_services[cname]['specified']:
                    logging.error("Routing of unknown service requirement to '%s' found for component '%s' in composite '%s'." % (sname, cname, composite.get("name")))

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
                        loggin.error("Exposed service '%s' does not match composite spec '%s'." % (sname, composite.get("name")))

        # required external service must be pending exactly once
        # or explicitly routed to external service
        for s in composite.findall("./requires/service"):
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

    def structure_to_markdown(self, filename, structure=None, level=0, mdfile=None, path=None):
        if structure is None:
            structure = self._structure

        header = ['---',
                    'title: Title',
                    'author:',
                    '- name: Johannes Schlatow',
                    '  affiliation: TU Braunschweig, IDA',
                    '  email: schlatow@ida.ing.tu-bs.de',
                    'date: \\today',
                    'abstract: Lorem ipsum.',
                    'lang: english',
                    'papersize: a4paper',
                    'numbersections: 1',
                    'draft: 1',
                    'todomargin: 3cm',
                    'packages:',
                    '- tubscolors',
                    '- array',
                    '- booktabs',
                    '- hyperref',
                    'sfdefault: 1',
                    'fancyhdr: 1',
                    'compiletex: 0',
                    'scalefigures: 1',
                    'table_caption_above: 0',
                    'floatpos: ht',
                    'versiontag: draft -- \\today',
                    '...',
                    '---']

        if level == 0:

            with open(filename, 'w') as mdfile:
                for l in header:
                    mdfile.write(l + '\n')

                self.structure_to_markdown(filename, structure, level=1, mdfile=mdfile)

        else:

            if path is None:
                path = list()

            # iterate children
            for node in structure.keys():
                if 'leaf' in structure[node] and structure[node]['leaf'] is False:
                    continue
                if 'recursive-children' in structure[node] and structure[node]['recursive-children'] is True:
                    continue

                mdfile.write('\clearpage\n\n')
                for i in range(level):
                    mdfile.write('#')
                mdfile.write(' \<%s\> {#sec:%d-%s}\n' % (node, level, node))

                # print path
                mdfile.write('Hierarchy: \n')
                mdfile.write('```\n')
                indent = ''
                for n in path + [node]:
                    mdfile.write('%s<%s>\n' % (indent, n))
                    indent += '  '
                mdfile.write('```\n')

                # TODO lookup elements from example file and add comments/annotations

                # print attribute table
                mdfile.write('\n| attribute | use | type |\n')
                mdfile.write(  '|-----------|-----|------|\n')
                if 'required-attrs' in structure[node]:
                    for attr in structure[node]['required-attrs']:
                        typename = 'string' # FIXME
                        mdfile.write('| %s | required | %s |\n' % (attr, typename))

                if 'optional-attrs' in structure[node]:
                    for attr in structure[node]['optional-attrs']:
                        typename = 'string' # FIXME
                        mdfile.write('| %s | optional | %s |\n' % (attr, typename))

                mdfile.write(  ': Table of attributes\n\n')

                # print children table
                if 'children' in structure[node]:
                    mdfile.write('\n| name | use | max | type |\n')
                    mdfile.write(  '|------|-----|-----|------|\n')
                    for name, spec in structure[node]['children'].items():
                        if 'leaf' in spec and spec['leaf'] is False:
                            typename = 'any'
                        elif 'recursive-children' in spec and spec['recursive-children'] is True:
                            typename = '[@sec:%d-%s]' % (level, node)
                        else:
                            typename = '[@sec:%d-%s]' % (level+1, name)

                        if 'max' in spec:
                            max_occur = str(spec['max'])
                        else:
                            max_occur = "-"

                        use = 'optional'
                        if 'min' in spec:
                            if spec['min'] > 0:
                                use = 'required'
                        
                        mdfile.write('| %s | %s | %s | %s |\n' % (name, use, max_occur, typename))

                    mdfile.write(  ': Table of children\n\n')

                    self.structure_to_markdown(filename, structure[node]['children'], level=level+1, mdfile=mdfile, path=path+[node])

class Subsystem:

    class Child(object):
        def __init__(self, xml_node, subsystem):
            self._root      = xml_node
            self._subsystem = subsystem

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

        def subsystem(self):
            return self._subsystem

        def platform_component(self):
            return self._subsystem

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

        def routes(self):
            # FIXME remove if we do not require explicit routing anymore
            routes = list()
            route = self._root.find("route")
            if route is not None:
                for s in self._root.find("route").findall("service"):
                    attribs = { "service" : s.get("name") }
                    if s.find("child") is not None:
                        # collect attributes
                        attribs['child'] = s.find("child").get("name")
                        if 'label' in s.keys():
                            attribs['label'] = s.get('label')

                    else:
                        raise Exception("ERROR")

                    routes.append(attribs)

            dependency = self._root.find("dependency")
            if dependency is not None:
                for c in self._root.find("dependency").findall("child"):
                    attribs = { "child" : c.get("name") }
                    routes.append(attribs)

            return routes

        def __repr__(self):
            return self.label()

    def __init__(self, xml_node, parent=None):
        self._root   = xml_node
        self._parent = parent
        self._subsystems = set()
        self._children = set()

        self._parse()

    def _parse(self):
        for sub in self._root.findall("subsystem"):
            self._subsystems.add(Subsystem(sub, parent=self))

        for child in self._root.findall("child"):
            self._children.add(Subsystem.Child(child, subsystem=self))

    def specs(self):
        specs = set()
        if self._parent is not None:
            specs = self._parent.specs()
            
        # parse <specs>
        if self._root.find("provides") is not None:
            for s in self._root.find("provides").findall("spec"):
                specs.add(s.get("name"))

        return specs

    def rte(self):
        # parse <rte>
        node = self._root.find("./provides/rte")
        if node is not None:
            return node.get("name")

        return "native"

    def subsystems(self):
        return self._subsystems

    def parent(self):
        return self._parent

    def children(self):
        return self._children

    def name(self, default=None):
        if 'name' in self._root.keys():
            return self._root.get('name')

        return default


class SubsystemParser:
    def __init__(self, xml_file, xsd_file):
 
        XMLParser.__init__(self, xml_file, xsd_file)

        if self._file is not None:
            # find <system>
            if self._root.tag != "system":
                self._root = self._root.find("system")
                if self._root == None:
                    raise Exception("Cannot find <system> node.")

    def root(self):
        return Subsystem(self._root)
