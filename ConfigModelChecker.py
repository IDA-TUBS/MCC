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

class SystemConfig:
    def __init__(self):
        self.childs

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
                                "filter"   : { "optional-attrs" : ["alias"], "children" : {
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
                                "filter"   : { "optional-attrs" : ["alias"], "children" : {
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

    # check whether all function names are only provided once
    def check_functions_unambiguous(self):
        # set of known function names
        functionnames = set()

        # iterate all provisions and function names
        for p in self._root.iter("provides"):
            for f in p.findall("function"):
                if f.get("name") in functionnames:
                    logging.warn("Function '%s' is not unambiguous." % f.get("name"))
                else:
                    functionnames.add(f.get("name"))

    # check whether all component names are only defined once
    def check_components_unambiguous(self):
        # set of known component names
        names = set()
        versioned_names = set()

        # iterate atomic components
        for c in self._root.findall("component"):
            if c.get("name") in names:
                if c.get("name") not in versioned_names:
                    logging.warn("Component '%s' is not unambiguous." % c.get("name"))
            else:
                names.add(c.get("name"))
                if "version" in c.keys():
                    versioned_names.add(c.get("name"))

    # check whether components are unambiguously classified as function, filter, mux, proxy, protocol or None
    def check_classification_unambiguous(self):
        for c in self._root.findall("component"):
            classes = self._get_component_classes(c)
            if len(classes) > 1:
                logging.error("Component '%s' is ambiguously classified as: %s" % (c.get("name"), classes))

        for c in self._root.findall("composite"):
            classes = self._get_component_classes(c)
            if len(classes) > 1:
                logging.error("Composite '%s' is ambiguously classified as: %s" % (c.get("name"), classes))

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
            # TODO

            # referenced filter must be defined
            if "filter" in r.keys():
                if len(self._find_element_by_attribute("filter", { "alias" : r.get("filter") }, component)) == 0:
                    logging.error("Requirement <service name=\"%s\" filter=\"%s\" /> refers to unknown alias." %
                        (r.get("name"), r.get("filter")))

        # TODO required services must be available

        # TODO required functions must be available

        # TODO required rte must be available

    # perform model check for <component> nodes: 
    def check_atomic_components(self):
        for c in self._root.findall("component"):
            self._check_provisions(c)
            self._check_requirements(c)

            # TODO check proxy/protocol/mux/filter

    # perform model check for <composite> nodes: 
    def check_composite_components(self):
        for c in self._root.findall("composite"):
            self._check_provisions(c)
            self._check_requirements(c)

            # TODO check proxy/protocol/mux/filter

    def check_system(self):
        # TODO check function/composite/component references in system and subsystems
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

    parser = ConfigModelParser(args.file)

    parser.check_structure()
    parser.check_functions_unambiguous()
    parser.check_components_unambiguous()
    parser.check_classification_unambiguous()
    parser.check_binaries()
    parser.check_atomic_components()
    parser.check_composite_components()
    parser.check_system()
