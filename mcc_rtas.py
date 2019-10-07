#!/usr/bin/env python

import logging
from argparse import ArgumentParser
from mcc.rtas import Mcc

def get_args():
    descr = 'all arguments are optional'
    parser = ArgumentParser(description=descr)
    parser.add_argument('filename', default='rtas_control.xml', nargs='?')
    parser.add_argument('--basepath', default='models/')
    parser.add_argument('-o', '--outpath', default='./run/rtas-')
    return parser.parse_args()

if __name__ == '__main__':

    args = get_args()

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    mcc = Mcc(args.filename, basepath=args.basepath, outpath=args.outpath)
    mcc.execute()
