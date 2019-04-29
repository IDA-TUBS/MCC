"""
Description
-----------

Implements analysis engines.

:Authors:
    - Johannes Schlatow

"""
import logging
from mcc.framework import *
from mcc.graph import *
from mcc import model
from mcc import parser
from mcc.taskmodel import *

import itertools
import copy

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
                for junction in objects:
                    if isinstance(junction, Tasklink):
                        continue

                    if junction.expect_in == 'junction' and \
                       junction.expect_in_args['junction_name'] == task.expect_out_args['name']:

                        objects.add(Tasklink(task, junction, linktype='signal'))
                        task.set_placeholder_out(None)
                        break

                assert task.expect_out is None, 'Not found: Junction "%s" for task %s' % (task.expect_out_args['name'], task)

        return objects

    def map(self, obj, candidates):
        """ Pulls taskgraph objects from repository
        """
        assert candidates is None

        if isinstance(obj, model.Instance):
            component = obj.component
        else:
            component = obj

        # get time-triggered taskgraph
        try:
            objects = component.taskgraph_objects()
        except Exception as e:
           print("Could not get taskgraph objects for %s" % obj) 
           raise e

        # for each incoming connection (see if incoming signal exists)
        signals = set()
        for e in self.layer.graph.in_edges(obj):
            serv = self.layer.get_param_value(self, 'target-service', e)
            signals.add(serv.ref())

        # for each outgoing connection (see if incoming signal exists)
        for e in self.layer.graph.out_edges(obj):
            serv = self.layer.get_param_value(self, 'source-service', e)
            signals.add(serv.ref())

        for sig in signals - {None}:
            objects.update(component.taskgraph_objects(signal=sig))

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
                for junction in junction_objects:
                    if isinstance(junction, Tasklink):
                        continue

                    if junction.expect_in == 'junction' and \
                       junction.expect_in_args['junction_name'] == task.expect_out_args['name']:

                        objects.add(Tasklink(task, junction, linktype='signal'))
                        task.set_placeholder_out(None)
                        break

                assert task.expect_out is None, 'Not found: Junction "%s" for task %s' % (task.expect_out_args['name'], task)

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
        method = call.expect_out_args('method')
        server = None
        for e in self.layer.graph.out_edges(obj):
            src = self.layer.get_param_value(self, 'source-service', e)
            if src.ref() == to_ref:
                server = e.target
                server_ref = self.layer.get_param_value(self, 'target-service', e).ref()
                break
        assert(server is not None)

        # get rpcobjects
        if isinstance(server, model.Instance):
            rpc_objects = server.component.taskgraph_objects(rpc=server_ref, method=method)
        else:
            rpc_objects = server.taskgraph_objects(rpc=server_ref, method=method)

        assert len(rpc_objects), 'No task objects found for RPC'

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
        call.set_placeholder_out(None)
        ret.set_placeholder_in(None)
        firsttask.set_placeholder_in(None)
        lasttask.set_placeholder_out(None)

        return objects

    def map(self, obj, candidates):
        """ Pulls taskgraph objects from repository
        """
        assert candidates is None

        objects = self.layer.get_param_value(self, 'coretasks', obj)

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

    def _graph_objects(self, obj, objects):
        result = set()

        for o in objects:
            if isinstance(o, Task):
                result.add(GraphObj(o, params={'mapping' : self.layer.get_param_value(self, 'mapping', obj)}))
            else:
                result.add(o)

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

    def check(self, obj, first):
        """ Check task graph consistency 
        """
        taskobjects = self.layer.get_param_value(self, self.param, obj)

        # component may have no tasks, which is an indicator for a superfluous component
        # but not necessarily an error
        if taskobjects is None:
            logging.warning("No tasks found for component %s" % obj)
        elif len(taskobjects) == 0:
            logging.warning("No tasks found for component %s" % obj)

        tasks = (t for t in taskobjects if isinstance(t, Task))
        links = (t for t in taskobjects if isinstance(t, Tasklink))

        # TODO check that sender exists for each receiver

        # check for unconnected tasks
        for t in tasks:
            # There must not be a client/server placeholder in the taskgraph
            if t.expect_in == 'client' or t.expect_in == 'server':
                logging.error("Client/Server placeholder (in) present in taskgraph for component %s" % obj)
                return False

            # resulting taskgraph may still contain interrupt or sender placeholders,
            #  junction placeholders must at least have one connection though
            if t.expect_in == 'junction':
                connections = 0
                for l in links:
                    if l.target == t:
                        connections += 1

                if connections == 0:
                    logging.error("Junction placeholder (in) present in taskgraph for component %s" % obj)
                    return False
                elif connections > 1 and t.expect_in != 'junction':
                    logging.error("Multiple connections to junction taskgraph for component %s" % obj)
                    return False

            if t.expect_out == 'server':
                logging.error("Server placeholder (out) present in taskgraph for component %s" % obj)
                return False

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
        pfc = self.layer.get_param_value(self, 'mapping', obj)
        comp = self.layer.get_param_value(self, 'component', obj)

        # trace ROM services
        for edge in self.layer.graph.in_edges(obj):
            if edge.source in visited:
                continue

            other_pfc = self.layer.get_param_value(self, 'mapping', edge.source)
            if other_pfc is not None and pfc != other_pfc:
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
        for edge in self.layer.graph.out_edges(obj):
            service = self.layer.get_param_value(self, 'service', edge)
            if service.function == 'Network':
                return edge.target

        return None

    def check(self, obj, first):
        # for each subsystem, sum up outbound network traffic
        if first:
            self.state = dict()

        pfc = self.layer.get_param_value(self, 'mapping', obj)
        if pfc is None: # skip unmapped components (proxies)
            return True

        if pfc not in self.state:
            self.state[pfc] = 0

        # only evaluate and trace provided ROM services that have an out-traffic node
        comp = self.layer.get_param_value(self, 'component', obj)
        for edge in self.layer.graph.in_edges(obj):
            other_pfc = self.layer.get_param_value(self, 'mapping', edge.source)
            if other_pfc is not None and pfc != other_pfc:
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

        pfc.set_state('out_traffic', int(self.state[pfc]))

        assert self.state[pfc] <= self.max_byte_s, "%s > %s" % (self.state[pfc], self.max_byte_s)
        return self.state[pfc] <= self.max_byte_s


class QuantumEngine(AnalysisEngine):
    def __init__(self, layer, name):
        acl = { layer        : {'reads' : set(['mapping']) }}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)
        self.name = name

    def check(self, obj, first):
        # for each subsystem, sum of caps must be below the specified threshold
        if first:
            self.state = dict()

        pfc = self.layer.get_param_value(self, 'mapping', obj)
        if pfc not in self.state:
            self.state[pfc] = pfc.quantum(self.name)

        self.state[pfc] -= obj.component.requires_quantum(self.name)

        if self.state[pfc] < 0:
            logging.error("Subsystem %s exceeds its %s (%d)." % (pfc, self.name,
                                                                 pfc.quantum(self.name)))

        pfc.set_state('%s-remaining' % self.name, self.state[pfc])

        return self.state[pfc] >= 0

class StaticEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='mapping')

    def map(self, obj, candidates):
        assert candidates is not None

        exclude = set()
        for o in candidates:
            if o.static():
                exclude.add(o)

        candidates -= exclude

        if len(candidates) > 1:
            logging.warning("Still cannot inherit mapping unambiguously.")
        elif len(candidates) == 1 and len(exclude) > 0:
            logging.warning("Mapping was reduced by excluding static subsystems. Candidates left for %s: %s" % (obj, candidates-exclude))

        return candidates - exclude

class FunctionEngine(AnalysisEngine):
    class Dependency:
        def __init__(self, function, provider):
            self.function = function
            self.provider = provider

        def __repr__(self):
            return "depends on %s from %s" % (self.function, self.provider)

    def __init__(self, layer, target_layer, repo):
        acl = { layer        : {'reads' : {'mapping', 'service'}},
                target_layer : {'writes' : {'mapping', 'service'}}}
        AnalysisEngine.__init__(self, layer, param='dependencies', acl=acl)
        self.repo = repo
        self.target_layer = target_layer

    def _required_functions(self, obj):
        # return required and unsatisfied function dependencies of 'obj'
        result = set()
        for dep in obj.dependencies('function'):
            depfunc = dep['function']
            # edge exists?
            satisfied = False
            for e in self.layer.graph.out_edges(obj):
                sc = self.layer.get_param_value(self, 'service', e)
                if sc.function == depfunc:
                    satisfied = True

            if not satisfied:
                result.add(depfunc)

        return result

    def _provided_functions(self, obj):
        # return functions provided by 'obj'
        funcs = copy.copy(obj.functions())
        if hasattr(obj, 'query'):
            for provider in self.repo.find_components_by_type(obj.query(), obj.type()):
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
        for obj in candidate:
            pfc = self.layer.get_param_value(self, 'mapping', obj.provider)

            if not from_pfc.in_native_domain(pfc):
                costs += 1

        return costs

    def map(self, obj, candidates):
        # aggregate dependencies
        functions = self._required_functions(obj)
        if len(functions) == 0:
            return {None}

        dependencies = dict()
        for f in functions:
            # find function provider(s)
            dependencies[f] = set()
            for node in self.layer.graph.nodes():
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
                best      = cand
            elif costs < min_costs:
                min_costs = costs
                best      = cand

        return best

    def transform(self, obj, target_layer):
        assert not isinstance(obj, Edge)

        graph_objs = set()
        graph_objs.add(GraphObj(obj, params={'mapping' : self.layer.get_param_value(self, 'mapping', obj)}))

        dependencies = self.layer.get_param_value(self, self.param, obj)
        if dependencies is not None:
            for dep in dependencies:
                graph_objs.add(GraphObj(Edge(obj, dep.provider),
                                        params={'service' : model.ServiceConstraints(function=dep.function)}))

        return graph_objs

    def target_types(self):
        # target layer has the same types as source layer
        return self.layer.node_types()


class MappingEngine(AnalysisEngine):
    def __init__(self, layer, repo, pf_model):
        AnalysisEngine.__init__(self, layer, param='mapping')
        self.pf_model = pf_model
        self.repo = repo

    def map(self, obj, candidates):
        if candidates is not None and len(candidates) > 0:
            return candidates

        assert not isinstance(obj, Edge)

        components = self.repo.find_components_by_type(obj.query(), obj.type())

        if len(components) == 0:
            logging.error("Cannot find referenced child %s '%s'." % (obj.type(), obj.query()))
            return set()

        pf_components = self.pf_model.platform_graph.nodes()
        static = set([pfc for pfc in pf_components if pfc.static()])
        pf_components = pf_components - static

        candidates = set()

        # iterate components and aggregate possible platform components
        for c in components:
            for pfc in pf_components:
                if pfc.match_specs(c.requires_specs()):
                    candidates.add(pfc)

        print("%s: %s" % (obj, candidates))
        return candidates

    def assign(self, obj, candidates):
        # TODO here we call the constraint solver
        return list(candidates)[0]

    def check(self, obj, first):
        """ Checks whether a platform mapping is assigned to all nodes.
        """
        assert(not isinstance(obj, Edge))

        okay = self.layer.get_param_value(self, 'mapping', obj) is not None
        if not okay:
            logging.error("Node '%s' is not mapped to anything.", obj)

        return okay

class DependencyEngine(AnalysisEngine):
    def __init__(self, layer):
        acl = { layer : { 'reads' : set(['component']) } }
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)

    def _find_provider_recursive(self, node, function):
        for con in self.layer.graph.out_edges(node):
            comp2 = self.layer.get_param_value(self, 'component', con.target)
            if function in comp2.functions():
                return True
            elif comp2.type() == 'proxy':
                if self._find_provider_recursive(con.target, function):
                    return True

        return False

    def check(self, obj, first):
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

    def check(self, obj, first):
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
            for s in obj.requires_services():
                # find provider among connected nodes
                found = 0
                for con in self.layer.graph.out_edges(obj):
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
        acl = { layer        : { 'reads'  : set(['service', 'pattern', 'component', target_layer.name]) },
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

    def check(self, obj, first):
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

        if len(source_ports) == 0:
            logging.error("Service requirement is over constrained for %s by %s" % ( source_comp, constraints))

        if len(target_ports) == 0:
            logging.error("Service provision is over constrained for %s by %s" % ( target_comp, constraints))

        return len(source_ports) > 0 and len(target_ports) > 0

    def map(self, obj, candidates):
        assert(isinstance(obj, Edge))
        source_ports, target_ports = self._get_ports(obj)

        candidates = set()

        # there may be multiple source ports, i.e. multiple requirements connected to the same target
        for src in source_ports:
            candidates.add(self.Connection(src, target_ports[0]))

        return set([frozenset(candidates)])

    def assign(self, obj, candidates):
        assert(isinstance(obj, Edge))

        assert(len(candidates) == 1)

        return list(candidates)[0]

    def _find_in_target_layer(self, component, nodes):
        for x in nodes:
            if hasattr(x, 'uid'):
                if x.uid() == component.uid():
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

        src_mapping = self.layer.get_param_value(self, self.target_layer.name, obj.source)
        dst_mapping = self.layer.get_param_value(self, self.target_layer.name, obj.target)

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

        assert(len(graph_objs) > 0)

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
            comps = self.repo.find_protocolstacks(from_service=source_service.name(), to_service=target_service.name())
            if len(comps) == 0:
                logging.warning("Could not find protocol stack from '%s' to '%s' in repo." % (source_service.name(), target_service.name()))
            return comps

        return set([None])

    def assign(self, obj, candidates):
        """ Assigns the first candidate.
        """
        return list(candidates)[0]

class MuxerEngine(AnalysisEngine):
    """ Selects 'muxer' parameter for nodes who have to many clients to a service.
    """

    class Muxer:
        def __init__(self, service, component, replicate=False):
            self.service   = service
            self.component = component
            self.replicate = replicate
            self.edges     = set()

        def assign_edge(self, edge):
            self.edges.add(edge)

        def assigned(self, edge):
            return edge in self.edges

        def assigned_component(self, edge):
            if self.replicate:
                # return copy of component
                return Repository.Component(self.component.xml_node, self.component.repo)
            else:
                return self.component

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
                                         'mapping'])},
                target_layer : { 'writes' : set(['mapping',
                                                 'source-service',
                                                 'target-service'])}}
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

            # FIXME we can only handle a single client cardinality restriction
            restricted_service = None
            for s in obj.provides_services():
                if s.max_clients() is not None:
                    assert restricted_service is None, \
                        "We can only handle a single max_client restriction per component."
                    restricted_service = s

            if restricted_service is None:
                return {None}

            affected_edges = set()
            for e in self.layer.graph.in_edges(obj):
                if self.layer.get_param_value(self, 'target-service', e).matches(restricted_service):
                    affected_edges.add(e)

            if len(affected_edges) == 0:
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

            if len(candidates) > 0:
                return candidates

            # if no muxer available but obj is not a singleton, we can replicate obj
            if not obj.singleton():
                cand = self.Muxer(restricted_service, obj)
                for e in affected_edges:
                    cand.assign_edge(e)

                candidates.add(cand)

            if len(candidates) > 0:
                return candidates

            return {None}

    def assign(self, obj, candidates):
        return list(candidates)[0]

    def transform(self, obj, target_layer):

        if isinstance(obj, Edge):
            muxer   = self.layer.get_param_value(self, self.param, obj)
            if muxer is not None:
                return GraphObj(Edge(obj.source, muxer.assigned_component(obj)),
                    params={'source-service': self.layer.get_param_value(self, 'source-service', obj),
                            'target-service': muxer.assigned_service()})
            else:
                return GraphObj(obj,
                    params={'source-service': self.layer.get_param_value(self, 'source-service', obj),
                            'target-service': self.layer.get_param_value(self, 'target-service', obj)})
        else:
            mapping = self.layer.get_param_value(self, 'mapping', obj)
            muxer   = self.layer.get_param_value(self, self.param, obj)
            new_objs = {GraphObj(obj, params={'mapping':mapping})}
            if muxer is not None:
                new_objs.add(GraphObj(muxer.component))
                new_objs.add(GraphObj(Edge(muxer.component, obj),
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
        if len(candidates) == 0:
            logging.error("No mapping candidate for '%s'." % (obj.label()))
            raise Exception("ERROR")
        elif len(candidates) > 1:
            logging.info("Multiple mapping candidates for '%s'." % (obj.label()))

        return list(candidates)[0]

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

        if isinstance(obj, model.BaseChild):
            return set([obj])

        components = self.repo.find_components_by_type(obj.query(), obj.type())

        if len(components) == 0:
            logging.error("Cannot find referenced child %s '%s'." % (obj.type(), obj.query()))
            return set()
        elif len(components) > 1:
            logging.info("Multiple candidates found for child %s '%s'." % (obj.type(), obj.query()))

        return set(components)

    def assign(self, obj, candidates):
        """ Assigns the first candidate.
        """
        assert(not isinstance(obj, Edge))

        assert len(candidates) != 0, "no component left for assignment to child %s" % obj

        return list(candidates)[0]

    def check(self, obj, first):
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
        acl = { layer        : { 'reads'  : set([source_param]) },
                target_layer : { 'writes' : set(['pattern-config', 'source-service', 'target-service'])}}
        AnalysisEngine.__init__(self, layer, param='pattern', acl=acl)
        self.source_param = source_param

    def map(self, obj, candidates):
        """ Finds component patterns.
        """
        component = self.layer.get_param_value(self, self.source_param, obj)
        if component is not None:
            return component.patterns()
        else:
            return set([None])

    def assign(self, obj, candidates):
        """ Assigns the first candidate.
        """
        if len(candidates) == 0:
            raise Exception("no pattern left for assignment")

        if len(candidates) == 1:
            return list(candidates)[0]

        return sorted(candidates, reverse=True, key=lambda c: c.prio())[0]

    def check(self, obj, first):
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
                assert obj.source in target_layer.graph.nodes(), "%s is not in %s" % (obj.source, target_layer)
                assert obj.target in target_layer.graph.nodes(), "%s is not in %s" % (obj.target, target_layer)

            return obj
        elif isinstance(obj, Edge):
            # TODO implement
            raise NotImplementedError()
        else:
            return self.layer.get_param_value(self, self.param, obj).flatten()

    def target_types(self):
        return self.layer.node_types()

class SpecEngine(AnalysisEngine):
    def __init__(self, layer, param='component'):
        acl = { layer : { 'reads' : set(['mapping']) } }
        AnalysisEngine.__init__(self, layer, param=param, acl=acl)

    def map(self, obj, candidates): 
        """ Reduces set of 'mapping' candidates by checking the obj's spec requirements.
        """
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
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

    def check(self, obj, first):
        """ Sanity check.
        """
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value(self, 'mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value(self, 'component', obj)
            if comp is None:
                print("No component assigned from candidates: %s" % self.layer.get_param_candidates(self, 'component', obj))
            assert(comp is not None)
        else:
            comp = obj

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

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return candidates

        keep = set()
        for c in candidates:

            pf_comp = self.layer.get_param_value(self, 'mapping', obj)
            assert(pf_comp is not None)

            if c.requires_rte() == pf_comp.rte():
                keep.add(c)

        return keep

    def check(self, obj, first):
        """ Sanity check
        """
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value(self, 'mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value(self, 'component', obj)
            if comp is None:
                print("No component assigned from candidates: %s" % self.layer.get_param_candidates(self, 'component', obj))
            assert(comp is not None)
        else:
            comp = obj

        if comp.requires_rte() != pf_comp.rte():
            return False

        return True

class ReachabilityEngine(AnalysisEngine):
    def __init__(self, layer, target_layer, platform_model):
        acl = { layer        : { 'reads'  : set(['mapping', 'service', target_layer.name]) },
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
        assert(len(candidates) > 0)

        return list(candidates)[0]

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
            result = [GraphObj(proxy, params={'remotename' : service.function})]

            src_map = self.layer.get_param_value(self, target_layer.name, obj.source)
            dst_map = self.layer.get_param_value(self, target_layer.name, obj.target)
            assert(len(src_map) == 1)
            assert(len(dst_map) == 1)
            src = list(src_map)[0]
            dst = list(dst_map)[0]

            result.append(GraphObj(Edge(src, proxy), params={'service' : proxy.service}))
            result.append(GraphObj(Edge(proxy, dst), params={'service' : proxy.service}))

            # add dependencies to pcomp
            found = False
            for n in self.layer.graph.nodes():
                if pcomp in n.functions():
                    pfc  = self.layer.get_param_value(self, 'mapping', n)
                    pfc_source = self.layer.get_param_value(self, 'mapping', obj.source)
                    pfc_target = self.layer.get_param_value(self, 'mapping', obj.target)
                    if pfc.in_native_domain(pfc_source):
                        result.append(GraphObj(Edge(proxy, n), params={ 'service' :
                            model.ServiceConstraints(name=carrier, from_ref='to', function=pcomp) }))
                        found = True
                    elif pfc.in_native_domain(pfc_target):
                        result.append(GraphObj(Edge(proxy, n), params={ 'service' :
                            model.ServiceConstraints(name=carrier, from_ref='from', function=pcomp) }))
                        found = True

            assert found, "Cannot find function '%s' required by proxy" % (pcomp)

            return result

    def target_types(self):
        return self.target_layer.node_types()

class GenodeSubsystemEngine(AnalysisEngine):
    """ Decompose component graph into subsystems by insert 'init' or other RTEs (e.g. noux, etc.).
    """
    # TODO [low] implement GenodeSubystemEngine (only required for nested/hierarchical systems)

    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='rte-instance')

class BacktrackingTestEngine(AnalysisEngine):
    def __init__(self, layer, param, model, failure_rate=0, fail_times=1000):
        super().__init__(layer, param)
        self.model         = model
        self.failure_rate  = 0
        self.fail_times    = fail_times

    def check(self, obj, first):
        if self.fail_times == 0:
            return True

        # check if for every assign node all the candidates have been used
        for node in self.model.decision_graph.nodes():
            if not self.model.decision_graph.candidates_exhausted(node):
                self.fail_times -= 1
                return node

        return True

    def node_types(self):
        return []

class InstantiationEngine(AnalysisEngine):
    def __init__(self, layer, target_layer, factory):
        acl = { layer        : { 'reads'  : { 'mapping', 'source-service', 'target-service', 'pattern-config'} },
                target_layer : { 'writes' : { 'mapping', 'source-service', 'target-service' }}}
        AnalysisEngine.__init__(self, layer, param='instance', acl=acl)
        self.factory      = factory
        self.target_layer = target_layer

    def reset(self):
        self.factory.reset()

    def map(self, obj, candidates):
        """ Get and map to dedicated and shared instance object from factory
        """
        assert candidates is None
        if isinstance(obj, Edge):
            source_candidates = self.layer.get_param_candidates(self, 'instance', obj.source)
            source_value      = self.layer.get_param_value(self, 'instance', obj.source)
            target_candidates = self.layer.get_param_candidates(self, 'instance', obj.target)
            target_value      = self.layer.get_param_value(self, 'instance', obj.target)

            # TODO check that source and target service are the same
            #      best done by using the factory to create edges once and reference them here
            #      at the moment, we only use shareable=true for SISO components
            if source_value.shared():
                if len(source_candidates) > 1:
                    return {False}

            return {True}
        else:

            # if it's already an instance
            if isinstance(obj, model.Instance):
                return {obj}

            pfc = self.layer.get_param_value(self, 'mapping', obj)

            ded    = self.factory.dedicated_instance(pfc.name(), obj,
                            self.layer.get_param_value(self, 'pattern-config', obj))

            if not obj.dedicated():
                shared = self.factory.shared_instance   (pfc.name(), obj,
                                self.layer.get_param_value(self, 'pattern-config', obj))
            else:
                # TODO if out edges have the same targets and constraints, we could still create a shared instance
                return {ded}

            return {ded, shared}

    def assign(self, obj, candidates):
        """ Assigns shared candidate if present
        """
        if not isinstance(obj, Edge):
            assert len(candidates) > 0

            for c in candidates:
                if c.shared():
                    return c

        return list(candidates)[0]

    def transform(self, obj, target_layer):

        if isinstance(obj, Edge):
            if self.layer.get_param_value(self, self.param, obj):
                source = self.layer.get_param_value(self, self.param, obj.source)
                target = self.layer.get_param_value(self, self.param, obj.target)

                return GraphObj(Edge(source,target),
                    params={'source-service': self.layer.get_param_value(self, 'source-service', obj),
                            'target-service': self.layer.get_param_value(self, 'target-service', obj)})
            else:
                # FIXME return already-inserted object to correctly set inter-layer relations
                return set()

        else:
            return GraphObj(self.layer.get_param_value(self, self.param, obj),
                            params={'mapping':self.layer.get_param_value(self, 'mapping', obj)})

    def target_types(self):
        return self.factory.types()

class SingletonEngine(AnalysisEngine):
    def __init__(self, layer, platform_model):
        acl = { layer : { 'reads' : set(['mapping', 'target-service']) }}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)
        self.pf_model = platform_model

    def check(self, obj, first):
        assert not isinstance(obj, Edge)

        # first, every node, which is a singleton component, must only be present once per PfComponent
        subsys = self.layer.get_param_value(self, 'mapping', obj)
        if obj.component.singleton():
            for n in self.layer.graph.nodes() - {obj}:
                if n.is_component(obj.component):
                    other_subsys = self.layer.get_param_value(self, 'mapping', n)
                    if subsys.same_singleton_domain(other_subsys):
                        logging.error("%s is instantiated in %s and %s" % (obj.component, subsys, other_subsys))
                        return False

        # second, every service provision with a max_clients restriction must have at most n clients
        restrictions = dict()
        for s in obj.provides_services():
            clients = 0
            if s.max_clients() is not None:
                restrictions[s] = { 'max' : int(s.max_clients()), 'cur' : 0 }

        if len(restrictions) == 0:
            return True

        for e in self.layer.graph.in_edges(obj):
            s = self.layer.get_param_value(self, 'target-service', e)
            if s in restrictions:
                restrictions[s]['cur'] += 1

        for s in restrictions:
            if restrictions[s]['cur'] > restrictions[s]['max']:
                logging.error('Instance %s has to many clients for service %s.' % (obj, s))
                return False

        return True

