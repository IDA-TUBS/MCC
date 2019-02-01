"""
Description
-----------

Implements external analysis engines.

:Authors:
    - Johannes Schlatow

"""
import logging
from mcc.framework import *
from mcc.graph import *
from mcc.importexport import PickleExporter
from mcc.parser import XMLParser
import time

from xml.etree import ElementTree as ET

class ResultParser(XMLParser):
    class StepResults:
        def __init__(self, xml_node):
            self.xml_node = xml_node

        def parse_map_result(self, obj_id):
            node = self.xml_node.find("./map[@node='%s']" % obj_id)
            assert(node is not None)

            candidates = set()
            for candidate in node.findall('candidate'):
                candidates.add(candidate.text)

            return candidates

        def parse_assign_result(self, obj_id):
            node = self.xml_node.find("./assign[@node='%s']" % obj_id)
            assert(node is not None)

            value = node.find('value').text
            return value

    def find_valid_step(self, layer, param, version, steptype='nodestep'):
        if self._root.tag != 'result':
            return None

        if self._root.get('version') != version:
            return None

        if self._root.get('param') != param:
            return None

        step_node = self._root.find(steptype)

        if step_node.get('layer') != layer:
            return None

        return ResultParser.StepResults(step_node)

class DependencyAnalysisEngine(ExternalAnalysisEngine):
    def __init__(self, registry, layers, model_filename, query_filename, result_filename):
        # FIXME acl
        acl = { layers[0] : { 'reads' : set(['mapping', 'service', layers[1].name]) },
                layers[1] : { 'reads' : set([layers[0].name]) } }
        ExternalAnalysisEngine.__init__(self, layers[0], param='testparam', acl=acl)

        self.registry = registry
        self.query_filename  = query_filename
        self.result_filename = result_filename
        self.model_filename  = model_filename
        self.version = 1

    def _export_model(self):

        # set node export IDs (eid)
        eid = 1
        for node in self.layer.graph.nodes():
            self.layer.graph.node_attributes(node)['eid'] = eid
            eid += 1

        export = PickleExporter(self.registry, self.acl)
        export.write(self.model_filename)

    def _start_query(self):
        self.last_query_version = "%s#%d" % (id(self), self.version)

        self.query_file = open(self.query_filename, 'w')
        self.query_file.write('<query version="%s" param="%s">\n' % (self.last_query_version, self.param))
        self.query_file.write('<nodestep layer="%s">\n' % (self.layer.name))

    def _end_query(self):
        self.query_file.write('</nodestep>\n')
        self.query_file.write('</query>\n')
        self.query_file.close()

        self.version += 1

    def _query_map(self, obj, candidates):
        logging.info("Sending MAP query to external analysis engine")
        if candidates is None or len(candidates) == 0:
            self.query_file.write('  <map node="%s" />\n' % self.layer.graph.node_attributes(obj)['eid'])
        else:
            self.query_file.write('  <map node="%s">\n' % self.layer.graph.node_attributes(obj)['eid'])
            for c in candidates:
                self.query_file.write('  <candidate>%s</candidate>\n' % c)
            self.query_file.write('  </map>\n')


    def _query_assign(self, obj, candidates):
        logging.info("Sending ASSIGN query to external analysis engine")
        if candidates is None or len(candidates) == 0:
            self.query_file.write('  <assign node="%s" />\n' % self.layer.graph.node_attributes(obj)['eid'])
        else:
            self.query_file.write('  <assign node="%s">\n' % self.layer.graph.node_attributes(obj)['eid'])
            for c in candidates:
                self.query_file.write('  <candidate>%s</candidate>\n' % c)
            self.query_file.write('  </assign>\n')

    def _wait_for_result(self):
        self._wait_for_file(self.result_filename)

        self.stepresults = None
        while self.stepresults is None:
            time.sleep(1)
            resultparser = ResultParser(self.result_filename)
            self.stepresults = resultparser.find_valid_step(layer=self.layer.name, param=self.param,
                    version=self.last_query_version, steptype="nodestep")
            print("Waiting for valid version")

        return True

    def _parse_map(self, obj):
        return self.stepresults.parse_map_result(self.layer.graph.node_attributes(obj)['eid'])

    def _parse_assign(self, obj):
        return self.stepresults.parse_assign_result(self.layer.graph.node_attributes(obj)['eid'])
