"""
Description
-----------

Implements configurators that create (sub)system configurations from a model.

:Authors:
    - Johannes Schlatow

"""

import logging
from mcc.framework import *
from mcc.model import Proxy
from mcc.model import NetworkManager

try:
    from lxml import objectify
    from lxml import etree as ET
    from lxml.etree import XMLSyntaxError

except ImportError:
    from xml.etree import ElementTree as ET

class EmptyConfigGenerator():
    def xml(self, root):
        return

    def adapt_routes(self):
        return

class DefaultConfigGenerator():
    def __init__(self, xml_node, config_override=None):
        self.xml_node        = xml_node
        self.config_override = config_override

    def xml(self, root):
        if self.config_override is not None:
            root.append(ET.fromstring(ET.tostring(self.config_override)))

        if self.xml_node is None:
            return

        for sub in self.xml_node.findall('./'):
            if sub.tag == 'config' and self.config_override is not None:
                continue
            else:
                root.append(ET.fromstring(ET.tostring(sub)))

    def adapt_routes(self):
        return

class DynamicConfigGenerator():
    def __init__(self, name, start_node):
        self.name = name
        self.start_node = start_node

        self.supported = { 'remote_rom_server' : { 'config' : self._rom_server_xml,
                                                   'route'  : self._rom_server_route },
                           'remote_rom_client' : { 'config' : self._rom_client_xml,
                                                   'route'  : lambda: None },
                           'report_rom'        : { 'config' : self._report_rom_xml,
                                                   'route'  : lambda: None }}

        platform = self.start_node.parent.platform
        if not hasattr(platform, 'nm'):
            platform.nm = NetworkManager([192, 168, 0, 0], 24)

        self.network_manager = platform.nm

        if name not in self.supported:
            raise NotImplementedError()

    def _remote_rom_ips_uid(self, remotename):
        ips = self.network_manager.lookup_or_allocate(remotename, 2)
        remote_uid = '%s-%d-%d' % (remotename, ips[0][3], ips[1][3])

        return ips, remote_uid

    def _rom_server_xml(self, root):
        model = self.start_node.model
        layer = self.start_node.layer
        obj   = self.start_node.layer_obj

        parents, parent_layer = model.find_parents(obj, layer, parent_type=Proxy)
        config = ET.SubElement(root, 'config')
        for p in parents:
            remotename = parent_layer._get_param_value('remotename', p)
            ips, remote_uid = self._remote_rom_ips_uid(remotename)

            src_ip = ips[0]
            dst_ip = ips[1]

            ET.SubElement(config, 'remote_rom',
                          name=remote_uid,
                          src='%d.%d.%d.%d' % (src_ip[0], src_ip[1], src_ip[2], src_ip[3]),
                          dst='%d.%d.%d.%d' % (dst_ip[0], dst_ip[1], dst_ip[2], dst_ip[3]),
                          binary='True')

    def _rom_client_xml(self, root):
        model = self.start_node.model
        layer = self.start_node.layer
        obj   = self.start_node.layer_obj

        parents, parent_layer = model.find_parents(obj, layer, parent_type=Proxy)
        config = ET.SubElement(root, 'config')
        for p in parents:
            remotename = parent_layer._get_param_value('remotename', p)
            ips, remote_uid = self._remote_rom_ips_uid(remotename)

            src_ip = ips[1]
            dst_ip = ips[0]

            ET.SubElement(config, 'remote_rom',
                          name=remote_uid,
                          src='%d.%d.%d.%d' % (src_ip[0], src_ip[1], src_ip[2], src_ip[3]),
                          dst='%d.%d.%d.%d' % (dst_ip[0], dst_ip[1], dst_ip[2], dst_ip[3]))

    def _report_rom_xml(self, root):
        raise NotImplementedError()

    def xml(self, root):
        self.supported[self.name]['config'](root)

    def _rom_server_route(self):
        model = self.start_node.model
        layer = self.start_node.layer
        obj   = self.start_node.layer_obj

        parents, parent_layer = model.find_parents(obj, layer, parent_type=Proxy)
        for p in parents:
            remotename = parent_layer._get_param_value('remotename', p)
            ips, remote_uid = self._remote_rom_ips_uid(remotename)

            # find ROM service without label and correct child
            found = False
            for r in self.start_node.routes:
                if not found and r.service == 'ROM' and r.from_label.empty():
                    # only if routed to correct child
                    for e in layer.graph.out_edges(obj):
                        if not found and e.target.identifier == r.server:
                            r.from_label.label = remote_uid
                            found = True

            assert found, 'Remote ROM label rewrite failed %s, %s' % (remotename, remote_uid)

    def adapt_routes(self):
        self.supported[self.name]['route']()


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

            if from_label is None or not isinstance(from_label, GenodeConfigurator.SessionLabel):
                self.from_label = GenodeConfigurator.SessionLabel(label=from_label)
            else:
                self.from_label = from_label

            if to_label is None or not isinstance(to_label, GenodeConfigurator.SessionLabel):
                self.to_label = GenodeConfigurator.SessionLabel(label=to_label)
            else:
                self.to_label = to_label

        def __repr__(self):
            return "Route(server=%s,service=%s)" % (self.server, self.service)

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

        def __init__(self, inst, parent, model, layer):
            self.model     = model
            self.layer     = layer
            self.layer_obj = inst

            self.name      = inst.identifier
            self.component = inst.component
            self.config    = inst.config.xml() if inst.config is not None else None
            self.parent    = parent
            self.routes    = list()

        def _create_generator(self):
            default = self.component.defaults()
            if default is not None:
                if default.get('dynamic') is None:
                    return DefaultConfigGenerator(default, self.config)
                else:
                    return DynamicConfigGenerator(self.component.binary_name(), self)
            elif self.config is not None:
                return DefaultConfigGenerator(None, self.config)
            else:
                return EmptyConfigGenerator()

        def _append_default_routes(self):
            # must be sorted before
            self.routes.append(GenodeConfigurator.Route(server='parent')) # route any-service to parent

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

            curserv   = None
            lastchild = None
            for r in self.routes:
                if curserv is None or curserv.get('name') != r.service \
                  or curserv.get('label') != r.from_label.label \
                  or curserv.get('label_prefix') != r.from_label.prefix \
                  or curserv.get('label_suffix') != r.from_label.suffix:

                    lastchild = None

                    if r.any_service():
                        curserv = ET.SubElement(route, 'any-service')
                    else:
                        curserv = ET.SubElement(route, 'service',
                                                name=r.service)

                        if not r.from_label.empty():
                            if r.from_label.label is not None:
                                curserv.set('label', r.from_label.label)
                            if r.from_label.prefix is not None:
                                curserv.set('label-prefix', r.from_label.prefix)
                            if r.from_label.suffix is not None:
                                curserv.set('label-suffix', r.from_label.suffix)

                # target
                if r.parent():
                    ET.SubElement(curserv, 'parent')
                elif r.any_child():
                    ET.SubElement(curserv, 'any-child')
                elif lastchild is None or lastchild.get('name') != r.server:
                    lastchild = ET.SubElement(curserv, 'child',
                                          name=r.server)

                    if not r.to_label.empty():
                        if r.to_label.label is not None:
                            lastchild.set('label', r.to_label.label)
                        if r.to_label.prefix is not None:
                            lastchild.set('label-prefix', r.to_label.prefix)
                        if r.to_label.suffix is not None:
                            lastchild.set('label-suffix', r.to_label.suffix)

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

            generator = self._create_generator()
            generator.adapt_routes()

            # generate <route>
            self._sort_routes()
            self._append_default_routes()
            self._routes_xml(start)

            # generate <config>
            generator.xml(start)

    class ConfigXML:

        def __init__(self, filename, subsystem, platform, xsd_file=None):
            self.filename  = filename
            self.subsystem = subsystem
            self.platform  = platform
            self.xsd_file  = xsd_file
            self.start_nodes = dict()

            self.parent_services = { "CAP", "LOG", "RM", "SIGNAL", "IO_MEM",
                                     "IRQ", "ROM", "RAM", "IO_PORT", "PD", "CPU"}

            self.default_caps = 300

        def _check_schema(self, root):
            if self.xsd_file is not None and hasattr(ET, "XMLSchema"):
                schema = ET.XMLSchema(file=self.xsd_file)
                if not schema.validate(root):
                    logging.error("Schema validation (%s) failed" % self.filename)
                else:
                    logging.info("Schema validation (%s) succeeded" % self.filename)

        def create_start_node(self, inst, model, layer):
            name = inst.identifier
            assert name not in self.start_nodes
            self.start_nodes[name] = GenodeConfigurator.StartNode(inst, self, model, layer)

            return self.start_nodes[name]

        def start_node(self, name):
            return self.start_nodes[name]

        def _write_header(self, root):
            # generate <parent-provides>
            provides = ET.SubElement(root, 'parent-provides')
            for s in sorted(self.parent_services):
                ET.SubElement(provides, 'service', name=s)

            # generate <default-route>
            routes    = ET.SubElement(root, 'default-route')
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
            for name in sorted(self.start_nodes.keys()):
                self.start_nodes[name].generate_xml(root, self.default_caps)
            self._write_footer(root)

            tree = ET.ElementTree(root)
            tree.write(self.filename, pretty_print=True)

            self._check_schema(root)


    def __init__(self, outpath, platform_model, config_xsd=None):
        self.outpath  = outpath
        self.platform = platform_model
        self.configs  = dict()

        self._prepare_files(config_xsd)

    def _prepare_files(self, config_xsd):
        # create ConfigXML for each non-static subsystem
        for pfc in self.platform.platform_graph.nodes():
            config = pfc.config()
            if config is not None:
                self.configs[pfc] = self.ConfigXML(self.outpath+config, pfc, self.platform, xsd_file=config_xsd)

    def create_configs(self, model, layer_name):
        layer = model.by_name[layer_name]
        for inst in layer.graph.nodes():
            pfc = layer._get_param_value('mapping', inst)
            if pfc in self.configs:

                node = self.configs[pfc].create_start_node(inst, model, layer)

                # add routes
                for e in layer.graph.out_edges(inst):
                    source_service = layer._get_param_value('source-service', e)
                    target_service = layer._get_param_value('target-service', e)
                    target_pfc     = layer._get_param_value('mapping', e.target)
                    if target_pfc == pfc:
                        node.add_route(self.Route(server=e.target.identifier,
                                                  service=source_service.name(),
                                                  from_label=source_service.label(),
                                                  to_label=target_service.label()))
                    else:
                        node.add_route(self.Route(server='parent',
                                                  service=source_service.name(),
                                                  from_label=source_service.label(),
                                                  to_label=target_service.label()))

        for cfg in self.configs.values():
            cfg.write_xml()
