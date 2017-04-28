#!/usr/bin/env python

import xml.etree.ElementTree as ET

import networkx as nx

import logging
import argparse

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

    parser = ConfigModelParser(args.file)
    parser.check_structure()
    parser.check_functions_unambiguous()
    parser.check_components_unambiguous()
    parser.check_classification_unambiguous()
    parser.check_binaries()
    parser.check_atomic_components()
    parser.check_composite_components()


    parser.check_system()
