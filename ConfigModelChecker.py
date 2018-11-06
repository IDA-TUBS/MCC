#!/usr/bin/env python

import logging
import argparse
from mcc import parser as cfgparser
from mcc import model
from mcc import lib

parser = argparse.ArgumentParser(description='Check config model XML.')
parser.add_argument('file', metavar='xml_file', type=str, 
        help='XML file to be processed')
parser.add_argument('--schema', type=str, default="XMLCCC.xsd",
        help='XML Schema Definition (xsd)')
parser.add_argument('--platform', type=str, default=None,
        help='XML file with platform specification')
parser.add_argument('--repo', type=str, default=None,
        help='XML file with contract repository')
parser.add_argument('--dotpath', type=str,
        help='Write graphs to DOT files in this path.')
parser.add_argument('--dependency_analysis', action='store_true')

args = parser.parse_args()

################
# main section #
################

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    repofile = args.repo
    if repofile is None:
        repofile = args.file

    pffile = args.platform
    if pffile is None:
        pffile = args.file

    cfg = cfgparser.Repository(repofile, args.schema)
    mcc = lib.SimpleMcc(repo=cfg)
    mcc.search_config(platform_xml=pffile, system_xml=args.file, xsd_file=args.schema, outpath=args.dotpath, with_da=args.dependency_analysis)

    # TODO implement Configurator (generate subsystem <config>s from model)

    # TODO check generated config against Genode's config.xsd
