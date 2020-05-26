#!/usr/bin/env python3

import logging
from argparse import ArgumentParser
from rosdemo import Mcc

def get_args():
    descr = 'all arguments are optional'
    parser = ArgumentParser(description=descr)
    parser.add_argument('--repofile', default='../../models/ros/repo.xml')
    parser.add_argument('--queryfile', default='../../models/ros/query.xml')
    parser.add_argument('-o', '--outpath', default='./run/ros')
    parser.add_argument('--chronological', action='store_true', default=False)
    return parser.parse_args()

if __name__ == '__main__':

    args = get_args()

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    mcc = Mcc(repofile=args.repofile, queryfile=args.queryfile, outpath=args.outpath)
    mcc.execute(chronological=args.chronological)
