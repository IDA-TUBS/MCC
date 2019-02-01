#!/usr/bin/env python

import logging
from mcc import c1

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    mcc = c1.Mcc('mcc_control.xml', basepath='models/', outpath='/tmp/test-')
    mcc.execute()
