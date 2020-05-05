#!/usr/bin/env python

import logging
from argparse import ArgumentParser
from rtas import Mcc

def get_args():
    descr = 'all arguments are optional'
    parser = ArgumentParser(description=descr)
    parser.add_argument('filename', default='rtas_control.xml', nargs='?')
    parser.add_argument('--basepath', default='../../models/rtas/')
    parser.add_argument('-o', '--outpath', default='./run/')
    parser.add_argument('-e', '--explore', action='store_true', default=False)
    parser.add_argument('-a', '--adapt', action='store_true', default=False)
    parser.add_argument('--wcet_factor', default=1.1, type=float)
    parser.add_argument('--chronological', action='store_true', default=False)
    return parser.parse_args()

if __name__ == '__main__':

    args = get_args()

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    mcc = Mcc(args.filename, basepath=args.basepath, outpath=args.outpath)
    mcc.execute(explore=args.explore, chronological=args.chronological, adapt=False if not args.adapt else args.wcet_factor)