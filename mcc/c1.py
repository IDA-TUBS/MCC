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
                                       'accel'  : 'c1_object_recognition_hw.xml' }},
                               'boris' : {
                                   'exploration' : {
                                       'normal' : 'c1_object_recognition.xml',
                                       'accel'  : 'c1_object_recognition_hw.xml' }}}

            self._pf_map   = { 'doris'       : 'base.xml',
                               'boris'       : 'base.xml'}

        def repo_filename(self):
            return self._basepath + self._repo

        def platform_filename(self):
            name = self._xml_node.get('name')
            return self._basepath + self._pf_map[name]

        def query_filename(self):
            name = self._xml_node.get('name')
            mode = self._xml_node.find('operationmode').get('name')
            hw   = 'accel' if self._xml_node.find('hw_acceleration').get('value') == 'true' else 'normal'
            return self._basepath + self._mode_map[name][mode][hw]

        def flux(self):
            return int(self._xml_node.find('flux').get('value'))


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

    def execute(self):
        results = dict()
        failed  = False

        # find configurations
        for name, device in self._devices.items():
            pffile   = device.platform_filename()
            pf       = cfgparser.PlatformParser(pffile)
            pf_model = SimplePlatformModel(pf)

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
                                   with_da=False)

            # store basemodel in BaseModelQuery
            base.insert(name=basesys.name(),
                        query_graph=query,
                        comp_inst=basemodel.by_name['comp_inst'],
                        filename=pffile)

            sys = cfgparser.SystemParser(device.query_filename())
            try:
                query, model = mcc.search_config(pf_model, sys, base,
                                          outpath=self._outpath+name+'-',
                                          with_da=False)

                results[name] = (pf_model, model)

            except Exception as e:
                failed = True
                import traceback
                traceback.print_exc()
                print(e)

        if failed:
            logging.error("Do not generate configs because of failed devices.")
            return

        # generate configs
        for name, (pf_model, model) in results.items():
            # generate <config> from model
            configurator = GenodeConfigurator(self._outpath+name+'-', pf_model)
            configurator.create_configs(model, layer_name='comp_inst')
