#!/usr/bin/env python

import xml.etree.ElementTree as ET

import logging
import argparse

parser = argparse.ArgumentParser(description='Check config model XML.')
parser.add_argument('file', metavar='xml_file', type=str, 
        help='XML file to be processed')

args = parser.parse_args()

################
# main section #
################

class SubsystemConfig:
    def __init__(self, root_node, parent):
        self._root = root_node
        self.parent = parent
        self.subsystems = dict()
        self.children = list()

    def parse(self):
        for sub in self._root.findall("subsystem"):
            name = sub.get("name")
            self.subsystems[name] = SubsystemConfig(sub, self)

        # TODO parse <child> nodes
        return

    def parent_services(self):
        return self.parent.services()

    def child_services(self):
        # TODO return child services
        return list()

    def services(self):
        return self.parent_services() + self.child_services()

    def add_function(self, name):
        self.parent.add_function(name)

class SystemConfig(SubsystemConfig):
    def __init__(self, root_node):
        self._root = root_node
        self.functions = set()
        self.subsystems = dict()
        self.children = list()
        self.specs = list()

    def parse(self):
        SubsystemConfig.parse(self)

        # TODO parse <specs>

    def parent_services(self):
        parent_services = set()

        if self._root.find("parent-provides"):
            for p in self._root.find("parent-provides").findall("service"):
                parent_services.add(p.get("name"))

        return parent_services

    def add_function(self, name):
        if name in self.functions:
            loggging.error("Function '%s' cannot be present multiple times." % name) 
        else:
            self.functions.add(name)

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
                                                              "function": { "required-attrs" : ["name"] },
                                                              "rte"     : { "required-attrs" : ["name"] },
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

        # find <config_model>
        if self._root.tag != "config_model":
            self._root = self._root.find("config_model")
            if self._root == None:
                raise "Cannot find <config_model> node."

    def _find_function_by_name(self, name):
        functions = list()
        # iterate components
        for c in self._root.findall("component"):
            p = c.find("provides")
            if p is not None:
                functions.update(self._find_element_by_attribute("function", { "name" : name }, root=p))

        # iterate composites
        for c in self._root.findall("composite"):
            p = c.find("provides")
            if p is not None:
                functions.update(self._find_element_by_attribute("function", { "name" : name }, root=p))

        return functions

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

        if component_node.find("provides"):
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

            required_services[cname] = { "specified" : set(), "used" : set() }
            provided_services[cname] = { "specified" : set(), "used" : set(), "exposed" : set() }

            # referenced components must be specified 
            cspecs = self._find_element_by_attribute("component", { "name" : cname })
            if len(cspecs) == 0:
                logging.error("Pattern of composite '%s' references unspecified component '%s'." %
                        (composite.get("name"), cname))

            # store specified service requirements/provisions
            for cspec in cspecs:
                tmp = set()
                if cspec.find("requires"):
                    for s in cspec.find("requires").findall("service"):
                        tmp.add(s.get("name"))
                required_services[cname]["specified"].update(tmp)

                tmp = set()
                if cspec.find("provides"):
                    for s in cspec.find("provides").findall("service"):
                        tmp.add(s.get("name"))
                provided_services[cname]["specified"].update(tmp)

            # references in <route> must be specified
            if c.find("route"):
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

            # references in <expose> must be specified
            if c.find("expose"):
                for s in c.find("expose").findall("service"):
                    sname = s.get("name")
                    provided_services[cname]["used"].add(sname)
                    provided_services[cname]["exposed"].add(sname)
                    if len(self._find_element_by_attribute("service", { "name" : sname }, composite.find("provides"))) == 0:
                        loggin.error("Exposed service '%s' does not match composite spec '%s'." % (sname, composite.get("name")))

        # required external service must be pending exactly once
        for s in composite.find("requires").findall("service"):
            sname = s.get("name")
            pending_count = 0
            for r in required_services.values():
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

    def check_system(self):
        # TODO check function/composite/component references in system and subsystems

        # preprocessing:
        # - on each level, build set of parent and child service provisions
        # - build set of function provisions
        # dependency resolution:
        # 1) check rte dependencies
        # 2) check function dependencies
        # 3) check service dependencies
        #    - use mux to solve cardinality problems
        #    - use protocol to solve compatibility problems
        #    - use proxy to solve reachability
        # warn if multiple candidates exist and dependencies are not decidable

        system = SystemConfig(self._root.find("system"))
        system.parse()

        return

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
