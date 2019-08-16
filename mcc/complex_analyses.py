"""
Description
-----------

Implements more sophisticated analysis engines.

:Authors:
    - Johannes Schlatow

"""
import logging
from mcc.framework import *

from collections import OrderedDict

from ortools.sat.python import cp_model

class CPMappingEngine(AnalysisEngine):
    """ Assigns platform mappings using ortools' CP-sat solver """

    class ModelData():
        """ helper class for easier access to all the CP model data """
        def __init__(self, objects, platforms):
            self.model = cp_model.CpModel()
            self.o = objects
            self.p = platforms

            #generate the variables which will contain the final solution
            self.m = dict()
            for o in self.o:
                o_vars = []
                for p in self.p:
                    self.m[o, p] = self.model.NewBoolVar('%s on %s' % (o, p))
                    o_vars.append(self.m[o, p])
                #each object should only be mapped once
                self.model.Add(1 == sum(o_vars))

        def AND(self, *literals):
            """ return a BoolVar which is true iff all literals are true """
            lliterals = list(literals)
            anded = self.model.NewBoolVar(' and '.join(map(str, lliterals)))
            self.model.Add(anded == 1).OnlyEnforceIf(lliterals)
            self.model.AddBoolAnd(lliterals).OnlyEnforceIf(anded)
            return anded

    def __init__(self, layer, repo, pf_model, cost_priorities=None):
        acl = { layer : { 'reads' : set(['dependencies']) } }
        AnalysisEngine.__init__(self, layer, param='mapping', acl=acl)
        self.pf_model = pf_model
        self.repo = repo

        # Each function must return a tuple with two elements:
        #   expr: The linear expression for the objective
        #   bound: The upper bound on the possible values of the evaluated
        #          'expr'. Note that this bound does not necessarily have to be
        #          the maximum possible value. Enforcing the bound to be the
        #          maximum might require extra code which would be redundant to
        #          already defined solution constraints.
        self._cost_funcs = { #insertion order specifies default priorities
                'comm': self._gen_communication_cost_data,
                }
        if cost_priorities is None:
            cost_priorities = list(self._cost_funcs.keys())
        self.cost_priorities = cost_priorities

    def _gen_cost_data(self, data):
        """ return the data required for setting and evaluating an objective

        Multiple cost objectives are prioritized lexicographically. Thus, if
        the total objective is to be minimized, lower values of high-priority
        objectives are always preferred even if this leads to far greater
        values of the lower-prioritized objectives.
        """
        result = OrderedDict()
        for category in reversed(self.cost_priorities):
            #The expression of each objective is multiplied with a factor so
            #that the objectives do not interfere with each other.
            step_size = 1
            if len(result): #if not the lowest priority
                previous = next(reversed(result.values()))
                #guarantee growing step size even if the upper bound was <= 1
                step_size = previous['step_size'] * max(2, previous['bound'])

            expr, bound = self._cost_funcs[category](data)
            result[category] = {
                    'expr': step_size * expr,
                    'step_size': step_size,
                    'bound': bound,
                    }
        return result

    def _log_costs(self, cost_data, objective_value):
        remaining = objective_value
        #begin with the most-prioritized cost objective
        for category, data in reversed(cost_data.items()):
            current = remaining // data['step_size']
            remaining -= current * data['step_size']
            assert 0 <= current <= data['bound']

            msg = 'costs [%s]: %d/%d'
            logging.info(msg % (category, current, data['bound']))

    def _gen_communication_cost_data(self, data):
        expr = bound = 0
        for o in data.o:
            # directly connected objects on different sources will have cost 1
            for dep in self.layer.graph.out_edges(o):
                if dep.target not in data.o:
                    continue

                bound += 1
                for p in data.p:
                    expr += data.AND(data.m[o, p].Not(), data.m[dep.target, p])
        return expr, bound

    def batch_assign(self, candidates, objects, bad_combinations):
        if objects is None:
            assert len(bad_combinations) == 0
            objects = list(candidates.keys())
        data = self.ModelData(objects, list(set().union(*candidates.values())))

        for o in data.o:
            for p in candidates[o].symmetric_difference(data.p):
                data.model.Add(0 == data.m[o, p])
        for bad_combination in bad_combinations:
            bad_vars = [data.m[k] for k in zip(data.o, bad_combination)]
            bad_values = len(bad_vars) * (1,)
            data.model.AddForbiddenAssignments(bad_vars, [bad_values])

        cost_data = self._gen_cost_data(data)
        data.model.Minimize(sum(d['expr'] for d in cost_data.values()))

        solver = cp_model.CpSolver()
        status = solver.Solve(data.model)
        logging.info('Solution status: ' + solver.StatusName(status))
        if status not in {cp_model.FEASIBLE, cp_model.OPTIMAL}:
            return False
        self._log_costs(cost_data, solver.ObjectiveValue())

        result = dict()
        for o in objects:
            o_solution = {p: solver.BooleanValue(data.m[o, p]) for p in data.p}
            result[o] = next(p for p,mapped in o_solution.items() if mapped)
        return result
