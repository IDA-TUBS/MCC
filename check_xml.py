#!/usr/bin/env python

import logging
import argparse
import os
from mcc import parser as cfgparser
from mcc import model
from mcc import lib

from lxml import etree

parser = argparse.ArgumentParser(description='Check config model XML.')
parser.add_argument('file', metavar='xml_file', type=str, 
        help='XML file to be processed')
parser.add_argument('--schema', type=str, default="XMLCCC.xsd",
        help='XML Schema Definition (xsd)')
parser.add_argument('--batch', action='store_true')
parser.add_argument('--dotpath', type=str, default='./',
        help='Write graphs to DOT files in this path.')

args = parser.parse_args()

################
# main section #
################

def check_xml(xmlfile):
    basename = os.path.basename(xmlfile)
    try:
        # create repo and check schema
        repo = cfgparser.Repository(xmlfile, args.schema)
        print('%s - OKAY' % basename)

        # check <repository>
        # FIXME let check functions return result
        repo.check_functions_unambiguous()
        repo.check_components_unambiguous()
        repo.check_classification_unambiguous()
        repo.check_binaries()
        repo.check_atomic_components()
        repo.check_composite_components()

    except cfgparser.Repository.NodeNotFoundError:
        print('%s - SKIP : no <repository> node' % basename)
    except etree.XMLSyntaxError as e:
        print('%s - FAIL : \n\t%s' % (basename, e))
        return

    try:
        # check <platform>
        pf_xml = cfgparser.PlatformParser(xmlfile, args.schema)
        pf_model = model.SimplePlatformModel(pf_xml)
        pf_model.write_dot(args.dotpath + basename[:-4] + '-platform.dot')
    except cfgparser.PlatformParser.NodeNotFoundError:
        print('%s - SKIP : no <platform> node' % basename)

    try:
        # check <system>
        sys_xml   = cfgparser.SystemParser(xmlfile, args.schema)
        sys_model = model.FuncArchQuery(sys_xml)
        sys_model.write_dot(args.dotpath + basename[:-4] + '-system.dot')
    except cfgparser.SystemParser.NodeNotFoundError:
        print('%s - SKIP : no <system> node' % basename)

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    if args.batch:
        # interpret args.file as path
        for xmlfile in os.listdir(args.file):
            if not xmlfile.endswith('.xml'):
                continue

            check_xml(args.file+'/'+xmlfile)
            print('')

    else:
        check_xml(args.file)
