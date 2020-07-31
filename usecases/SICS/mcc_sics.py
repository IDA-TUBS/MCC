#!/usr/bin/env python3

import logging
from argparse import ArgumentParser
from sics import Mcc

def get_args():
    descr = 'all arguments are optional'
    parser = ArgumentParser(description=descr)
    parser.add_argument('filename', default='sics_control.xml', nargs='?')
    parser.add_argument('--basepath', default='../../models/sics/')
    parser.add_argument('-o', '--outpath', default='./run/')
    parser.add_argument('-e', '--explore', action='store_true', default=False)
    parser.add_argument('-a', '--adapt', action='store_true', default=False)
    parser.add_argument('--replay_adapt', type=str, default=None)
    parser.add_argument('--wcet_factor', default=1.1, type=float)
    parser.add_argument('--chronological', action='store_true', default=False)
    return parser.parse_args()

if __name__ == '__main__':

    args = get_args()

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    mcc = Mcc(args.filename, basepath=args.basepath, outpath=args.outpath)
    if args.replay_adapt:
        adapt = args.replay_adapt
    else:
        adapt = False if not args.adapt else args.wcet_factor
    mcc.execute(explore=args.explore, chronological=args.chronological, adapt=adapt)
