"""
Description
-----------

Implements configurators that create (sub)system configurations from a model.

:Authors:
    - Johannes Schlatow

"""

import logging
from mcc.framework import *

try:
    from lxml import objectify
    from lxml import etree as ET
    from lxml.etree import XMLSyntaxError

except ImportError:
    from xml.etree import ElementTree as ET

class GenodeConfigurator:
    """ Converts component instantiation layer into a Genode <config> xml.
    """
    class SessionLabel:
        def __init__(self, label=None, prefix=None, suffix=None):
            self.label  = label
            self.prefix = prefix
            self.suffix = suffix

        def empty(self):
            return self.label is None and self.prefix is None and self.suffix is None

        def exact(self):
            return self.label is not None

        def prefix_length(self):
            return len(self.prefix) if self.prefix is not None else 0

        def suffix_length(self):
            return len(self.suffix) if self.suffix is not None else 0

        def __lt__(self, rhs):
            # empty is more generic, rhs comes first
            if self.empty():
                return False

            # empty is more generic, we come first
            if rhs.empty():
                return True

            # exact match, we come first
            if self.exact():
                return True

            # exact match, rhs comes first
            if rhs.exact():
                return False

            # longer prefix/suffix is more specific and takes precedence
            return self.prefix_length() + self.suffix_length() > rhs.prefix_length() + self.suffix_length()

    class Route:
        def __init__(self, server=None, service=None, from_label=None, to_label=None):
            self.server     = server
            self.service    = service

            if from_label is None or not isinstance(from_label, SessionLabel):
                self.from_label = GenodeConfigurator.SessionLabel(label=from_label)
            else:
                self.from_label = from_label

            if to_label is None or not isinstance(to_label, SessionLabel):
                self.to_label = GenodeConfigurator.SessionLabel(label=to_label)
            else:
                self.to_label = to_label

        def any_child(self):
            return self.server is None

        def parent(self):
            return self.server == 'parent'

        def any_service(self):
            return self.service is None

        def __lt__(self, rhs):
            # for sorting: specific rules take precedence over generic rules

            # we are generic, rhs comes first
            if self.any_service():
                return False

            # rhs is generic, we come first
            if rhs.any_service():
                return True

            # we are generic, rhs comes first:
            if self.any_child():
                return False

            # rhs is generic, we come first
            if rhs.any_child():
                return True

            # sort services by name
            if self.service != rhs.service:
                return self.service < rhs.service

            # for equal services, sort by labels
            if self.from_label != rhs.from_label:
                return self.from_label < rhs.from_label

            # for same labels, 'parent' comes last
            if self.parent():
                return False

            if rhs.parent():
                return True

            return self.server < rhs.server

        def __le__(self, rhs):
            return self.__lt__(rhs)

        def __ge__(self):
            return not self.__lt__(rhs)

        def __gt__(self):
            return not self.__le__(rhs)

    class StartNode:

        def __init__(self, name, component):
            self.name      = name
            self.component = component
            self.routes    = list()

        def _append_default_routes(self):
            # must be sorted before
            self.routes.append(GenodeConfigurator.Route(server='parent')) # route any-service to parent
            self.routes.append(GenodeConfigurator.Route())                # route any-service to any-child

        def _sort_routes(self):
            self.routes = sorted(self.routes)

        def add_route(self, route):
            self.routes.append(route)

        def _provides_xml(self, startnode):
            seen = set()
            services = self.component.provides_services()
            if len(services) == 0:
                return

            provides = ET.SubElement(startnode, 'provides')
            for s in services:
                if s.name() in seen:
                    continue
                ET.SubElement(provides, 'service', name=s.name())

        def _routes_xml(self, startnode):
            if len(self.routes) == 0:
                return

            route = ET.SubElement(startnode, 'route')

            curserv = None
            for r in self.routes:
                if curserv is None or curserv.get('name') != r.service \
                  or curserv.get('label') != r.from_label.label \
                  or curserv.get('label_prefix') != r.from_label.prefix \
                  or curserv.get('label_suffix') != r.from_label.suffix:

                    if r.any_service():
                        curserv = ET.SubElement(route, 'any-service')
                    else:
                        curserv = ET.SubElement(route, 'service',
                                                name=r.service)

                        if not r.from_label.empty():
                            curserv.set('label', r.from_label.label)
                            curserv.set('label-prefix', r.from_label.prefix)
                            curserv.set('label-suffix', r.from_label.suffix)

                # target
                if r.parent():
                    ET.SubElement(curserv, 'parent')
                elif r.any_child():
                    ET.SubElement(curserv, 'any-child')
                else:
                    child = ET.SubElement(curserv, 'child',
                                          name=r.server)

                    if not r.to_label.empty():
                        child.set('label', r.to_label.label)
                        child.set('label-prefix', r.to_label.prefix)
                        child.set('label-suffix', r.to_label.suffix)

        def generate_xml(self, root, default_caps):
            start  = ET.SubElement(root,  'start',
                                   name=self.name)
            caps = self.component.requires_quantum('caps')
            if caps != default_caps:
                start.set('caps', str(caps))

            binary = ET.SubElement(start, 'binary',
                                   name=self.component.binary_name())

            ram = ET.SubElement(start, 'resource',
                                name='RAM',
                                quantum='%dM'%self.component.requires_quantum('ram'))

            # generate <provides>
            self._provides_xml(start)

            # generate <route>
            self._sort_routes()
            self._append_default_routes()
            self._routes_xml(start)

            # generate <config>
            # TODO generate per-component <config> via ConfigGenerator
            ET.SubElement(start, 'config')

    class ConfigXML:

        def __init__(self, filename, subsystem, xsd_file=None):
            self.filename  = filename
            self.subsystem = subsystem
            self.xsd_file  = xsd_file
            self.start_nodes = dict()

            self.parent_services = { "CAP", "LOG", "RM", "SIGNAL", "IO_MEM",
                                     "IRQ", "ROM", "RAM", "IO_PORT", "PD", "CPU"}

            self.default_caps = 300

        def _check_schema(self, root):
            if self.xsd_file is not None:
                raise NotImplementedError()

        def create_start_node(self, name, component):
            assert name not in self.start_nodes
            self.start_nodes[name] = GenodeConfigurator.StartNode(name, component)

            return self.start_nodes[name]

        def start_node(self, name):
            return self.start_nodes[name]

        def _write_header(self, root):
            # generate <parent-provides>
            provides = ET.SubElement(root, 'parent-provides')
            for s in self.parent_services:
                ET.SubElement(provides, 'service', name=s)

            # generate <default-routes>
            routes    = ET.SubElement(root, 'default-routes')
            any_serv  = ET.SubElement(routes, 'any-service')
            parent    = ET.SubElement(any_serv, 'parent')
            any_child = ET.SubElement(any_serv, 'any-child')

            # generate <default caps='x'>
            caps = ET.SubElement(root, 'default',
                                 caps=str(self.default_caps))

        def _write_footer(self, root):
            # nothing to be done here
            return

        def write_xml(self):
            root = ET.Element('config')

            self._write_header(root)
            for node in self.start_nodes.values():
                node.generate_xml(root, self.default_caps)
            self._write_footer(root)

            tree = ET.ElementTree(root)
            tree.write(self.filename, pretty_print=True)

            self._check_schema(root)


    def __init__(self, outpath, platform_model):
        self.outpath  = outpath
        self.platform = platform_model
        self.configs  = dict()

        self._prepare_files()

    def _prepare_files(self):
        # create ConfigXML for each non-static subsystem
        for pfc in self.platform.platform_graph.nodes():
            config = pfc.config()
            if config is not None:
                self.configs[pfc] = self.ConfigXML(self.outpath+config, pfc)

    def create_configs(self, layer):
        for inst in layer.graph.nodes():
            pfc = layer._get_param_value('mapping', inst)
            if pfc in self.configs:
                node = self.configs[pfc].create_start_node(inst.identifier, inst.component)

                # add routes
                for e in layer.graph.out_edges(inst):
                    source_service = layer._get_param_value('source-service', e)
                    target_service = layer._get_param_value('target-service', e)
                    node.add_route(self.Route(server=e.target.identifier,
                                              service=source_service.name(),
                                              from_label=source_service.label(),
                                              to_label=target_service.label()))

        for cfg in self.configs.values():
            cfg.write_xml()
