import xml.etree.ElementTree as ET

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

    def services_routed_to_function(self, composite, functionname):
        result = set()
        for c in self.patterns[composite]['chosen'].findall('component'):
            if c.find('route') is not None:
                for s in c.find('route').findall('service'):
                    slabel = None
                    if 'label' in s.keys():
                        slabel = s.get('label')

                    f = s.find('function')
                    if f is not None:
                        if functionname is None or f.get('name') == functionname:
                            result.add((s.get('name'), slabel))

        return result

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
                            if functionname is not None:
                                if s.find('function') is not None and s.find('function').get('name') == functionname:
                                    result.add((self._get_component_from_repo(c), slabel))
                            else:
                                if s.find('service') is not None or s.find('function') is not None:
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


class ConfigModelParser:

    def __init__(self, config_model_file):
        self._file = config_model_file
        if self._file is not None:
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
                                                              "function": { "required-attrs" : ["name"] },
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
                                                                            "optional-attrs" : ["max_clients", "filter"], },
                                                              "function": { "required-attrs" : ["name"] }, } },
                                "requires" : { "children" : { "service" : { "required-attrs" : ["name"],
                                                                            "optional-attrs" : ["label", "filter"] },
                                                              "function": { "required-attrs" : ["name"] } } },
                                "proxy"    : { "required-attrs" : ["carrier"] },
                                "filter"   : { "max" : 1, "optional-attrs" : ["alias"], "children" : {
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
                                                "function" : { "required-attrs" : ["name"] },
                                                "service"  : { },
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
                                            "function" : { "required-attrs" : ["name"] },
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

        if self._file is not None:
            # find <config_model>
            if self._root.tag != "config_model":
                self._root = self._root.find("config_model")
                if self._root == None:
                    raise Exception("Cannot find <config_model> node.")

    def _find_function_by_name(self, name):
        function_providers = list()
        # iterate components
        for c in self._root.findall("component"):
            p = c.find("provides")
            if p is not None:
                for f in self._find_element_by_attribute("function", { "name" : name }, root=p):
                    function_providers.append(c)

        # iterate composites
        for c in self._root.findall("composite"):
            p = c.find("provides")
            if p is not None:
                for f in self._find_element_by_attribute("function", { "name" : name }, root=p):
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

            # referenced filter must be defined
            if "filter" in p.keys():
                if len(self._find_element_by_attribute("filter", { "alias" : p.get("filter") }, component)) == 0:
                    logging.error("Provision <service name=\"%s\" filter=\"%s\" /> refers to unknown alias." %
                        (p.get("name"), p.get("filter")))


    def _check_requirements(self, component):
        if component.find("requires") is None:
            return

        services = set()
        for r in component.find("requires").findall("service"):
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

            # referenced filter must be defined
            if "filter" in r.keys():
                if len(self._find_element_by_attribute("filter", { "alias" : r.get("filter") }, component)) == 0:
                    logging.error("Requirement <service name=\"%s\" filter=\"%s\" /> refers to unknown alias." %
                        (r.get("name"), r.get("filter")))

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

                    if s.find("function") != None:
                        fname = s.find("function").get("name")
                        if len(self._find_element_by_attribute("function", { "name" : fname }, composite.find("requires"))) == 0:
                            logging.error("Routing of service '%s' to function '%s' does not match composite spec '%s'." % (sname, fname, composite.get("name")))

                    if s.find("child") != None:
                        chname = s.find("child").get("name")
                        if len(self._find_element_by_attribute("component", { "name" : chname }, pattern)) == 0:
                            logging.error("Routing of service '%s' to child '%s' of composite '%s' not possible." % (sname, chname, composite.get("name")))
                        else:
                            provided_services[chname]["used"].add(sname)

                    if s.find("service") != None:
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

class SubsystemConfig:
    def __init__(self, root_node, parent, model):
        self.root = root_node
        self.parent = parent
        self.model = model
        self.rte = None

    def parse(self):
        # add subsystem to graph
        self.model().add_subsystem(self, self.parent)

        for sub in self.root.findall("subsystem"):
            name = sub.get("name")
            subsystem = SubsystemConfig(sub, self, self.model)
            subsystem.parse()

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
        return self.parent.system_specs()

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
        self.system_model = model

    def model(self):
        return self.system_model

    def parse(self):
        # recursively parse subsystem config
        SubsystemConfig.parse(self)

        # parse <specs>
        for s in self.root.findall("spec"):
            self.specs.add(s.get("name"))

        # parse routes
        self.parse_routes()

    def parse_routes(self):
        # parse routes between children
        fa = self.model().by_name['func_arch']
        for child in fa.nodes():
            if child.find("route") is not None:
                for s in child.find("route").findall("service"):
                    if s.find("child") is not None:
                        for target in fa.nodes():
                            if target.get("name") == s.find("child").get("name"):
                                # we check later whether the target component actually provides this service
                                edge = fa.add_edge(child, target, {'service' : s.get("name")})
                                if 'label' in s.keys():
                                    fa.edge[child][target]['label'] = s.get('label')
                                break
                    elif s.find("function") is not None:
                        fname = s.find('function').get('name')
                        for target in fa.nodes():
                            if fname in self.provisions(target, 'function'):
                                edge = fa.add_edge(child, target, {'service' : s.get('name'), 'function' : fname })
                                if 'label' in s.keys():
                                    fa.edge[child][target]['label'] = s.get('label')
                    else:
                        raise Exception("ERROR")
        return


    def select_rte(self):
        result = SubsystemConfig.select_rte(self)

        if result:
            if self.rte.find('provides').find('rte').get('name') != "native":
                logging.error("Top-level RTE must be 'native' (found: %s)." % (self.rte.find('provides').find('rte').get('name')))

        return result

    def _check_explicit_routes(self, component, child):
        # check provisions for each incoming edge
        provides = self.model().by_name['func_arch'].in_edges(child)
        requires = self.model().by_name['func_arch'].out_edges(child)
        for p in provides:
            if 'function' in p:
                found = False
                if component.find('provides') is not None:
                    if len(self.model().repo._find_element_by_attribute('function', { 'name' : p['function'] }, component.find('provides'))):
                        found = True

                if not found:
                    logging.info("Child component '%s' does not provide function '%s'." % (component.get('name'), p['function']))
                    return False

            else: # service
                found = False
                if component.find('provides') is not None:
                    if len(self.model().repo._find_element_by_attribute('service', { 'name' : p['service'] }, component.find('provides'))):
                        found = True
                if not found:
                    logging.info("Child component '%s' does not provide service '%s'." % (component.get('name'), p['service']))
                    return False

        # check requirements for each outgoing edge
        for r in requires:
            found = False
            if component.find('requires') is not None:
                if len(self.model().repo._find_element_by_attribute('service', { 'name' : r['service'] }, component.find('requires'))):
                    found = True
            if not found:
                logging.info("Child component '%s' does not require routed service '%s'." % (component.get('name'), r['service']))
                return False

        return True

    def connect_functions(self):
        # choose compatible components based on explicit routes
        for c in self.model().children(None):
            if not self.model().repo.find_compatible_component(c, self._check_explicit_routes, check_pattern=False):
                logging.critical("Failed to satisfy explicit routes for child '%s'." % c.attrib)
                return False

        if not self.model().connect_functions():
            return False

        # solve reachability
        if not self.model().insert_proxies():
            logging.critical("Cannot insert proxies.")
            return False

        # connect function requirements of proxies
        if not self.model().connect_functions():
            return False

        return True

    def solve_dependencies(self):

        self.model().build_component_graph()

        # check/expand explicit routes (uses protocol to solve compatibility problems)
        if not self.model().solve_routes():
            return False

        # solve pending requirements
        # warn if multiple candidates exist and dependencies are not decidable
        if not self.model().solve_pending():
            return False

        if not self.model().insert_muxers():
            return False

        # (heuristically) map unmapped components to lowest subsystem
        if not self.model().map_unmapped_components():
            return False

        # merge non-singleton components
        self.model().merge_components(singleton=False)

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
        return self.model().functions
