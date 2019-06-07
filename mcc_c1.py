#!/usr/bin/env python

import logging
from argparse import ArgumentParser
from mcc import c1

def get_args():
    descr = 'all arguments are optional'
    parser = ArgumentParser(description=descr)
    parser.add_argument('filename', default='mcc_control.xml', nargs='?')
    parser.add_argument('--basepath', default='models/')
    parser.add_argument('-o', '--outpath', default='/tmp/test-')
    return parser.parse_args()

if __name__ == '__main__':

    args = get_args()

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    mcc = c1.Mcc(args.filename, basepath=args.basepath, outpath=args.outpath)
    mcc.execute()
