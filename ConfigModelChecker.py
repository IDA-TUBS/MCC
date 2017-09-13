#!/usr/bin/env python

import xml.etree.ElementTree as ET

import networkx as nx

import logging
import argparse
from mcc import parser as cfgparser
from mcc import model

parser = argparse.ArgumentParser(description='Check config model XML.')
parser.add_argument('file', metavar='xml_file', type=str, 
        help='XML file to be processed')
parser.add_argument('--dotpath', type=str,
        help='Write graphs to DOT files in this path.')

args = parser.parse_args()

################
# main section #
################

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    cfg = cfgparser.Repository(args.file)
    cfg.check_structure()
    cfg.check_functions_unambiguous()
    cfg.check_components_unambiguous()
    cfg.check_classification_unambiguous()
    cfg.check_binaries()
    cfg.check_atomic_components()
    cfg.check_composite_components()

    mcc = model.Mcc(repo=cfg)
    mcc.search_config(args.file, args)

#    parser.check_system()
