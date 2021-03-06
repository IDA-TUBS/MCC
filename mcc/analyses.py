"""
Description
-----------

Implements analysis engines.

:Authors:
    - Johannes Schlatow
    - Edgard Schmidt

"""
import logging
from mcc.framework import *
from mcc.graph import *
from mcc import model
from mcc import parser
from mcc.taskmodel import *

import itertools
import copy
import random
from collections import deque

class WcetEngine(AnalysisEngine):
    def __init__(self, layer):
        """ Assigns WCETs to tasks (by copying from the Task object).
            (required for adaption of WCETs by AdaptationSimulation)
        """
        AnalysisEngine.__init__(self, layer, param='wcet')

        # store WCETs persistently across several adaptations
        self.wcets = dict()

    def update_wcet(self, taskname, wcet):
        self.wcets[taskname] = wcet

    def map(self, obj, candidates):
        assert not candidates

        task = obj.obj(self.layer)
        if task.name in self.wcets:
            return set([self.wcets[task.name]])
        else:
            return set([task.wcet])

    def assign(self, obj, candidates):
        assert len(candidates) == 1
        return list(candidates)[0]


class ActivationEngine(AnalysisEngine):
    def __init__(self, layer):
        """ Assigns activation pattern to root tasks and checks
            existence of activation pattern in taskgraph.
        """
        acl = { layer        : {'reads' : set(['mapping'])}}
        AnalysisEngine.__init__(self, layer, param='activation', acl=acl)

    def map(self, obj, candidates):
        assert not candidates

        result = set()

        # only assign activation pattern to root tasks
        if not set(self.layer.in_edges(obj)):
            task = obj.obj(self.layer)
            if task.expect_in == 'interrupt':
                # pragmatically assume its a nic task and there
                #  is only one other nic task in the system
                # FIXME if this does not hold anymore, we must have a look at the proxy
                pfc = self.layer.get_param_value(self, 'mapping', obj)
                for o in self.layer.nodes() - {obj}:
                    # find task who raises interrupt with same id
                    t = o.obj(self.layer)
                    if t.expect_out == 'interrupt' and \
                       t.expect_out_args['id'] == task.expect_in_args['id']:

                        # task must be in different domains
                        if not pfc.in_native_domain(
                                self.layer.get_param_value(self, 'mapping', o)):
                            result.add(InEventModel(t.expect_out_args['id']))
            elif task.activation_period != 0:
                result.add(PJEventModel(P=task.activation_period,
                                        J=task.activation_jitter))
            else:
                logging.error("Root task %s has no activation period" % obj)

            if len(result) > 1:
                logging.error("Cannot unambiguously connect interrupts %s" % \
                              task.expect_in_args['id'])

        elif not set(self.layer.out_edges(obj)):
            task = obj.obj(self.layer)
            if task.expect_out == 'interrupt':
                pfc = self.layer.get_param_value(self, 'mapping', obj)
                for o in self.layer.nodes() - {obj}:
                    # find task who raises interrupt with same id
                    t = o.obj(self.layer)
                    if t.expect_in == 'interrupt' and \
                       t.expect_in_args['id'] == task.expect_out_args['id']:

                        # task must be in different domains
                        if not pfc.in_native_domain(
                                self.layer.get_param_value(self, 'mapping', o)):
                            result.add(OutEventModel(t.expect_in_args['id']))
            else:
                result.add(None)


            if len(result) > 1:
                logging.error("Cannot unambiguously connect interrupts %s" % \
                              task.expect_out_args['id'])


        else:
            return {None}

        return result

    def assign(self, obj, candidates):
        return random.choice(list(candidates))


class PriorityEngine(AnalysisEngine):
    def __init__(self, layer, taskgraph, platform):
        """ Simple implementation for assigning components to scheduling priorities.
        """
        acl = { layer        : {'reads' : {'mapping'}},
                taskgraph    : {'reads' : {'activation'}}}
        AnalysisEngine.__init__(self, layer, param='priority', acl=acl)

        self.taskgraph = taskgraph
        self.platform  = platform

    def batch_map(self, data):

        # get priority range from platform component
        partitions = dict()
        for pfc in self.platform.platform_components():
            partitions[pfc] = {'prios'    : pfc.priorities(),
                               'complist' : []
                              }

        # at the moment, we only want a single but deterministic assignment
        #    rationale: there are lots of heuristics and even
        #               optimal priority-assignment schemes.
        #               We expect that there will be such a scheme for
        #               task chains as well. Until now, we just apply something
        #               similar to RMS.
        #    note: if we want to implement audsleys algorithm, we must assign
        #          priorities after the task graph is known

        periods = dict()
        isr_period = 1
        # iterate nodes deterministically, as isr_periods are assigned by order of appearance
        for task in sorted(self.taskgraph.nodes(), key=lambda x: x.obj(self.taskgraph).label()):
            act = self.taskgraph.get_param_value(self, 'activation', task)
            if act and (act.wrapsinstance(PJEventModel) or act.wrapsinstance(InEventModel)):
                if act.wrapsinstance(PJEventModel):
                    current_period = act.P
                else:
                    # highest priority for interrupts
                    current_period = isr_period
                    isr_period += 1

                if current_period in periods:
                    # make sure that periods are distinct
                    logging.error('Periods are not distinct. Period %d occurs multiple times.' \
                            % current_period)
                    raise NotImplementedError
                else:
                    periods[current_period] = [task]
                    t = task
                    next_tasks = deque()
                    # trace task graph (not following calls)
                    while t:
                        tmp = set()
                        # collect activated tasks in tmp
                        for e in self.taskgraph.out_edges(t):
                            tmp.add(e.target)
                        # deterministically iterate through tasks
                        for t in sorted(tmp, key=lambda x: x.obj(self.taskgraph).label()):
                            next_tasks.append(t)
                            periods[current_period].append(t)

                        try:
                            t = next_tasks.popleft()
                        except:
                            t = None

        # hierarchically sort periods
        tasklist = []
        for p in sorted(periods.keys()):
            for t in periods[p]:
                tasklist.append(t)

        # sort components by first occurence of a task in tasklist
        visisted_comps = set()
        for t in tasklist:
            comps = self.taskgraph.associated_objects(self.layer.name, t)
            if len(comps) > 1:
                logging.error("Task %d is associated to multiple component. " \
                              "Priority assignment won't be deterministic." % t)
            for c in comps:
                if c not in visisted_comps:
                    pfc = self.layer.get_param_value(self, 'mapping', c)
                    partitions[pfc]['complist'].append(c)
                    visisted_comps.add(c)

        # initialise result object with lowest priority
        result = dict()
        for c in data.keys():
            if self.layer.associated_objects(self.taskgraph.name, c):
                result[c] = set()
            else:
                result[c] = set([None])

        # map to priority range
        for pfc, data in partitions.items():
            prios    = sorted(data['prios'])
            complist = data['complist']

            # get the i-th priority for component i
            #   unless we have no more prios left
            #   then take the lowest priority
            for i in range(len(complist)):
                j = min(i, len(prios)-1)
                result[complist[i]] = {prios[j]}

        return result

    def batch_assign(self, data, objects, bad_combinations):
        # at the moment, we only want a single but deterministic assignment
        if bad_combinations:
            return False

        result = dict()
        for o, cands in data.items():
            result[o] = list(cands)[0]

        return result


class AffinityEngine(AnalysisEngine):
    def __init__(self, layer):
        """ Simple implementation for assigning components to cores.
        """
        acl = { layer        : {'reads' : set(['mapping'])}}
        AnalysisEngine.__init__(self, layer, param='affinity', acl=acl)

    def map(self, obj, candidates):
        assert candidates is None
        assert not isinstance(obj, Edge)

        # get platform component
        pfc = self.layer.get_param_value(self, 'mapping', obj)
        inst = obj.obj(self.layer)

        available = set(range(pfc.smp_cores()))

        required = inst.component.affinities()
        if required:
            return available & required

        return available

    def assign(self, obj, candidates):
        return random.choice(list(candidates))


class ReliabilityEngine(AnalysisEngine):
    def __init__(self, layer, layers, constrmodel):
        """ Dummy implementation for excluding task graphs that
            do not achieve a certain reliability.
        """
        acl = { layer        : {'reads' : set(['mapping'])}}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)

        self.constrmodel  = constrmodel
        self.layers       = layers

    def _get_objects_on_layer(self, source, sink, target_layer):
        objects = set()
        for path in self.layers[0].graph.paths(source, sink, undirected=True):
            last = None
            for n in path:
                # add node
                objects.add(n)
                # add edge to last node
                if last is not None:
                    for e in self.layers[0].in_edges(n):
                        if e.source == last:
                            objects.add(e)
                            break
                last = n

        for l1,l2 in zip(self.layers, self.layers[1:]):
            if l1 == target_layer:
                break
            next_objects = set()
            for obj in objects:
                next_objects.update(l1.associated_objects(l2.name, obj))
            objects = next_objects

        return objects

    def batch_check(self, iterable):

        objects = set()

        # iterate constraints from constrmodel
        for constraint in self.constrmodel.reliability_constraints():
            if constraint['value'] != 'high':
                logging.info("Ignoring reliability constraint %s" % constraint)
                continue

            objects.update(self._get_objects_on_layer(constraint['source'], constraint['sink'], self.layer))

        result = True
        for obj in objects:
            if isinstance(obj, Edge):
                continue
            mapping = self.layer.get_param_value(self, 'mapping', obj)
            if mapping.name() in self.constrmodel.unreliable_pf_components():
                result = False

        return result


class TasksCoreEngine(AnalysisEngine):
    def __init__(self, layer):
        """ Gets task objects (core) from repo
        """
        acl = { layer        : {'reads' : set(['source-service', 'target-service'])}}
        AnalysisEngine.__init__(self, layer, param='coretasks', acl=acl)

    def _connect_junctions(self, objects):
        # connect junctions
        for task in [t for t in objects if isinstance(t, Task)]:
            if task.expect_out == 'junction':
                found = False
                for junction in objects:
                    if isinstance(junction, Tasklink):
                        continue

                    if junction.expect_in == 'junction' and \
                       junction.expect_in_args['junction_name'] == task.expect_out_args['name']:

                        objects.add(Tasklink(task, junction, linktype='signal'))
                        found = True
#                        task.set_placeholder_out(None)
                        break

                assert found, 'Not found: Junction "%s" for task %s' % (task.expect_out_args['name'], task)

        return objects

    def map(self, obj, candidates):
        """ Pulls taskgraph objects from repository
        """
        assert candidates is None

        component = obj.obj(self.layer)
        if isinstance(component, model.Instance):
            component = component.component

        # get time-triggered taskgraph
        try:
            objects = component.taskgraph_objects(obj)
        except Exception as e:
           logging.error("Could not get taskgraph objects for %s" % obj) 
           raise e

        # for each incoming connection (see if incoming signal exists)
        signals = set()
        for e in self.layer.in_edges(obj):
            serv = self.layer.get_param_value(self, 'target-service', e)
            signals.add(serv.ref())

        # for each outgoing connection (see if incoming signal exists)
        for e in self.layer.out_edges(obj):
            serv = self.layer.get_param_value(self, 'source-service', e)
            signals.add(serv.ref())

        for sig in signals - {None}:
            objects.update(component.taskgraph_objects(obj, signal=sig))

        objects = self._connect_junctions(objects)

        return set([frozenset(objects)])

    def assign(self, obj, candidates):
        """ Selects single candidate
        """
        assert len(candidates) == 1
        return list(candidates)[0]


class TasksRPCEngine(AnalysisEngine):
    def __init__(self, layer):
        """ Gets task objects (RPC) from repo
        """
        acl = { layer        : {'reads' : set(['coretasks', 'source-service', 'target-service'])}}
        AnalysisEngine.__init__(self, layer, param='rpctasks', acl=acl)

    def _connect_junctions(self, objects, junction_objects):
        # connect junctions
        for task in [t for t in objects if isinstance(t, Task)]:
            if task.expect_out == 'junction':
                found = False
                for junction in junction_objects:
                    if isinstance(junction, Tasklink):
                        continue

                    if junction.expect_in == 'junction' and \
                       junction.expect_in_args['junction_name'] == task.expect_out_args['name']:

                        objects.add(Tasklink(task, junction, linktype='signal'))
#                        task.set_placeholder_out(None)
                        found = True
                        break

                assert found is None, 'Not found: Junction "%s" for task %s' % (task.expect_out_args['name'], task)

        return objects

    def _connect_rpc(self, obj, objects, call):
        assert call in objects

        # find return task
        ret = None
        for task in (t for t in objects if isinstance(t, Task)):
            if task.expect_in == 'server' and task.expect_in_args['callertask'] == call:
                ret = task
                break

        assert ret is not None, 'Could not find return task for %s' % call.expect_out_args

        # find server component 
        to_ref = call.expect_out_args['to_ref']
        method = call.expect_out_args['method']
        server = None
        for e in self.layer.out_edges(obj):
            src = self.layer.get_param_value(self, 'source-service', e)
            if src.ref() == to_ref:
                server = e.target
                server_ref = self.layer.get_param_value(self, 'target-service', e).ref()
                break
        assert(server is not None)

        # get rpcobjects
        server_obj = server.obj(self.layer)
        if isinstance(server_obj, model.Instance):
            rpc_objects = server_obj.component.taskgraph_objects(server, rpc=server_ref, method=method)
        else:
            rpc_objects = server_obj.taskgraph_objects(server, rpc=server_ref, method=method)

        assert rpc_objects, 'No task objects found for RPC (to_ref=%s, method=%s) %s' % (server_ref, method)

        # check rpcobjects for any calls
        rpcs = set()
        for task in (t for t in rpc_objects if isinstance(t, Task)):
            if task.expect_out == 'server':
                rpcs.add(task)

        for rpc in rpcs:
            rpc_objects = self._connect_rpc(server, rpc_objects, rpc)

        # connect junction placeholders in rpc_objects
        self._connect_junctions(rpc_objects, self.layer.get_param_value(self, 'coretasks', server))

        # connect rpcobjects into objects
        firsttask = None
        lasttask  = None
        for task in (t for t in rpc_objects if isinstance(t, Task)):
            if task.expect_in == 'client':
                firsttask = task
            if task.expect_out == 'client':
                lasttask = task

        assert firsttask is not None
        assert lasttask  is not None

        objects.update(rpc_objects)
        objects.add(Tasklink(call, firsttask))
        objects.add(Tasklink(lasttask, ret))
#        call.set_placeholder_out(None)
#        ret.set_placeholder_in(None)
#        firsttask.set_placeholder_in(None)
#        lasttask.set_placeholder_out(None)

        return objects

    def map(self, obj, candidates):
        """ Pulls taskgraph objects from repository
        """
        assert candidates is None

        objects = set(self.layer.get_param_value(self, 'coretasks', obj))

        rpcs = set()
        for task in (t for t in objects if isinstance(t, Task)):
            if task.expect_out == 'server':
                rpcs.add(task)
        for rpc in rpcs:
            objects = self._connect_rpc(obj, objects, rpc)

        return set([frozenset(objects)])

    def assign(self, obj, candidates):
        """ Selects single candidate
        """
        assert len(candidates) == 1
        return list(candidates)[0]

class TaskgraphEngine(AnalysisEngine):
    def __init__(self, layer, target_layer):
        """ Transforms a component graph into a task graph.
        """
        acl = { layer        : {'reads' : set(['mapping', 'rpctasks', 'source-service', 'target-service'])},
                target_layer : {'writes' : set(['mapping'])}}
        AnalysisEngine.__init__(self, layer, param='tasks', acl=acl)
        self.target_layer = target_layer

    def _edge(self, link):
        return Tasklink(self._node(link.source), self._node(link.target), link.linktype)

    def _node(self, task):
        if not hasattr(task, 'node'):
            task.node = Layer.Node(task)

        return task.node

    def _graph_objects(self, obj, objects):
        result = set()

        for o in objects:
            if isinstance(o, Task):
                result.add(GraphObj(self._node(o), params={'mapping' : self.layer.get_param_value(self, 'mapping', obj)}))
            else:
                result.add(self._edge(o))

        return result

    def _remove_unconnected_junctions(self, objects):
        # remove unconnected junctions
        tasks = set([t for t in objects if isinstance(t, Task)])
        links = (t for t in objects if isinstance(t, Tasklink))
        # first: aggregate seeds (junctions without any input)
        unconnected = set()
        for task in tasks:
            if task.expect_in == 'junction':
                connected = False
                for link in links:
                    if link.target == task:
                        connected = True
                if not connected:
                    unconnected.add(task)
        # second: iteratively add subsequent tasks to unconnected set
        old = 0
        while old != len(unconnected):
            old = len(unconnected)
            for task in tasks - unconnected:
                connected = False
                for link in (l for l in links if l.target == task):
                    if link.source not in unconnected:
                        connected = True

                if not connected:
                    unconnected.add(task)

        # now remove tasklinks and tasks
        for link in [l for l in objects if isinstance(l, Tasklink)]:
            if link.source in unconnected or link.target in unconnected:
                objects.remove(link)

        return objects - unconnected

    def map(self, obj, candidates):
        assert candidates is None

        if isinstance(obj, Edge):
            # add Tasklinks
            source_tasks = self.layer.get_param_value(self, 'tasks', obj.source)
            target_tasks = self.layer.get_param_value(self, 'tasks', obj.target)
            source_ref   = self.layer.get_param_value(self, 'source-service', obj).ref()
            target_ref   = self.layer.get_param_value(self, 'target-service', obj).ref()

            source_sender = None
            source_receiver = None
            # find sender or receiver in source_tasks
            for task in (t for t in source_tasks if isinstance(t, Task)):
                if task.expect_out == 'receiver' and \
                   task.expect_out_args['to_ref'] == source_ref:
                    source_sender = task
                if task.expect_in == 'sender' and \
                   task.expect_in_args['from_ref'] == source_ref:
                    source_receiver = task

            # find sender or receiver in target_tasks
            target_sender = None
            target_receiver = None
            for task in (t for t in target_tasks if isinstance(t, Task)):
                if task.expect_out == 'receiver' and \
                   task.expect_out_args['to_ref'] == target_ref:
                    target_sender = task
                if task.expect_in == 'sender' and \
                   task.expect_in_args['from_ref'] == target_ref:
                    target_receiver = task

            objects = set()
            if source_sender is not None:
                assert target_receiver is not None, "Receiver task on %s with ref %s is missing" % (obj.target, target_ref)
                objects.add(Tasklink(source_sender, target_receiver, linktype='signal'))

            if target_sender is not None:
                assert source_receiver is not None, "Receiver task on %s with ref %s is missing" % (obj.source, source_ref)
                objects.add(Tasklink(target_sender, source_receiver, linktype='signal'))

        else:
            objects = self.layer.get_param_value(self, 'rpctasks', obj)
            objects = self._remove_unconnected_junctions(set(objects))

        return set([frozenset(objects)])

    def assign(self, obj, candidates):
        """ Selects single candidate
        """
        assert len(candidates) == 1
        return list(candidates)[0]

    def check(self, obj):
        """ Check task graph consistency 
        """
        taskobjects = self.layer.get_param_value(self, self.param, obj)

        component = obj.obj(self.layer)

        # component may have no tasks, which is an indicator for a superfluous component
        # but not necessarily an error
        if not taskobjects:
            logging.warning("No tasks found for component %s" % component)

        tasks = (t for t in taskobjects if isinstance(t, Task))
        links = [t for t in taskobjects if isinstance(t, Tasklink)]

        # check for unconnected tasks
        for t in tasks:
#            # There must not be a client/server placeholder in the taskgraph
#            if t.expect_in == 'client' or t.expect_in == 'server':
#                logging.error("Client/Server placeholder (in) present in taskgraph for component %s" % component)
#                return False

            # resulting taskgraph may still contain interrupt or sender placeholders,
            #  junction placeholders must at least have one connection though
            if t.expect_in == 'junction':
                connections = 0
                for l in links:
                    if l.target == t:
                        connections += 1

                if connections == 0:
                    logging.error("Junction placeholder (in) present in taskgraph for component %s" % component)
                    assert False, "This should never happen unless there is a problem in the timing model"
                    return False
                elif connections > 1 and t.expect_in != 'junction':
                    logging.error("Multiple connections to junction taskgraph for component %s" % component)
                    return False

#            if t.expect_out == 'server':
#                logging.error("Server placeholder (out) present in taskgraph for component %s" % component)
#                return False

        return True

    def transform(self, obj, target_layer):
        objects = self.layer.get_param_value(self, self.param, obj)
        return self._graph_objects(obj, objects)

    def source_types(self):
        return tuple({model.Instance, parser.Repository.Component, Edge})

    def target_types(self):
        return tuple({Task})

class NetworkEngine(AnalysisEngine):
    def __init__(self, layer, max_byte_s=10*1024*1024):
        acl = { layer        : {'reads' : set(['mapping','component','service','connections']) }}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)
        self.max_byte_s = max_byte_s

    def _find_sink(self, obj, visited):
        # find 
        if not self.layer.isset_param_value(self, 'mapping', obj):
            return None

        pfc = self.layer.get_param_value(self, 'mapping', obj)
        comp = self.layer.get_param_value(self, 'component', obj)

        # trace ROM services
        for edge in self.layer.in_edges(obj):
            if edge.source in visited:
                continue

            if self.layer.isset_param_value(self, 'mapping', edge.source):
                if self.layer.get_param_value(self, 'mapping', edge.source) != pfc:
                    continue

            for con in self.layer.get_param_value(self, 'connections', edge):
                service = con.source_service
                if service.name() == 'ROM':
                    provided = comp.provides_services(name=con.target_service.name(),
                                                      ref =con.target_service.ref())

                    assert(len(provided) == 1)

                    size, msec, pksz = provided[0].out_traffic()
                    if size is None:
                        sink = self._find_sink(edge.source, visited + {obj})
                        if sink is not None:
                            return sink

        # trace Network services
        for edge in self.layer.out_edges(obj):
            service = self.layer.get_param_value(self, 'service', edge)
            if service.function == 'Network':
                return edge.target

        return None

    def batch_check(self, iterable):
        self.state = dict()

        for obj in iterable:
            self._check(obj)

        for (pfc, out_traffic) in self.state.items():
            pfc.set_state('out_traffic', int(out_traffic))

            if out_traffic > self.max_byte_s:
                # FIXME we should return a set of
                #       all obj and mapping params on this pfc
                return False

        return True

    def _check(self, obj):
        if not self.layer.isset_param_value(self, 'mapping', obj):
            # skip unmapped components (proxies)
            return

        pfc = self.layer.get_param_value(self, 'mapping', obj)
        if pfc not in self.state:
            self.state[pfc] = 0

        # only evaluate and trace provided ROM services that have an out-traffic node
        comp = self.layer.get_param_value(self, 'component', obj)
        for edge in self.layer.in_edges(obj):
            if self.layer.isset_param_value(self, 'mapping', edge.source):
                other_pfc = self.layer.get_param_value(self, 'mapping', edge.source)
                if pfc != other_pfc:
                    continue

            for con in self.layer.get_param_value(self, 'connections', edge):
                service = con.source_service
                if service.name() == 'ROM':
                    provided = comp.provides_services(name=con.target_service.name(),
                                                      ref =con.target_service.ref())

                    assert(len(provided) == 1)

                    size, msec, pksz = provided[0].out_traffic()
                    if size is None:
                        continue

                    sink = self._find_sink(edge.source, {obj})
                    if sink is None:
                        continue

                    self.state[pfc] += size / (float(msec)/1000)
                    break


class QuantumEngine(AnalysisEngine):
    def __init__(self, layer, name):
        acl = { layer        : {'reads' : set(['mapping']) }}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)
        self.name = name

    def batch_check(self, iterable):
        self.state = dict()

        for obj in iterable:
            self._check(obj)

        for (pfc, remaining) in self.state.items():
            if remaining < 0:
                logging.error("Subsystem %s exceeds its %s (%d)." % (pfc, self.name,
                                                                     pfc.quantum(self.name)))
                return False

            pfc.set_state('%s-remaining' % self.name, remaining)

        return True

    def _check(self, obj):
        pfc = self.layer.get_param_value(self, 'mapping', obj)
        if pfc not in self.state:
            self.state[pfc] = pfc.quantum(self.name)

        self.state[pfc] -= obj.obj(self.layer).component.requires_quantum(self.name)


class StaticEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='mapping')

    def map(self, obj, candidates):
        assert candidates is not None

        exclude = set()
        if len(candidates) > 1:
            for o in candidates:
                if o.static():
                    exclude.add(o)

            candidates -= exclude

        if len(candidates) > 1:
            logging.warning("Still cannot inherit mapping unambiguously.")
        if exclude:
            logging.info("Mapping was reduced by excluding static subsystems. Candidates left for %s: %s" \
                            % (obj.obj(self.layer), candidates))

        return candidates

class CoprocEngine(AnalysisEngine):
    def __init__(self, layer, platform, source_param):
        acl = { layer        : {'reads' : {source_param}}}
        AnalysisEngine.__init__(self, layer, param='mapping', acl=acl)

        self.platform = platform
        self.source_param = source_param

    def map(self, obj, candidates):
        assert candidates is None

        cur_pfc = self.layer.get_param_value(self, self.source_param, obj)

        coprocs = set()
        for pfc in self.platform.platform_components():
            if pfc.coproc() and cur_pfc.in_native_domain(pfc):
                coprocs.add(pfc)

        for pfc in coprocs:
            if pfc.match_specs(obj.obj(self.layer).component.requires_specs()):
                return {pfc}

        return {cur_pfc}

    def assign(self, obj, candidates):
        return random.choice(list(candidates))


class FunctionEngine(AnalysisEngine):
    class Dependency:
        def __init__(self, function, provider):
            self.function = function
            self.provider = provider

        def __repr__(self):
            return "depends on %s from %s" % (self.function, self.provider)

#        def __eq__(self, o):
#            return self.function == o.function and self.provider == o.provider
#
#        def __hash__(self):
#            return hash((self.function, self.provider))

    def __init__(self, layer, target_layer, repo):
        acl = { layer        : {'reads' : {'mapping', 'service'}},
                target_layer : {'writes' : {'mapping', 'service'}}}
        AnalysisEngine.__init__(self, layer, param='dependencies', acl=acl)
        self.repo = repo
        self.target_layer = target_layer

    def _required_functions(self, obj):
        # return required and unsatisfied function dependencies of 'obj'
        result = set()
        for dep in obj.obj(self.layer).dependencies('function'):
            depfunc = dep['function']
            # edge exists?
            satisfied = False
            for e in self.layer.out_edges(obj):
                sc = self.layer.get_param_value(self, 'service', e)
                if sc.function == depfunc:
                    satisfied = True

            if not satisfied:
                result.add(depfunc)

        return result

    def _provided_functions(self, obj):
        comp = obj.obj(self.layer)
        # return functions provided by 'obj'
        funcs = copy.copy(comp.functions())
        if hasattr(comp, 'query'):
            for provider in self.repo.find_components_by_type(comp.query(), comp.type()):
                funcs.update(provider.functions())

        return funcs

    def _candidate_set(self, dependencies):
        # convert dependencies dict into candidate set
        result = set()

        # we simply create all permuations
        for cand in itertools.product(*dependencies.values()):
            result.add(frozenset(cand))

        return result

    def _calculate_costs(self, from_pfc, candidate):
        costs = 0
        for cand in candidate:
            pfc = self.layer.get_param_value(self, 'mapping', cand.provider)

            if not from_pfc.in_native_domain(pfc):
                costs += 1

        return costs

    def map(self, obj, candidates):
        # aggregate dependencies
        functions = self._required_functions(obj)
        if not functions:
            return {frozenset()}

        dependencies = dict()
        for f in functions:
            # find function provider(s)
            dependencies[f] = set()
            for node in self.layer.nodes():
                if node is obj:
                    continue

                if f in self._provided_functions(node):
                    dependencies[f].add(self.Dependency(f, node))

        return self._candidate_set(dependencies)

    def assign(self, obj, candidates):
        pfc = self.layer.get_param_value(self, 'mapping', obj)

        if len(candidates) == 1:
            return list(candidates)[0]

        best      = None
        for cand in candidates:
            costs = self._calculate_costs(pfc, cand)
            if best is None:
                min_costs = costs
                best      = [cand]
            elif costs < min_costs:
                min_costs = costs
                best      = [cand]
            elif costs == min_costs:
                best.append(cand)

        assert best is not None
        return random.choice(best)

    def transform(self, obj, target_layer):
        assert not isinstance(obj, Edge)

        graph_objs = set()
        graph_objs.add(GraphObj(obj, params={'mapping' : self.layer.get_param_value(self, 'mapping', obj)}))

        dependencies = self.layer.get_param_value(self, self.param, obj)
        for dep in dependencies:
            graph_objs.add(GraphObj(Edge(obj, dep.provider),
                                    params={'service' : model.ServiceConstraints(function=dep.function)}))

        return graph_objs

    def target_types(self):
        # target layer has the same types as source layer
        return self.layer.node_types()


class MappingEngine(AnalysisEngine):
    def __init__(self, layer, repo, pf_model, cost_sensitive=True):
        acl = { layer : { 'reads' : set(['dependencies']) } }
        AnalysisEngine.__init__(self, layer, param='mapping', acl=acl)
        self.pf_model = pf_model
        self.repo = repo
        self.cost_sensitive = cost_sensitive

    def _calculate_costs(self, combination):
        cost = 0

        total_combi = dict(combination)
        for n in set(self.layer.nodes()).difference(combination):
            total_combi[n] = self.layer.get_param_value(self, 'mapping', n)

        for obj in total_combi.keys():

            # directly connected objects on different sources will have cost 1
            for dep in self.layer.out_edges(obj):
                if total_combi[dep.target] != total_combi[obj]:
                    cost += 1

            # dependencies that cannot be satisfied in the same domains will also have cost 1
            resolutions = self.layer.get_param_candidates(self, 'dependencies', obj)
            best_local_cost = max(map(lambda x: len(x.copy()), resolutions), default=0)
            for resolution in resolutions:
                local_cost = 0
                for dep in resolution:
                    if not total_combi[obj].in_native_domain(total_combi[dep.provider]):
                        local_cost += 1

                if local_cost < best_local_cost:
                    best_local_cost = local_cost

            cost += best_local_cost

        return cost

    def map(self, obj, candidates):
        if candidates is not None and candidates:
            return candidates

        assert not isinstance(obj, Edge)

        child = obj.obj(self.layer)

        components = self.repo.find_components_by_type(child.query(), child.type())

        if not components:
            logging.error("Cannot find referenced child %s '%s'." % (child.type(), child.query()))
            return set()

        pf_components = self.pf_model.platform_graph.nodes()
        static = set([pfc for pfc in pf_components if pfc.static()])
        pf_components = pf_components - static

        candidates = set()

        # iterate components and aggregate possible platform components
        for c in components:
            for pfc in pf_components:
                if pfc.match_specs(c.requires_specs()) and not pfc.coproc():
                    candidates.add(pfc)

        return candidates

    def assign(self, obj, candidates):
        return random.choice(list(candidates))

    def batch_assign(self, data, objects, bad_combinations):
        sets   = list()
        if objects is None:
            assert not bad_combinations
            objects = data.keys()

        for obj in objects:
            sets.append(data[obj])

        best_costs        = 0
        best_combinations = None
        for combination in itertools.product(*sets):
            if combination not in bad_combinations:
                result = dict(zip(objects, combination))
                if not self.cost_sensitive:
                    return result

                if best_combinations is None:
                    best_combinations = [result]
                    best_costs = self._calculate_costs(result)
                else:
                    costs = self._calculate_costs(result)
                    if costs < best_costs:
                        best_costs = costs
                        best_combinations = [result]
                    elif costs == best_costs:
                        best_combinations.append(result)

        if best_combinations is not None:
            return random.choice(best_combinations)

        logging.error("Mapping candidates exhausted: %s\n%s" % (objects, bad_combinations))
        return False

    def check(self, obj):
        """ Checks whether a platform mapping is assigned to all nodes.
        """
        assert(not isinstance(obj, Edge))

        okay = self.layer.get_param_value(self, 'mapping', obj) is not None
        if not okay:
            logging.error("Node '%s' is not mapped to anything.", obj)

        return okay

    def batch_check(self, iterable):
        """ Checks whether a platform mapping is assigned to all nodes.
        """
        for obj in iterable:
            assert(not isinstance(obj, Edge))

            okay = self.layer.get_param_value(self, 'mapping', obj) is not None
            if not okay:
                logging.error("Node '%s' is not mapped to anything.", obj)
                return False

        return True

class DependencyEngine(AnalysisEngine):
    def __init__(self, layer):
        acl = { layer : { 'reads' : set(['component']) } }
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)

    def _find_provider_recursive(self, node, function):
        for con in self.layer.out_edges(node):
            comp2 = self.layer.get_param_value(self, 'component', con.target)
            if function in comp2.functions():
                return True
            elif comp2.type() == 'proxy':
                if self._find_provider_recursive(con.target, function):
                    return True

        return False

    def check(self, obj):
        """ Checks whether all functional dependencies are satisfied by the selected component.
        """
        assert(not isinstance(obj, Edge))

        comp = self.layer.get_param_value(self, 'component', obj)

        # iterate function dependencies
        for f in comp.requires_functions():
            # find function among connected nodes
            if not self._find_provider_recursive(obj, f):
                logging.error("Cannot satisfy function dependency '%s' from component '%s'." % (f, comp))
                return False

        return True

class ComponentDependencyEngine(AnalysisEngine):
    def __init__(self, layer):
        acl = { layer : { 'reads' : set(['mapping', 'source-service']) } }
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)

    def check(self, obj):
        """ Checks that 
            a) all service requirements are satisfied once and (nodes)
            b) that service connections are local (edges).
        """
        if isinstance(obj, Edge):
            source_mapping = self.layer.get_param_value(self, 'mapping', obj.source)
            target_mapping = self.layer.get_param_value(self, 'mapping', obj.target)
            if not source_mapping.in_native_domain(target_mapping):
                # logging.error("Service connection '%s' from component '%s' to '%s' crosses platform components." % (s, obj, comp2))
                return False
            else:
                return True
        else:
            # iterate function dependencies
            for s in obj.obj(self.layer).requires_services():
                # find provider among connected nodes
                found = 0
                for con in self.layer.out_edges(obj):
                    src_serv = self.layer.get_param_value(self, 'source-service', con)
                    assert(src_serv is not None)
                    if s == src_serv:
                        found += 1

                if found == 0:
                    logging.error("Service dependency '%s' from component '%s' is not satisfied." % (s, obj))
                    return False
                if found > 1:
                    logging.error("Service dependency '%s' from component '%s' is ambiguously satisfied." % (s, obj))
                    return False

            return True

class ServiceEngine(AnalysisEngine):
    class Connection:
        def __init__(self, source_service, target_service):
            self.source_service = source_service
            self.target_service = target_service

        def __repr__(self):
            return '%s to %s' % (self.source_service, self.target_service)

    def __init__(self, layer, target_layer):
        acl = { layer        : { 'reads'  : set(['service', 'pattern', 'component']) },
                target_layer : { 'writes' : set(['source-service', 'target-service'])}}
        AnalysisEngine.__init__(self, layer, param='connections', acl=acl)
        self.target_layer = target_layer

    def _get_ports(self, obj):
        constraints = self.layer.get_param_value(self, 'service', obj)

        source_comp = self.layer.get_param_value(self, 'component', obj.source)
        target_comp = self.layer.get_param_value(self, 'component', obj.target)

        if constraints is None:
            logging.error('%s -> %s' % (source_comp, target_comp))
        assert(constraints is not None)

        source_ports = source_comp.requires_services()
        target_ports = target_comp.provides_services(function=constraints.function)

        if constraints.name is not None:
            source_ports = [p for p in source_ports if p.name() == constraints.name]
            target_ports = [p for p in target_ports if p.name() == constraints.name]

        if constraints.to_ref is not None:
            target_ports = [p for p in target_ports if p.ref() == constraints.to_ref]

        if constraints.from_ref is not None:
            source_ports = [p for p in source_ports if p.ref() == constraints.from_ref]

        if constraints.function is not None:
            source_ports = [p for p in source_ports if p.function() is None or p.function() == constraints.function]

        # remark: we do not check the function provision as this is/should be checked by a functional dependency engine before
        #         otherwise, if the function is not implemented by the target comp,
        #                    it should have never been selected in the first place

        return source_ports, target_ports

    def check(self, obj):
        """ Check ServiceConstraints object for compatibility with connected provider
        """
        assert(isinstance(obj, Edge))
        source_ports, target_ports = self._get_ports(obj)

        constraints = self.layer.get_param_value(self, 'service', obj)
        source_comp = self.layer.get_param_value(self, 'component', obj.source)
        target_comp = self.layer.get_param_value(self, 'component', obj.target)

        if len(source_ports) > 1:
            logging.warning("Service requirement %s by %s requires multiple connections: %s" % (source_comp, constraints, source_ports))

        if len(target_ports) > 1:
            logging.warning("Service provision is under constrained for %s by %s: %s" % (target_comp, constraints, target_ports))

        if not source_ports:
            logging.error("Service requirement is over constrained for %s by %s" % ( source_comp, constraints))

        if not target_ports:
            logging.error("Service provision is over constrained for %s by %s" % ( target_comp, constraints))

        return source_ports and target_ports

    def map(self, obj, candidates):
        assert(isinstance(obj, Edge))
        source_ports, target_ports = self._get_ports(obj)

        candidates = set()

        # there may be multiple source ports, i.e. multiple requirements connected to the same target
        for src in source_ports:
            if src.label():
                for trg in target_ports:
                    if not trg.label() or trg.label() == src.label():
                        candidates.add(self.Connection(src, trg))
            else:
                candidates.add(self.Connection(src, target_ports[0]))

        return set([frozenset(candidates)])

    def assign(self, obj, candidates):
        assert(isinstance(obj, Edge))

        assert(len(candidates) == 1)

        return list(candidates)[0]

    def _find_in_target_layer(self, component, nodes):
        for x in nodes:
            if isinstance(x, Edge):
                continue
            obj = x.obj(self.target_layer)
            if hasattr(obj, 'uid'):
                if obj.uid() == component.uid():
                    return x

        return None

    def transform(self, obj, target_layer):
        """ Transform comm_arch edges into comp_arch edges.
        """
        assert(isinstance(obj, Edge))

        source_comp = self.layer.get_param_value(self, 'component', obj.source)
        target_comp = self.layer.get_param_value(self, 'component', obj.target)

        source_pattern = self.layer.get_param_value(self, 'pattern', obj.source)
        target_pattern = self.layer.get_param_value(self, 'pattern', obj.target)

        src_mapping = self.layer.associated_objects(self.target_layer.name, obj.source)
        dst_mapping = self.layer.associated_objects(self.target_layer.name, obj.target)

        graph_objs = set()
        for con in self.layer.get_param_value(self, self.param, obj):
            src_serv = con.source_service
            dst_serv = con.target_service

            src_comp, src_ref = source_pattern.requiring_component(src_serv.name(), src_serv.function(), src_serv.ref())
            assert(src_comp is not None)

            dst_comp, dst_ref = target_pattern.providing_component(dst_serv.name(), dst_serv.function(), dst_serv.ref())
            assert(dst_comp is not None)

            # find source component and target component in target_layer
            src_node = self._find_in_target_layer(src_comp, src_mapping)
            dst_node = self._find_in_target_layer(dst_comp, dst_mapping)

            assert(src_node is not None)
            assert(dst_node is not None)

            if src_comp is source_comp:
                source_service = src_serv
            else:
                # transform src_serv to services of src_comp 
                source_services = src_comp.requires_services(name=src_serv.name(), ref=src_ref)
                assert len(source_services) == 1, "Invalid number (%d) of service requirements in component %s to service %s, ref %s" % (len(source_services), src_comp, src_serv.name(), src_ref)

                source_service = source_services[0]

            if dst_comp is target_comp:
                target_service = dst_serv
            else:
                # transform dst_serv to services of dst_comp 
                target_services = dst_comp.provides_services(name=dst_serv.name(), ref=dst_ref)
                assert len(target_services) == 1, "Invalid number (%d) of service provisions in component %s of service %s, ref %s" % (len(target_services), dst_comp, dst_serv.name(), dst_ref)

                target_service = target_services[0]

            obj = GraphObj(Edge(src_node, dst_node), params={ 'source-service' : source_service, 'target-service' : target_service })
            graph_objs.add(obj)

        assert graph_objs

        return graph_objs

    def target_types(self):
        return tuple({parser.Repository.Component})


class ProtocolStackEngine(AnalysisEngine):
    """ Selects 'protocolstack' parameter for edges that have 'source-service' != 'target-service'.
    """

    def __init__(self, layer, repo):
        acl = { layer : { 'reads' : set(['source-service', 'target-service'])} }
        AnalysisEngine.__init__(self, layer, param='protocolstack', acl=acl)
        self.repo = repo

    def map(self, obj, candidates):
        """ Finds possible protocol stack components for connections (:class:`ServiceEngine.Connection`) that have
        different source and target service.
        """
        assert(isinstance(obj, Edge))

        source_service = self.layer.get_param_value(self, 'source-service', obj)
        target_service = self.layer.get_param_value(self, 'target-service', obj)

        assert source_service is not None and target_service is  not None, "source-service (%s) or target-service (%s) not present for %s" % (source_service, target_service, obj)

        if not source_service.matches(target_service):
            comps = self.repo.find_components_by_type(querytype='proto',
                          query={ 'from_service' : source_service.name(),
                                  'to_service'   : target_service.name()})
            if not comps:
                logging.warning("Could not find protocol stack from '%s' to '%s' in repo." % (source_service.name(), target_service.name()))
                return set()

            return set(comps)

        return {None}

    def assign(self, obj, candidates):
        """ Assigns the first candidate.
        """
        return random.choice(list(candidates))

class MuxerEngine(AnalysisEngine):
    """ Selects 'muxer' parameter for nodes who have to many clients to a service.
    """

    class Muxer:
        def __init__(self, service, component, replicate=False):
            self.service   = service
            self.replicate = replicate
            self.edges     = set()

            if self.replicate:
                # return copy of component
                self.component = Repository.Component(component.xml_node, component.repo)
            else:
                self.component = component

            self.component_node = Layer.Node(self.component)

        def assign_edge(self, edge):
            self.edges.add(edge)

        def assigned(self, edge):
            return edge in self.edges

        def assigned_service(self):
            res = self.component.provides_services(self.service.name())
            assert len(res) == 1, "Muxer service is ambiguous"
            return res[0]

        def source_service(self):
            res = self.component.requires_services(self.service.name())
            assert len(res) == 1, "Muxer service is ambiguous"
            return res[0]

        def target_service(self):
            return self.service

    def __init__(self, layer, target_layer, repo):
        acl = { layer : { 'reads' : set(['target-service',
                                         'source-service',
                                         'mapping',
                                         'pattern-config'])},
                target_layer : { 'writes' : set(['mapping',
                                                 'source-service',
                                                 'target-service',
                                                 'pattern-config'])}}
        AnalysisEngine.__init__(self, layer, param='muxer', acl=acl)
        self.repo = repo

    def map(self, obj, candidates):
        if isinstance(obj, Edge):
            # find muxer object at target node and map if service matches
            muxer = self.layer.get_param_value(self, self.param, obj.target)
            if muxer is not None:
                if muxer.assigned(obj):
                    return {muxer}

            return {None}
        else:
            assert candidates is None

            component = obj.obj(self.layer)

            # FIXME we can only handle a single client cardinality restriction
            restricted_service = None
            for s in component.provides_services():
                if s.max_clients() is not None:
                    assert restricted_service is None, \
                        "We can only handle a single max_client restriction per component."
                    restricted_service = s

            if restricted_service is None:
                return {None}

            affected_edges = set()
            for e in self.layer.in_edges(obj):
                if self.layer.get_param_value(self, 'target-service', e).matches(restricted_service):
                    affected_edges.add(e)

            if not affected_edges:
                return {None}

            # always insert muxer if available?
            muxers = self.repo.find_components_by_type(query={'service' : restricted_service.name()},
                                                       querytype='mux')
            candidates = set()
            for mux in muxers:
                cand = self.Muxer(restricted_service, mux)
                for e in affected_edges:
                    cand.assign_edge(e)

                candidates.add(cand)

            if candidates:
                return candidates

            # if no muxer available but obj is not a singleton, we can replicate component
            if not component.singleton():
                cand = self.Muxer(restricted_service, component, replicate=True)
                for e in affected_edges:
                    cand.assign_edge(e)

                candidates.add(cand)

            if candidates:
                return candidates

            return {None}

    def assign(self, obj, candidates):
        return random.choice(list(candidates))

    def transform(self, obj, target_layer):

        if isinstance(obj, Edge):
            muxer   = self.layer.get_param_value(self, self.param, obj)
            if muxer is not None:
                return GraphObj(Edge(obj.source, muxer.component_node),
                    params={'source-service': self.layer.get_param_value(self, 'source-service', obj),
                            'target-service': muxer.assigned_service()})
            else:
                return GraphObj(obj,
                    params={'source-service': self.layer.get_param_value(self, 'source-service', obj),
                            'target-service': self.layer.get_param_value(self, 'target-service', obj)})
        else:
            mapping = self.layer.get_param_value(self, 'mapping', obj)
            muxer   = self.layer.get_param_value(self, self.param, obj)
            params = {'mapping' : mapping}
            if self.layer.isset_param_value(self, 'pattern-config', obj):
                params['pattern-config'] = self.layer.get_param_value(self, 'pattern-config', obj)
            new_objs = {GraphObj(obj, params=params)}
            if muxer is not None:
                new_objs.add(GraphObj(muxer.component_node))
                new_objs.add(GraphObj(Edge(muxer.component_node, obj),
                                      params={'source-service':muxer.source_service(),
                                              'target-service':muxer.target_service()}))

            return new_objs

    def target_types(self):
        # target layer has the same types as source layer
        return self.layer.node_types()

class QueryEngine(AnalysisEngine):
    """ Assigns 'mapping' parameter as suggested by the query model.
    """
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='mapping')

    def assign(self, obj, candidates):
        """ Assigns the first candidate.
        """
        if len(candidates) > 1:
            logging.info("Multiple mapping candidates for '%s'." % (obj))

        return random.choice(list(candidates))

    def source_types(self):
        return self.layer.node_types()

class ComponentEngine(AnalysisEngine):
    def __init__(self, layer, repo):
        AnalysisEngine.__init__(self, layer, param='component')
        self.repo = repo

    def map(self, obj, candidates):
        """ Finds component candidates for queried childs.
        """
        assert(not isinstance(obj, Edge))

        assert(candidates is None)

        child = obj.obj(self.layer)

        if isinstance(child, model.BaseChild):
            return set([child])

        components = self.repo.find_components_by_type(child.query(), child.type())

        if not components:
            logging.error("Cannot find referenced child %s '%s'." % (child.type(), child.query()))
            return set()
        elif len(components) > 1:
            logging.info("Multiple candidates found for child %s '%s'." % (child.type(), child.query()))

        return set(components)

    def assign(self, obj, candidates):
        """ Assigns the first candidate.
        """
        assert(not isinstance(obj, Edge))

        return random.choice(list(candidates))

    def check(self, obj):
        """ Sanity check.
        """
        return self.layer.get_param_value(self, self.param, obj) is not None

class EnvPatternEngine(AnalysisEngine):
    def __init__(self, layer, envmodel):
        AnalysisEngine.__init__(self, layer, param='pattern')
        self.envmodel = envmodel

    def map(self, obj, candidates):
        if self.envmodel is None:
            return candidates

        new_candidates = set()
        for c in candidates:
            if self.envmodel.accept_properties(c.properties()):
                new_candidates.add(c)

        return new_candidates

class PatternEngine(AnalysisEngine):
    def __init__(self, layer, target_layer, source_param='component', envmodel=None):
        acl = { layer        : { 'reads'  : set([source_param, 'mapping']) },
                target_layer : { 'writes' : set(['pattern-config', 'mapping', 'source-service', 'target-service'])}}
        AnalysisEngine.__init__(self, layer, param='pattern', acl=acl)
        self.source_param = source_param

    def map(self, obj, candidates):
        """ Finds component patterns.
        """
        component = self.layer.get_param_value(self, self.source_param, obj)
        if component is not None:
            return component.patterns()
        else:
            return {None}

    def assign(self, obj, candidates):
        """ Assigns the first candidate.
        """
        if len(candidates) == 1:
            return list(candidates)[0]

        first = sorted(candidates, reverse=True, key=lambda c: c.prio())[0]
        if first.prio() == 0:
            return random.choice(list(candidates))


    def check(self, obj):
        """ Checks whether a pattern was assigned.
        """
        if isinstance(obj, Edge):
            expected = self.layer.get_param_value(self, self.source_param, obj) is not None
            present  = self.layer.get_param_value(self, self.param, obj) is not None
            return expected == present
        else:
            return self.layer.get_param_value(self, self.param, obj) is not None

    def transform(self, obj, target_layer):
        """ Inserts the pattern into target_layer.
        """
        if self.layer.get_param_value(self, self.param, obj) is None:
            # no protocol stack was selected
            if isinstance(obj, Edge):
                assert obj.source in target_layer.nodes(), "%s is not in %s" % (obj.source, target_layer)
                assert obj.target in target_layer.nodes(), "%s is not in %s" % (obj.target, target_layer)

            return obj
        elif isinstance(obj, Edge):
            params = None
            if self.layer.isset_param_value(self, 'mapping', obj.source):
                params = { 'mapping' : self.layer.get_param_value(self, 'mapping', obj.source) }
            elif self.layer.isset_param_value(self, 'mapping', obj.target):
                params = { 'mapping' : self.layer.get_param_value(self, 'mapping', obj.target) }

            pattern = self.layer.get_param_value(self, self.param, obj)
            result = pattern.flatten(params)

            # TODO implement
            assert len(result) == 1, "Pattern insertion on edges not implemented"

            node = list(result)[0].obj

            result.add(GraphObj(
                Edge(obj.source, node)))
            result.add(GraphObj(
                Edge(node, obj.target)))

            return result
        else:
            params = None
            if self.layer.isset_param_value(self, 'mapping', obj):
                params = { 'mapping' : self.layer.get_param_value(self, 'mapping', obj) }
            return self.layer.get_param_value(self, self.param, obj).flatten(params)

    def target_types(self):
        return tuple({parser.Repository.Component})

class SpecEngine(AnalysisEngine):
    def __init__(self, layer, param='component'):
        acl = { layer : { 'reads' : set(['mapping']) } }
        AnalysisEngine.__init__(self, layer, param=param, acl=acl)

    def map(self, obj, candidates): 
        """ Reduces set of 'mapping' candidates by checking the obj's spec requirements.
        """
        assert(not isinstance(obj, Edge))

        child = obj.obj(self.layer)

        # no need to check this for proxies
        if isinstance(child, model.Proxy):
            return candidates

        keep = set()
        for c in candidates:
            pf_comp = self.layer.get_param_value(self, 'mapping', obj)
            assert(pf_comp is not None)

            for p in c.patterns():
                if pf_comp.match_specs(p.requires_specs()):
                    keep.add(c)
                    break

        return keep

    def check(self, obj):
        """ Sanity check.
        """
        assert(not isinstance(obj, Edge))

        child = obj.obj(self.layer)

        # no need to check this for proxies
        if isinstance(child, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value(self, 'mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value(self, 'component', obj)
            if comp is None:
                print("No component assigned from candidates: %s" % self.layer.get_param_candidates(self, 'component', obj))
            assert(comp is not None)
        else:
            comp = child

        if not pf_comp.match_specs(comp.requires_specs()):
            return False

        return True

class RteEngine(AnalysisEngine):
    def __init__(self, layer, param='component'):
        acl = { layer : { 'reads' : set(['mapping']) } }
        AnalysisEngine.__init__(self, layer, param=param, acl=acl)

    def map(self, obj, candidates):
        """ Reduces set of 'mapping' candidates by checking the obj's rte requirements.
        """
        assert(not isinstance(obj, Edge))

        child = obj.obj(self.layer)

        # no need to check this for proxies
        if isinstance(child, model.Proxy):
            return candidates

        keep = set()
        for c in candidates:

            pf_comp = self.layer.get_param_value(self, 'mapping', obj)
            assert(pf_comp is not None)

            if c.requires_rte() == pf_comp.rte():
                keep.add(c)

        return keep

    def check(self, obj):
        """ Sanity check
        """
        assert(not isinstance(obj, Edge))

        child = obj.obj(self.layer)

        # no need to check this for proxies
        if isinstance(child, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value(self, 'mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value(self, 'component', obj)
            if comp is None:
                print("No component assigned from candidates: %s" % self.layer.get_param_candidates(self, 'component', obj))
            assert(comp is not None)
        else:
            comp = child

        if comp.requires_rte() != pf_comp.rte():
            return False

        return True

class ReachabilityEngine(AnalysisEngine):
    def __init__(self, layer, target_layer, platform_model):
        acl = { layer        : { 'reads'  : set(['mapping', 'service']) },
                target_layer : { 'writes' : set(['service', 'remotename'])}}
        AnalysisEngine.__init__(self, layer, param='proxy', acl=acl)
        self.platform_model = platform_model
        self.target_layer = target_layer

    def _find_carriers(self, obj):
        src_comp = self.layer.get_param_value(self, 'mapping', obj.source)
        dst_comp = self.layer.get_param_value(self, 'mapping', obj.target)

        result, carrier, pcomp = self.platform_model.reachable(src_comp, dst_comp)
        if result or carrier == self.layer.get_param_value(self, 'service', obj).name:
            return set([('native', pcomp)])
        else:
            return set([(carrier, pcomp)])

    def map(self, obj, candidates):
        """ Finds possible carriers.
        """
        assert(isinstance(obj, Edge))
        assert(candidates is None)

        candidates = self._find_carriers(obj)

        return candidates

    def assign(self, obj, candidates):
        """ Assigns first candidate
        """
        assert(isinstance(obj, Edge))

        return random.choice(list(candidates))

    def transform(self, obj, target_layer):
        """ Transforms obj (Edge) based on the selected carrier.

            'native' -- returns obj

            'else'   -- inserts :class:`mcc.model.Proxy`
        """
        assert(isinstance(obj, Edge))
        assert(target_layer == self.target_layer)

        carrier, pcomp = self.layer.get_param_value(self, self.param, obj)
        if carrier == 'native':
            return GraphObj(obj, params={ 'service' : self.layer.get_param_value(self, 'service', obj) })
        else:
            assert carrier is not None, "not implemented"
            # FIXME automatically determine carrier from contract repo

            service = self.layer.get_param_value(self, 'service', obj)
            proxy = model.Proxy(carrier=carrier, service=service)
            proxynode = Layer.Node(proxy)
            result = [GraphObj(proxynode, params={'remotename' : service.function})]

            src_map = self.layer.associated_objects(target_layer.name, obj.source)
            dst_map = self.layer.associated_objects(target_layer.name, obj.target)
            assert(len(src_map) == 1)
            assert(len(dst_map) == 1)
            src = list(src_map)[0]
            dst = list(dst_map)[0]

            result.append(GraphObj(Edge(src, proxynode), params={'service' : proxy.service}))
            result.append(GraphObj(Edge(proxynode, dst), params={'service' : proxy.service}))

            # add dependencies to pcomp
            found = False
            for n in self.layer.nodes():
                comp = n.obj(self.layer)
                if pcomp in comp.functions():
                    pfc  = self.layer.get_param_value(self, 'mapping', n)
                    pfc_source = self.layer.get_param_value(self, 'mapping', obj.source)
                    pfc_target = self.layer.get_param_value(self, 'mapping', obj.target)
                    if pfc.in_native_domain(pfc_source):
                        result.append(GraphObj(Edge(proxynode, n), params={ 'service' :
                            model.ServiceConstraints(name=carrier, from_ref='to', function=pcomp) }))
                        found = True
                    elif pfc.in_native_domain(pfc_target):
                        result.append(GraphObj(Edge(proxynode, n), params={ 'service' :
                            model.ServiceConstraints(name=carrier, from_ref='from', function=pcomp) }))
                        found = True

            assert found, "Cannot find function '%s' required by proxy" % (pcomp)

            return result

    def target_types(self):
        return self.target_layer.node_types()


class InstantiationEngine(AnalysisEngine):
    def __init__(self, layer, target_layer, factory, target_mapping='mapping'):
        acl = { layer        : { 'reads'  : { 'mapping', 'source-service', 'target-service', 'pattern-config'} },
                target_layer : { 'writes' : { target_mapping, 'source-service', 'target-service' }}}
        AnalysisEngine.__init__(self, layer, param='instance', acl=acl)
        self.factory      = factory
        self.target_layer = target_layer
        self.target_mapping = target_mapping

    def reset(self, obj):
        if isinstance(obj, Layer.Node):
            pfc = self.layer.untracked_get_param_value('mapping', obj)

            cands = self.layer.untracked_get_param_candidates('instance', obj)
            for c in cands:
                if not c.shared():
                    self.factory.remove_instance(pfc.name(), c)

    def _find_node(self, obj, instance):
        for n in self.layer.associated_objects(self.target_layer.name, obj):
            if n.obj(self.target_layer) == instance:
                return n
        return None

    def map(self, obj, candidates):
        """ Get and map to dedicated and shared instance object from factory
        """
        assert candidates is None
        if isinstance(obj, Edge):
            source_candidates = self.layer.get_param_candidates(self, 'instance', obj.source)
            source_value      = self.layer.get_param_value(self, 'instance', obj.source)
#            target_candidates = self.layer.get_param_candidates(self, 'instance', obj.target)
#            target_value      = self.layer.get_param_value(self, 'instance', obj.target)

            # TODO check that source and target service are the same
            #      best done by using the factory to create edges once and reference them here
            #      at the moment, we only use shareable=true for SISO components
            if source_value.shared():
                if len(source_candidates) > 1:
                    return {False}

            return {True}
        else:

            component = obj.obj(self.layer)

            # if it's already an instance
            if isinstance(component, model.Instance):
                return {component}

            pfc = self.layer.get_param_value(self, 'mapping', obj)

            config = None
            if self.layer.isset_param_value(self, 'pattern-config', obj):
                config = self.layer.get_param_value(self, 'pattern-config', obj)
            ded    = self.factory.dedicated_instance(pfc.name(), component, config)

            if not component.dedicated():
                shared = self.factory.shared_instance(pfc.name(), component, config)
            else:
                # TODO if out edges have the same targets and constraints, we could still create a shared instance
                return {ded}

            return {ded, shared}

    def assign(self, obj, candidates):
        """ Assigns shared candidate if present
        """
        if not isinstance(obj, Edge):
            for c in candidates:
                if c.shared():
                    return c

        return random.choice(list(candidates))

    def transform(self, obj, target_layer):

        if isinstance(obj, Edge):
            if self.layer.get_param_value(self, self.param, obj):
                source = self.layer.get_param_value(self, self.param, obj.source)
                target = self.layer.get_param_value(self, self.param, obj.target)

                source_node = self._find_node(obj.source, source)
                target_node = self._find_node(obj.target, target)

                assert source_node is not None
                assert target_node is not None

                return GraphObj(Edge(source_node,target_node),
                    params={'source-service': self.layer.get_param_value(self, 'source-service', obj),
                            'target-service': self.layer.get_param_value(self, 'target-service', obj)})
            else:
                # FIXME return already-inserted object to correctly set inter-layer relations

                #      nodes cannot be inserted multiple times, i.e. they are indexed by hash so that
                #      returning the same obj (by transform()) multiple times will not create another
                #      node but track that obj was written by multiple operations
                #      in contrast, as we use a MultiDigraph, edges would be inserted multiple times
                #      unless we use the same object (i.e. store the reference)
                return set()

        else:
            instance = self.layer.get_param_value(self, self.param, obj)
            assert hasattr(instance, 'node')

            return GraphObj(instance.node,
                            params={self.target_mapping:self.layer.get_param_value(self, 'mapping', obj)})

    def target_types(self):
        return self.factory.types()

class SingletonEngine(AnalysisEngine):
    def __init__(self, layer, platform_model):
        acl = { layer : { 'reads' : set(['mapping', 'target-service']) }}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)
        self.pf_model = platform_model

    def check(self, obj):
        assert not isinstance(obj, Edge)

        instance = obj.obj(self.layer)

        # first, every node, which is a singleton component, must only be present once per PfComponent
        subsys = self.layer.get_param_value(self, 'mapping', obj)
        if instance.component.singleton():
            for n in self.layer.nodes() - {obj}:
                if n.obj(self.layer).is_component(instance.component):
                    other_subsys = self.layer.get_param_value(self, 'mapping', n)
                    if subsys.same_singleton_domain(other_subsys):
                        logging.error("%s is instantiated in %s and %s" % (instance.component, subsys, other_subsys))
                        return False

        # second, every service provision with a max_clients restriction must have at most n clients
        restrictions = dict()
        for s in instance.provides_services():
            clients = 0
            if s.max_clients() is not None:
                restrictions[s] = { 'max' : int(s.max_clients()), 'cur' : 0 }

        if not restrictions:
            return True

        for e in self.layer.in_edges(obj):
            s = self.layer.get_param_value(self, 'target-service', e)
            if s in restrictions:
                restrictions[s]['cur'] += 1

        for s in restrictions:
            if restrictions[s]['cur'] > restrictions[s]['max']:
                logging.error('Instance %s has to many clients for service %s.' % (instance, s))
                return False

        return True

