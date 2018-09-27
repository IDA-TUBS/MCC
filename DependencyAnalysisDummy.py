#!/usr/bin/env python

import logging
import argparse
from mcc.framework import Registry, Layer
from mcc.importexport import PickleImporter

import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description='')
parser.add_argument('--modelfile', type=str, default="/tmp/testmodel.pickle")
parser.add_argument('--queryfile', type=str, default="/tmp/testquery.xml")
parser.add_argument('--responsefile', type=str, default="/tmp/testresponse.xml")

args = parser.parse_args()

class QueryParser:
    def __init__(self, xml_file):
        self._file = xml_file
        if self._file is not None:
            parser = ET.XMLParser()

            self._tree = ET.parse(self._file, parser=parser)
            self._root = self._tree.getroot()

    def write_dummy_result(self, filename):
        assert(self._root.tag == 'query')
        
        step = self._root.find('./nodestep')
        if step is None:
            step = self._root.find('./edgestep')

        assert(step is not None)

        for op in step.findall('./map'):
            cand1 = ET.SubElement(op, 'candidate')
            cand1.text = 'SAFE'
            cand2 = ET.SubElement(op, 'candidate')
            cand2.text = 'UNSAFE'

        for op in step.findall('./assign'):
            value = ET.SubElement(op, 'value')
            value.text = 'SAFE'

        self._root.tag = 'result'
        self._tree.write(filename)


################
# main section #
################

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    # create registry for cross-layer model
    model = Registry()
    model.add_layer(Layer('func_arch'))
    model.add_layer(Layer('comm_arch'))

    # import model
    importer = PickleImporter(model)
    importer.read(args.modelfile)

    # read query file
    query = QueryParser(args.queryfile)

    # write response file
    query.write_dummy_result(args.responsefile)
