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

            self._repo     = 'rtas_repo.xml'
            self._pf       = 'rtas_base.xml'

        def name(self):
            return self._xml_node.get('name')

        def repo_filename(self):
            return self._basepath + self._xml_node.get('repo')

        def platform_filename(self):
            return self._basepath + self._xml_node.get('platform')

        def query_filename(self):
            return self._basepath + self._xml_node.get('query')

    def __init__(self, xml_file, basepath):
        self._file     = xml_file
        self._basepath = basepath
        assert(self._file is not None)

        parser = ET.XMLParser()
        self._tree = ET.parse(self._file, parser=parser)
        self._root = self._tree.getroot()

    def find_devices(self):
        result = set()
        for device in self._root.findall("./mcc_control"):
            result.add(self.DeviceControl(device, self._basepath))

        return result


class ConstraintsModel:
    def __init__(self, control):
        self.control = control

        self._latency_constraints = list()
        self._reliability_constraints = list()
        self._unreliable_components = set()

    def parse(self, model):
        for c in self._parse_latencies():
            srcnode = self._find_name_in_model(model, c['source'])
            snknode = self._find_name_in_model(model, c['sink'])

            assert srcnode is not None, "%s not found in query" % c['source']
            assert snknode is not None, "%s not found in query" % c['sink']
            c['source'] = srcnode
            c['sink']   = snknode
            self._latency_constraints.append(c)

        for c in self._parse_reliability():
            srcnode = self._find_name_in_model(model, c['source'])
            snknode = self._find_name_in_model(model, c['sink'])

            assert srcnode is not None, "%s not found in query" % c['source']
            assert snknode is not None, "%s not found in query" % c['sink']
            c['source'] = srcnode
            c['sink']   = snknode
            self._reliability_constraints.append(c)

        self._unreliable_components = self._parse_unrealiable()

    def _find_name_in_model(self, model, name):
        for n in model.by_order[0].graph.nodes():
            if n.untracked_obj().identifier() == name:
                return n

        return None

    def _parse_latencies(self):
        constraints = list()
        for lat in self.control._xml_node.findall('./latency'):
            data = { 'source' : lat.get('source'),
                     'sink'   : lat.get('sink') }

            if lat.get('max_rt_us'):
                data['max_rt'] = int(lat.get('max_rt_us'))
                assert False, 'max_rt_us not supported in latency requirement'
            if lat.get('max_age_us'):
                data['max_age'] = int(lat.get('max_age_us'))
                assert False, 'max_age_us not supported in latency requirement'
            if lat.get('min_rate_us'):
                data['min_rate'] = int(lat.get('min_rate_us'))

            constraints.append(data)

        return constraints

    def _parse_reliability(self):
        constraints = list()
        for rel in self.control._xml_node.findall('./reliability'):
            data = { 'source' : rel.get('source'),
                     'sink'   : rel.get('sink'),
                     'value'  : rel.get('value')}

            constraints.append(data)

        return constraints

    def _parse_unrealiable(self):
        comps = set()
        for pf in self.control._xml_node.findall('./platform_component'):
            rel = pf.get('reliability')
            if rel and rel == 'low':
                comps.add(pf.get('name'))

        return comps

    def latency_constraints(self):
        return self._latency_constraints

    def reliability_constraints(self):
        return self._reliability_constraints

    def unreliable_pf_components(self):
        return self._unreliable_components


class Mcc:
    def __init__(self, filename, basepath='mcc/models/', outpath='mcc/run/'):
        self._filename = filename
        self._basepath = basepath
        self._outpath  = outpath

        self._parser = ControlParser(filename, basepath)
        self._devices = dict()
        for dev in self._parser.find_devices():
            name = dev.name()
            self._devices[name] = dev

    def execute(self, explore=False, chronological=False):
        results = dict()
        failed  = False

        # find configurations
        for name, device in self._devices.items():
            pffile   = device.platform_filename()
            pf       = cfgparser.PlatformParser(pffile)
            pf_model = SimplePlatformModel(pf)

            constr   = ConstraintsModel(device)

            # try to create repositories from given files
            repos = list()
            repos.append(cfgparser.Repository(pffile))
            repos.append(cfgparser.Repository(device.repo_filename()))

            cfg = cfgparser.AggregateRepository(repos)
            mcc = lib.SimpleMcc(repo=cfg, test_backtracking=explore,
                                          chronologicaltracking=chronological)

            base = lib.BaseModelQuery()

            basesys   = cfgparser.SystemParser(pffile)
            query, basemodel = mcc.search_config(pf_model, basesys,
                                   outpath=self._outpath+name+'-'+basesys.name()+'-',
                                   with_da=False, constrmodel=None)

            # store basemodel in BaseModelQuery
            base.insert(name=basesys.name(),
                        query_graph=query,
                        comp_inst=basemodel.by_name['comp_inst'],
                        filename=pffile)

            sys = cfgparser.SystemParser(device.query_filename())
            try:
                query, model = mcc.search_config(pf_model, sys, base,
                                          outpath=self._outpath+name+'-',
                                          with_da=False, constrmodel=constr)

                results[name] = (pf_model, model)

            except Exception as e:
                failed = True
                import traceback
                traceback.print_exc()
                print(e)

        if failed:
            logging.error("Do not generate configs because of failed devices.")
            return
