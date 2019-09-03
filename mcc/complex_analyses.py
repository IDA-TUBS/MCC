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
import itertools

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
        """
        Args:
            :param cost_priorities: Each list entry is higher prioritized than
                                    each of the subsequent entries. If an entry
                                    is a tuple, its elements are prioritized
                                    equally.
            :type cost_priorities: list of strings and tuples of strings
        """
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
        self._cost_funcs = {
                'comm': self._gen_communication_cost_data,
                'dep_comm': self._gen_dep_communication_cost_data,
                }
        if cost_priorities is None:
            cost_priorities = [('comm', 'dep_comm')]
        self.cost_priorities = []
        for cats in cost_priorities:
            normalized = cats if isinstance(cats, tuple) else (cats,)
            self.cost_priorities.append(normalized)

    def _gen_cost_data(self, data):
        """ return the data required for setting and evaluating an objective

        Multiple cost objectives are prioritized lexicographically. Thus, if
        the total objective is to be minimized, lower values of high-priority
        objectives are always preferred even if this leads to far greater
        values of the lower-prioritized objectives.

        Returns:
            The total expression and a dictionary with the seperated objective
            expressions and their upper bounds.
        """
        expr = 0
        var_data = OrderedDict()
        # The expression of each priority level is multiplied with a factor so
        # that the expressions of other levels do not interfere with it.
        step_size = 1
        for categories in reversed(self.cost_priorities):
            if len(var_data): #if not the lowest priority
                previous = next(reversed(var_data.values()))
                #guarantee growing step size even if the upper bound was <= 1
                step_size *= max(2, sum(previous['bounds']))

            assert isinstance(categories, tuple)
            exprs, ubs = zip(*[self._cost_funcs[c](data) for c in categories])

            expr += step_size * sum(exprs)
            var_data[categories] = {'exprs': exprs, 'bounds': ubs}
        return expr, dict(reversed(var_data.items())) # high priority first

    def _log_costs(self, cost_var_data, solver):
        for i, (categories, data) in enumerate(cost_var_data.items(), start=1):
            for cat, e, ub in zip(categories, data['exprs'], data['bounds']):
                msg = 'cost [%s] (priority: %d): %d/%d'
                logging.info(msg % (cat, i, solver.Value(e), ub))

    def _gen_communication_cost_data(self, data):
        """ directly connected objects on different sources will have cost 1 """
        expr = bound = 0
        for o in data.o:
            for dep in self.layer.graph.out_edges(o):
                if dep.target not in data.o:
                    continue

                bound += 1
                for p in data.p:
                    expr += data.AND(data.m[o, p].Not(), data.m[dep.target, p])
        return expr, bound

    def _gen_dep_communication_cost_data(self, data):
        """ deps that cannot be satisfied in the same domains will have cost 1
        """
        def _gen_dep_cost(o, deps):
            """ generate cost data for an object and a set of dependencies

            Returns:
                tuple with IntVar for the cost value and an upper bound
            """
            providers = [d.provider for d in deps if d.provider in data.o]
            p_combis = itertools.product(data.p, repeat=2)
            p_combis = [(a,b) for a,b in p_combis if not a.in_native_domain(b)]

            expr = 0
            for provider, (p1, p2) in itertools.product(providers, p_combis):
                expr += data.AND(data.m[o, p1], data.m[provider, p2])
            bound = len(providers)
            label = 'costs for dep candidate %s for object %s'
            var = data.model.NewIntVar(0, bound, label % (deps, o))
            data.model.Add(var == expr)
            return var, bound

        expr = bound = 0
        for o in data.o:
            cands = self.layer.get_param_candidates(self, 'dependencies', o)
            assert len(cands)
            cexpressions, cbounds = zip(*[_gen_dep_cost(o, c) for c in cands])

            obound = max(cbounds)
            best = data.model.NewIntVar(0, obound, 'best dep costs for %s' % o)
            data.model.AddMinEquality(best, cexpressions)

            expr += best
            bound += obound
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

        cost_expr, cost_var_data = self._gen_cost_data(data)
        data.model.Minimize(cost_expr)

        solver = cp_model.CpSolver()
        status = solver.Solve(data.model)
        logging.info('Solution status: ' + solver.StatusName(status))
        if status not in {cp_model.FEASIBLE, cp_model.OPTIMAL}:
            return False
        self._log_costs(cost_var_data, solver)

        result = dict()
        for o in objects:
            o_solution = {p: solver.BooleanValue(data.m[o, p]) for p in data.p}
            result[o] = next(p for p,mapped in o_solution.items() if mapped)
        return result
