"""
Description
-----------

Implements query and status report functionality for C1 use cases.

:Authors:
    - Johannes Schlatow

"""

import logging
from mcc.framework import *
from mcc.model import SimplePlatformModel
from mcc import parser as cfgparser
from mcc import lib
from mcc.configurator import GenodeConfigurator

from xml.etree import ElementTree as ET

class StatusGenerator:
    class DeviceStatus:
        def __init__(self, name, device):
            self._name   = name
            self._device = device
            self._cfgfound = 'false'
            self._cfgokay  = 'false'
            self._cfgerror = None

            self._model    = None
            self._platform = None

        def generate_xml(self, root):
            status = ET.SubElement(root, 'mcc_status', name=self._name)

            cfg = ET.SubElement(status, 'configuration', found=self._cfgfound, generated=self._cfgokay)
            cfg.text = self._cfgerror

            ET.SubElement(status, 'operationmode', name=self._device.opmode())
            # TODO fill with status information

            if self._platform is not None:
                metrics = ET.SubElement(status, 'metrics')
                for sub in self._platform.platform_graph.nodes():
                    if sub.static():
                        continue

                    node = ET.SubElement(metrics, 'subsystem', name=sub.name())
                    for name in ['ram', 'caps']:
                        provided  = sub.quantum(name)
                        remaining = sub.state('%s-remaining' % name)
                        ET.SubElement(node, name,  provided=str(provided),  requested=str(provided-remaining))

                    # outbound network traffic (currently, we do not distinguish between comms in the
                    # platform model, thus we can only sum up the traffic per processing resource)
                    value = sub.state('out_traffic')
                    ET.SubElement(node, 'out_traffic', byte_s=str(value))

                    # TODO cpu load

    def __init__(self, devices):

        self._devices = dict()
        for name, device in devices.items():
            self._devices[name] = self.DeviceStatus(name, device)

    def mcc_result(self, name, found, platform=None, model=None):
        if found:
            self._devices[name]._cfgfound = 'true'
            assert platform is not None
            assert model is not None
            self._devices[name]._model = model
            self._devices[name]._platform = platform
        else:
            self._devices[name]._cfgfound = 'false'

    def cfg_result(self, name, generated, error=None):
        if generated:
            self._devices[name]._cfgokay = 'true'
        else:
            self._devices[name]._cfgokay = 'false'

        self._devices[name]._cfgerror = error

    def write_to_file(self, filename):
        root = ET.Element('xml')
        for device in self._devices.values():
            device.generate_xml(root)

        tree = ET.ElementTree(root)
        tree.write(filename)

class ControlParser:
    class DeviceControl:
        def __init__(self, xml_node, basepath):
            self._xml_node = xml_node
            self._basepath = basepath

            self._repo     = 'c1_repo.xml'

            # device name -> mode -> accel
            self._mode_map = { 'doris' : {
                                   'exploration' : {
                                       'normal' : 'c1_object_recognition.xml',
                                       'accel'  : 'c1_object_recognition_hw.xml' },
                                    'pose' : {
                                       'normal' : 'c1_pose_estimation.xml',
                                       'accel'  : 'c1_pose_estimation_hw.xml' }},
                               'boris' : {
                                   'exploration' : {
                                       'normal' : 'c1_object_recognition.xml',
                                       'accel'  : 'c1_object_recognition_hw.xml' },
                                    'pose' : {
                                       'normal' : 'c1_pose_estimation.xml',
                                       'accel'  : 'c1_pose_estimation_hw.xml' }}}

            self._pf_map   = { 'doris'       : 'base.xml',
                               'boris'       : 'base.xml'}

        def repo_filename(self):
            return self._basepath + self._repo

        def platform_filename(self):
            name = self._xml_node.get('name')
            return self._basepath + self._pf_map[name]

        def query_filename(self):
            name = self._xml_node.get('name')
            mode = self.opmode()
            hw   = 'accel' if self._xml_node.find('hw_acceleration').get('value') == 'true' else 'normal'
            return self._basepath + self._mode_map[name][mode][hw]

        def flux(self):
            return int(self._xml_node.find('flux').get('value'))

        def opmode(self):
            return self._xml_node.find('operationmode').get('name')


    def __init__(self, xml_file, basepath):
        self._file     = xml_file
        self._basepath = basepath
        assert(self._file is not None)

        parser = ET.XMLParser()
        self._tree = ET.parse(self._file, parser=parser)
        self._root = self._tree.getroot()

    def find_device(self, name):
        device = self._root.find("./mcc_control[@name='%s']" % name)
        if device is not None:
            return self.DeviceControl(device, self._basepath)

        return None

class EnvironmentModel:
    # TODO manage flux and reliability requirements
    def __init__(self, control):
        self.control = control

    def accept_properties(self, arg):
        return True

class Mcc:
    def __init__(self, filename, basepath='mcc/models/', outpath='mcc/run/'):
        self._filename = filename
        self._basepath = basepath
        self._outpath  = outpath

        self._parser = ControlParser(filename, basepath)
        self._devices = dict()
        for name in ['doris', 'boris']:
            dev = self._parser.find_device(name)
            if dev is not None:
                self._devices[name] = dev
            else:
                logging.error("Unable to find device %s in %s" % (name, self._filename))

        self._devstate = StatusGenerator(self._devices)

    def execute(self):
        results = dict()
        failed  = False

        # find configurations
        for name, device in self._devices.items():
            pffile   = device.platform_filename()
            pf       = cfgparser.PlatformParser(pffile)
            pf_model = SimplePlatformModel(pf)

            env      = EnvironmentModel(device)

            # try to create repositories from given files
            repos = list()
            repos.append(cfgparser.Repository(pffile))
            repos.append(cfgparser.Repository(device.repo_filename()))

            cfg = cfgparser.AggregateRepository(repos)
            mcc = lib.SimpleMcc(repo=cfg, test_backtracking=False)

            base = lib.BaseModelQuery()

            basesys   = cfgparser.SystemParser(pffile)
            query, basemodel = mcc.search_config(pf_model, basesys,
                                   outpath=self._outpath+name+'-'+basesys.name()+'-',
                                   with_da=False, envmodel=env)

            # store basemodel in BaseModelQuery
            base.insert(name=basesys.name(),
                        query_graph=query,
                        comp_inst=basemodel.by_name['comp_inst'],
                        filename=pffile)

            sys = cfgparser.SystemParser(device.query_filename())
            try:
                query, model = mcc.search_config(pf_model, sys, base,
                                          outpath=self._outpath+name+'-',
                                          with_da=False, envmodel=env)

                results[name] = (pf_model, model)

                self._devstate.mcc_result(name, found=True, platform=pf_model, model=model)

            except Exception as e:
                failed = True
                self._devstate.mcc_result(name, found=False)
                import traceback
                traceback.print_exc()
                print(e)

        if failed:
            logging.error("Do not generate configs because of failed devices.")
            for name in self._devices.keys():
                self._devstate.cfg_result(name, generated=False,
                                         error="Configs not generated because search failed for at least one device.")
            return

        # generate configs
        for name, (pf_model, model) in results.items():
            # generate <config> from model
            configurator = GenodeConfigurator(self._outpath+name+'-', pf_model)
            configurator.create_configs(model, layer_name='comp_inst')
            self._devstate.cfg_result(name, generated=True)

        # write status reports
        for name in self._devices.keys():
            self._devstate.write_to_file(self._outpath+'status.xml')
