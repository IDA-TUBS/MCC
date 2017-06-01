#!/usr/bin/env python

import xml.etree.ElementTree as ET

import logging
import argparse

from mcc import parser

aparser = argparse.ArgumentParser(description='Check config model XML.')
aparser.add_argument('file', metavar='xml_file', type=str, 
        help='XML file to be processed')

args = aparser.parse_args()

################
# main section #
################

if __name__ == '__main__':

    p = parser.ConfigModelParser(None)
    p.structure_to_markdown(args.file)
