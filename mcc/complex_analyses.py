"""
Description
-----------

Implements more sophisticated analysis engines.

:Authors:
    - Johannes Schlatow

"""
import logging
from mcc.framework import *
from mcc.taskmodel import *

from collections import OrderedDict
import itertools

from ortools.sat.python import cp_model

from pycpa import model as pycpa_model
from pycpa import options as pycpa_options
from pycpa import schedulers as pycpa_schedulers
from pycpa import analysis as pycpa_analysis
from pycpa import junctions as pycpa_junctions
from taskchain import model as tc_model

class CPAEngine(AnalysisEngine):

    def __init__(self, layer, complayer):
        acl = { layer        : {'reads' : {'mapping', 'activation'}},
                complayer    : {'reads' : {'priority'}}}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)

        self.complayer = complayer

    def batch_check(self, iterable):

        resources = dict()  # PfComponent -> tc_model.ResourceModel
        tasks     = dict()  # Node -> pycpa_model.Task
        revtasks  = dict()  # pycpa_model.Task -> Node
        threads   = dict()  # Component -> (tc_model.ExecutionContext, tc_model.SchedulingContext)
        threadmap = dict()  # Node -> Thread
        junctions = dict()

        taskid = 1
        for obj in iterable:
            task = obj.obj(self.layer)
            pfc = self.layer.get_param_value(self, 'mapping', obj)

            # create new resource model if needed
            if pfc not in resources:
                create = True
                for tmp in resources.keys():
                    if tmp.in_native_domain(pfc):
                        resources[pfc] = resources[tmp]
                        create = False
                        break

                if create:
                    resources[pfc] = tc_model.ResourceModel(pfc.name())

            # create pycpa_model.Task
            name = 't%d-%s' % (taskid, task.name)
            tasks[obj] = pycpa_model.Task(name, wcet=task.wcet, bcet=task.bcet)
            if task.expect_in == 'junction':
                jt = task.expect_in_args['junction_type']
                if jt == 'AND':
                    junctions[obj] = pycpa_model.Junction('j%d'%taskid, strategy=pycpa_junctions.ANDJoin())
                    resources[pfc].add_junction(junctions[obj])
                elif jt == 'OR':
                    junctions[obj] = pycpa_model.Junction('j%d'%taskid, strategy=pycpa_junctions.ORJoin())
                    resources[pfc].add_junction(junctions[obj])
                elif jt == 'MUX':
                    raise NotImplementedError

            taskid += 1
            revtasks[tasks[obj]] = obj
            resources[pfc].add_task(tasks[obj])

            comp = task.thread
            # create new execution and scheduling context if needed
            if comp not in threads:
                # create execution context
                ectx = tc_model.ExecutionContext('e-'+task.thread.obj(self.complayer).label())
                resources[pfc].add_execution_context(ectx)

                # get scheduling priority
                prio = self.complayer.get_param_value(self, 'priority', comp)

                # create scheduling context
                sctx = tc_model.SchedulingContext('s-'+task.thread.obj(self.complayer).label())
                if prio:
                    sctx.priority = prio
                resources[pfc].add_scheduling_context(sctx)

                threads[comp] = (ectx, sctx)

            threadmap[obj] = comp

        # create tasklinks
        roots  = set()
        leaves = set()
        for model in set(resources.values()):
            for pycpa_task in model.tasks:
                node = revtasks[pycpa_task]
                # remember root tasks
                if not set(self.layer.in_edges(node)):
                    roots.add(node)

                if node in junctions:
                    model.link_junction(junctions[node], pycpa_task)

                has_out = False
                for e in self.layer.out_edges(node):
                    has_out = True
                    if e.target not in junctions:
                        model.link_tasks(pycpa_task, tasks[e.target])
                    else:
                        model.connect_junction(pycpa_task, junctions[e.target])

                if not has_out:
                    leaves.add(node)


        # assign execution and scheduling contexts by tracing task graph
        visited = set()
        for root in roots:
            pfc = self.layer.get_param_value(self, 'mapping', root)

            # assign/store event model
            act = self.layer.get_param_value(self, 'activation', root)
            if isinstance(act, PJEventModel):
                tasks[root].in_event_model = pycpa_model.PJdEventModel(P=act.P, J=act.J)

            ectx, sctx = threads[threadmap[root]]

            logging.info("\n\nprocessing chain from %s" % tasks[root])

            # assign own scheduling context to root tasks
            resources[pfc].assign_scheduling_context(tasks[root],
                                                     sctx)

            # assign own execution context to root tasks
            resources[pfc].assign_execution_context(tasks[root],
                                                    ectx,
                                                    blocking=False)

            threadstack = []
            node = root
            next_nodes = deque()

            while node:
                logging.info("\nprocessing task %s" % tasks[node])

                if not set(self.layer.out_edges(node)):
                    # release our execution context
                    pfc = self.layer.get_param_value(self, 'mapping', node)
                    resources[pfc].assign_execution_context(tasks[node],
                                                            threads[threadmap[node]][0])


                # first follow rpc edges
                for e in (e for e in self.layer.out_edges(node) if e.edgetype() == 'call'):
                    assert e.target not in visited
                    next_nodes.append(e.target)
                    visited.add(e.target)

                    logging.info("processing edge %s -> %s" % (tasks[e.source],tasks[e.target]) )

                    # called task gets its scheduling context from top of stack
                    if threadstack:
                        sctx = threads[threadstack[0]][1]
                    else:
                        sctx = threads[threadmap[e.source]][1]
                    resources[pfc].assign_scheduling_context(tasks[e.target], sctx)

                    thread_target = threadmap[e.target]
                    thread_source = threadmap[e.source]

                    # if called task is already on the stack
                    logging.info('%s is in %s' % (thread_target, threadstack))
                    if thread_target in threadstack:
                        # this is a return call -> release ectx from current task
                        resources[pfc].assign_execution_context(tasks[e.source],
                                                                threads[thread_source][0],
                                                                blocking = False)

                        assert threadstack[-1] == thread_source, '%s != %s, for edge %s -> %s\n%s'  \
                             % (threadstack[-1], thread_source, e.source, e.target, threadstack)
                        threadstack.pop()
                    elif not threadstack:
                        resources[pfc].assign_execution_context(tasks[e.source],
                                                                threads[thread_source][0],
                                                                blocking = True)
                        if thread_source != thread_target:
                            threadstack.append(thread_source)
                        threadstack.append(thread_target)
                    else:
                        # this is a real call -> push ectx to stack
                        threadstack.append(thread_target)

                    # called task blocks all execution contexts on the stack
                    for th in threadstack:
                        resources[pfc].assign_execution_context(tasks[e.target],
                                                                threads[th][0],
                                                                blocking = True)

                for e in (e for e in self.layer.out_edges(node) if e.edgetype() == 'signal'):
                    if e.target in visited:
                        continue

                    logging.info("processing edge %s -> %s" % (tasks[e.source],tasks[e.target]) )

                    next_nodes.appendleft(e.target)
                    visited.add(e.target)

                    pfc = self.layer.get_param_value(self, 'mapping', e.target)
                    if e.edgetype() == 'signal':
                        # signalled tasks get their own scheduling context
                        resources[pfc].assign_scheduling_context(tasks[e.target],
                                                                 threads[threadmap[e.target]][1])
                        # next task releases its execution context
                        resources[pfc].assign_execution_context(tasks[e.target],
                                                                threads[threadmap[e.target]][0],
                                                                blocking = False)

                try:
                    node = next_nodes.pop()
                except:
                    node = None


        for model in set(resources.values()):
            model.check()

        # FIXME (future work) deal with mux and demux junctions

        # TODO create TaskchainResources, create taskchains
        
        # TODO find interrupt tasks and connect

        # TODO perform analysis

        # TODO define path for latency requirement (split at junctions)

        # TODO perform path analysis

        tc_model.ResourceModel.write_dot(set(resources.values()), '/tmp/taskgraph.dot')

        return False


class CPMappingEngine(AnalysisEngine):
    """ Assigns platform mappings using ortools' CP-sat solver """

    class ModelData():
        """ helper class for easier access to all the CP model data """
        def __init__(self, ae, layer, unmapped_objects):
            self.model = cp_model.CpModel()
            self.o = set(layer.nodes())
            #set of all platforms
            self.p = set()
            for o in self.o:
                self.p.update(layer.get_param_candidates(ae, 'mapping', o))

            #generate the variables which will contain the final solution
            self.m = dict()
            for o in self.o:
                o_vars = []
                for p in self.p:
                    self.m[o, p] = self.model.NewBoolVar('%s on %s' % (o, p))
                    o_vars.append(self.m[o, p])
                #each object should only be mapped once
                self.model.Add(1 == sum(o_vars))

            for predefined in self.o - set(unmapped_objects):
                platform = layer.get_param_value(ae, 'mapping', predefined)
                self.model.Add(1 == self.m[predefined, platform])

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
            for dep in self.layer.out_edges(o):
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
        data = self.ModelData(self, self.layer, objects)

        for o in objects:
            for p in candidates[o].symmetric_difference(data.p):
                data.model.Add(0 == data.m[o, p])
        for bad_combination in bad_combinations:
            bad_vars = [data.m[k] for k in zip(objects, bad_combination)]
            bad_values = len(bad_vars) * (1,)
            data.model.AddForbiddenAssignments(bad_vars, [bad_values])

        cost_expr, cost_var_data = self._gen_cost_data(data)
        data.model.Maximize(cost_expr)

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
