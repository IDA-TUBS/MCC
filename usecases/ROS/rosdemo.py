"""
Description
-----------

Implements query and status report functionality for ROS use cases.

:Authors:
    - Johannes Schlatow

"""

import logging
from mcc.framework import *
from mcc.model import SimplePlatformModel
from mcc import rosmodel

from xml.etree import ElementTree as ET


class Mcc:
    def __init__(self, repofile, queryfile, outpath='mcc/run/'):
        self._repofile  = repofile
        self._queryfile = queryfile
        self._outpath   = outpath

    def execute(self, chronological=False):
        failed  = False

        # find configurations
        sys    = rosmodel.SystemParser(self._queryfile)

        repo = rosmodel.Repository(self._repofile)

        mcc = rosmodel.MccBase(repo=repo,
                               chronologicaltracking=chronological)

        try:
            model = mcc.search_config(sys, outpath=self._outpath+'-')

        except Exception as e:
            failed = True
            import traceback
            traceback.print_exc()
            print(e)

        if failed:
            logging.error("Do not generate configs because of failed devices.")
            return
