"""
Description
-----------

Implements analysis engines for simulation of design-space exploration.

:Authors:
    - Johannes Schlatow

"""
import logging
from mcc.framework import *
from mcc.importexport import *

import csv
import random
import math
import time

class SimulationEngine(AnalysisEngine):
    """ Base class. Implements bookkeeping of found solutions.
    """
    class Solution:
        def __init__(self, **kwargs):
            self.data = kwargs

    def __init__(self, layer, model, outpath=None):
        super().__init__(layer, None)
        self.model        = model
        self.modeloutpath = outpath
        self.solutions    = list()

        self._last_iteration  = 0
        self._last_rolledback = 0
        self._last_variables  = set()

    def write_stats(self, outpath=None):
        print("Solutions found: %d" % len(self.solutions))

        if outpath:
            with open(outpath, 'w') as csvfile:
                fieldnames = ['solution',
                              'time',
                              'iterations',
                              'total_variables',
                              'new_variables',
                              'combinations',
                              'combinations_left',
                              'complexity',
                              'operations',
                              'rolledback']
                writer = csv.DictWriter(csvfile,
                                        delimiter='\t',
                                        fieldnames=fieldnames)

                writer.writeheader()
                i = 1
                for s in self.solutions:
                    s.data['solution'] = i
                    writer.writerow(s.data)
                    i += 1

    def write_model(self):
        if self.modeloutpath:
            export = PickleExporter(self.model)
            export.write('%smodel-%d.pickle' % (self.modeloutpath, len(self.solutions)+1))

    def record_solution(self):
        graph = self.model.decision_graph

        ######################
        # write model file
        self.write_model()

        ######################
        # acquire statistics

        # a) number of variables in this solution
        variables = self.model._find_variables()

        # (optional) assigned values of these variables

        # b) number of possible combinations for these variables
        combinations = 1
        for v in variables:
            combinations = combinations * len(v.layer.untracked_get_param_candidates(v.param, v.obj))

        # number of combinations left to iterate (theoretical)
        combinations_left = 1
        for v in variables:
            failed = v.layer.get_param_failed(v.param, v.obj)
            if failed:
                left = failed.candidates_left() + 1
            else:
                left = len(v.layer.untracked_get_param_candidates(v.param, v.obj))

            if left > 1:
                combinations_left = combinations_left * left


        # c) how many iterations were required between this and the last solution
        iterations = self.model.backtracking_try - self._last_iteration
        self._last_iteration = self.model.backtracking_try

        # d) how many operations were executed between this and the last solution
        rolledback = self.model.stats['rolled-back operations'] - self._last_rolledback
        self._last_rolledback = self.model.stats['rolled-back operations']

        # e) calculate number of new variables
        newvars = variables - self._last_variables
        self._last_variables = variables

        # store solution statistics
        self.solutions.append(self.Solution(total_variables=len(variables),
                                            new_variables=len(newvars),
                                            time=time.monotonic(),
                                            combinations=combinations,
                                            combinations_left=combinations_left,
                                            complexity=self.model.backtracking_try + combinations_left,
                                            iterations=iterations,
                                            operations=len(graph.nodes()),
                                            rolledback=rolledback))


class BacktrackingSimulation(SimulationEngine):
    """ Performs design-space exploration by rejecting solutions as long as there are still more candidates to
        iterate. Keeps track of all found solutions and statistics.
    """
    def __init__(self, layer, model, outpath=None):
        super().__init__(layer, model, outpath)

    def batch_check(self, iterable):
        self.record_solution()
        graph = self.model.decision_graph

        # make sure to track a read access to all leaves in the decision_graph
        for n in graph.leaves():
            for p in graph.written_params(n):
                graph.track_read(p.layer, p.obj, p.param)

        for node in graph.nodes():
            if graph.revisable(node):
                return False

        return True

    def node_types(self):
        return []


class AdaptationSimulation(SimulationEngine):
    """ Performs simulation of parameter adaptation by changing parameters and rolling back
        to their writing operation.
    """
    def __init__(self, layer, model, wcet_engine, factor=1.1, outpath=None):
        super().__init__(layer, model, outpath)

        assert factor > 1
        self.factor = factor
        self.wcet_engine = wcet_engine
        self.adaptations = list()

    def write_adaptations(self, filename):
        with open(filename, 'w') as csvfile:
            fieldnames = ['adaptation',
                          'taskname',
                          'wcet']
            writer = csv.DictWriter(csvfile,
                                    delimiter='\t',
                                    fieldnames=fieldnames)

            writer.writeheader()
            i = 1
            for taskname,wcet in self.adaptations:
                row = { 'adaptation' : i,
                        'taskname'   : taskname,
                        'wcet'       : wcet }

                writer.writerow(row)
                i += 1

    def batch_check(self, iterable):
        self.record_solution()

        graph = self.model.decision_graph
        tg = self.model.by_name['task_graph']

        # randomly select a task from taskgraph
        task_set = list(tg.untracked_nodes())
        culprit = random.choice(task_set)
        task = culprit.untracked_obj()

        # increase WCET by factor
        new_wcet = int(math.ceil(tg.untracked_get_param_value('wcet', culprit).copy() * self.factor))

        logging.info("Increasing WCET of task %s to %d" % (task, new_wcet))

        # store new WCET persistently in WcetEngine
        self.wcet_engine.update_wcet(task.name, new_wcet)

        # hack: add new value to candidates
        candidates = tg.untracked_get_param_candidates('wcet', culprit)
        candidates.add(new_wcet)
        tg.untracked_set_param_candidates('wcet', culprit, candidates)

        # write log with tasknames and current WCET
        self.adaptations.append((task.name, new_wcet))

        # find and return corresponding node in decision graph
        return graph.find_writers(tg, culprit, 'wcet').assign

    def node_types(self):
        return []
