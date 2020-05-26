"""
Description
-----------

Implements parser, model and lib for ROS2 use case

:Authors:
    - Johannes Schlatow

"""
try:
    from lxml import etree as ET
except ImportError:
    from xml.etree import ElementTree as ET

import logging

from mcc.graph import GraphObj, Edge
from mcc.parser import XMLParser
from mcc.framework import *
from mcc.backtracking import BacktrackRegistry
from mcc.importexport import PickleExporter

from ortools.sat.python import cp_model


class Repository(XMLParser):

    class Callback:
        def __init__(self, cbtype, name, trigger, wcet, publishes, prio, wcrt, hid=None):
            self.cbtype    = cbtype
            self.name      = name
            self.trigger   = trigger
            self.wcet      = wcet
            self.publishes = publishes
            self.prio      = prio
            self.wcrt      = wcrt
            self.hid       = hid

        def is_subscriber(self, topic):
            return self.cbtype == "subscriber_callback" and self.trigger == topic

        def is_publisher(self, topic):
            return topic in self.publishes

        def label(self):
            if self.name is not None:
                return "%s:%s" % (self.cbtype, self.name)
            else:
                return self.cbtype

        def __repr__(self):
            return self.label()

    class Handler:
        def __init__(self, etype, name, wcet, wcrt):
            self.etype = etype
            self.name  = name
            self.wcet  = wcet
            self.wcrt  = wcrt

        def label(self):
            return self.name

        def __repr__(self):
            return self.label()

    class Topic:
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return self.name

        def __eq__(self, rhs):
            if isinstance(rhs, ImmutableParam):
                return rhs == self

            if not isinstance(rhs, Repository.Topic):
                return False
            return self.name == rhs.name

        def __hash__(self):
            return hash(self.name)


    class RosNode:
        def __init__(self, xml_node, repo):
            self.repo = repo
            self.xml_node = xml_node

        def subscribes(self):
            topics = set()
            for s in self.xml_node.findall("./subscribes/topic"):
                topics.add(Repository.Topic(s.get('name')))

            return topics

        def publishes(self):
            topics = set()
            for s in self.xml_node.findall("./publishes/topic"):
                topics.add(Repository.Topic(s.get('name')))

            return topics

        def callbacks(self):
            cbs = set()
            for c in self.xml_node.findall('./callbacks/*'):
                cbtype = c.tag
                name    = c.get('name')
                wcet    = int(c.get('wcet_us'))
                prio    = int(c.get('prio'))
                wcrt    = int(c.get('wcrt_us'))
                if c.tag == 'timer_callback':
                    trigger = int(c.get('period_ms'))
                else:
                    trigger = Repository.Topic(c.get('topic'))

                pubs = set()
                for p in c.findall('./publish'):
                    pubs.add(Repository.Topic(p.get('topic')))

                hid = c.get('exception_handler')

                cbs.add(Repository.Callback(cbtype=cbtype, name=name, trigger=trigger, wcet=wcet,
                                            publishes=pubs, wcrt=wcrt, prio=prio, hid=hid))

            return cbs

        def handlers(self):
            ehs = set()
            for h in self.xml_node.findall('./exception_handlers/handler'):
                name    = h.get('id')
                wcet    = int(h.get('wcet_us'))
                wcrt    = int(h.get('wcrt_us'))
                etype   = h.get('type')

                ehs.add(Repository.Handler(etype=etype, name=name, wcet=wcet, wcrt=wcrt))

            return ehs

        def label(self):
            if hasattr(self, 'name'):
                return self.name

            name = self.xml_node.get('name')
            assert name is not None
            return name

        def __repr__(self):
            return self.label()

        def __setstate__(self, state):
            self.name = state

        def __getstate__(self):
            return (self.label())

    class NodeNotFoundError(Exception):
        pass

    def __init__(self, config_model_file, xsd_file=None):
        XMLParser.__init__(self, config_model_file, xsd_file)

        if self._file is not None:
            # find <repository>
            if self._root.tag != "repository":
                self._root = self._root.find("repository")
                if self._root == None:
                    raise self.NodeNotFoundError("Cannot find <repository> node.")

    def find_rosnode_by_name(self, name):
        node = self._root.find("./rosnode[@name='%s']" % name)
        assert node is not None, "Node %s not in repository" % name
        return Repository.RosNode(node, self)


class ChildQuery:
    def __init__(self, xml_node):
        self._root      = xml_node

        self._parse()

    def _parse(self):
        self._identifier = self._root.get('name')
        self._ecu        = self._root.get('ecu')

        n = self._root.find('rosnode')
        if n is not None:
            self._queryname = n.get('name')

    def identifier(self):
        return self._identifier

    def label(self):
        if self._identifier is not None:
            return self._identifier
        else:
            return self._queryname

    def ecu(self):
        return self._ecu

    def query(self):
        return self._queryname

    def __repr__(self):
        return self.label()

    def __getstate__(self):
        return ( self._identifier,
                 self._queryname,
                 self._ecu)

    def __setstate__(self, state):
        self._identifier, self._queryname, self._ecu = state


class SystemParser:
    class NodeNotFoundError(Exception):
        pass

    class Requirement:
        class Event:
            def __init__(self, etype, topic):
                self.etype = etype
                if isinstance(topic, str):
                    self.topic = Repository.Topic(topic)
                else:
                    assert isinstance(topic, Repository.Topic)
                    self.topic = topic

            def match(self, callback):
                if self.etype == 'receive':
                    return callback.is_subscriber(self.topic)
                elif self.etype == 'publish':
                    return callback.is_publisher(self.topic)

            def __repr__(self):
                return '%s %s' % (self.etype, self.topic)

        def __init__(self, xml_node):
            self.xml_node = xml_node
            self.name = self.xml_node.get('name')

        def latency(self):
            return int(self.xml_node.get('max_latency_us'))

        def events(self):
            result = list()
            for ev in self.xml_node.findall('./*'):
                result.append(self.Event(etype=ev.tag,
                                         topic=ev.get('topic')))

            return result

        def __repr__(self):
            if self.name is not None:
                return self.name
            else:
                return 'n/a'

        def __setstate__(self, state):
            self.name = state

        def __getstate__(self):
            return (self.name)


    def __init__(self, xml_file, xsd_file=None):
        XMLParser.__init__(self, xml_file, xsd_file)

        if self._file is not None:
            # find <system>
            if self._root.tag != "system":
                self._root = self._root.find("system")
                if self._root == None:
                    raise self.NodeNotFoundError("Cannot find <system> node.")

    def name(self):
        res = self._root.get('name')
        if res is None:
            res = ''

        return res

    def children(self):
        result = set()
        for c in self._root.findall('child'):
            result.add(ChildQuery(c))

        return result

    def requirements(self):
        return [self.Requirement(n) for n in self._root.findall('./requirements/chain')]

class CallbackEngine(AnalysisEngine):
    def __init__(self, layer, target_layer):
        acl = { layer        : { 'reads'  : set(['mapping', 'topic']) },
                target_layer : { 'writes' : set(['mapping', 'handler', 'topic'])}}
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)

        self.target_layer = target_layer

    def transform(self, obj, target_layer):
        """ insert callbacks (with handlers as params)
            and connect callbacks accordingly
        """
        if isinstance(obj, Edge):
            topic = self.layer.get_param_value(self, 'topic', obj)
            source_node = obj.source
            target_node = obj.target

            source_callbacks = self.layer.associated_objects(self.target_layer.name, source_node)
            target_callbacks = self.layer.associated_objects(self.target_layer.name, target_node)

            publisher = None
            subscriber = None

            # find subscribing callback
            for s in source_callbacks:
                # this can probably be untracked access
                if s.untracked_obj().is_subscriber(topic):
                    # track access
                    s.obj(self.target_layer)
                    subscriber = s
                    break
            assert subscriber is not None

            # find publishing callback
            for t in target_callbacks:
                # this can probably be untracked access
                if t.untracked_obj().is_publisher(topic):
                    # track access
                    t.obj(self.target_layer)
                    publisher = t
                    break
            assert publisher is not None

            return GraphObj(Edge(publisher, subscriber), params={ 'topic' : topic })

        else:
            # get mapping
            mapping = self.layer.get_param_value(self, 'mapping', obj)

            # get rosnode
            rosnode = obj.obj(self.layer)

            # parse callbacks
            callbacks = rosnode.callbacks()

            # parse handlers
            handlers  = rosnode.handlers()

            graph_objs = set()
            for cb in callbacks:
                params = { 'mapping' : mapping }
                if cb.hid is not None:
                    for h in handlers:
                        if h.name == cb.hid:
                            params['handler'] = h
                            break
                    assert 'handler' in params
                graph_objs.add(GraphObj(Layer.Node(cb), params=params))

            return graph_objs

    def target_types(self):
        return tuple({Repository.Callback})

class SegmentEngine(AnalysisEngine):

    class Segment:
        def __init__(self, requirement=None):
            self.node = Layer.Node(self)
            if requirement is not None:
                self._requirements = {requirement}
            else:
                self._requirements = {}

        def label(self):
            return '%s' % self._requirements

        def __repr__(self):
            return self.label()

        def add_requirement(self, req):
            self._requirements.add(req)

        def match_requirement(self, req):
            return req in self._requirements

        def requirements(self):
            return self._requirements

        def dummy(self):
            return not self._requirements

    def __init__(self, layer, target_layer, query):
        acl = { layer        : { 'reads'  : set(['mapping', 'topic', 'handler']) },
                target_layer : { 'writes' : set(['mapping'])}}
        AnalysisEngine.__init__(self, layer, param='segment', acl=acl)

        self.target_layer = target_layer
        self.query        = query

    def _sources(self, start, objects):
        if start is None:
            return objects
        else:
            return [e.source for e in self.layer.in_edges(start)]

    def batch_map(self, data):
        segments = dict()
        objects = data.keys()
        for req in self.query.requirements():
            segments[req] = [self.Segment(req)]

            last = None
            for ev in reversed(req.events()):
                for t in self._sources(last, objects):
                    cb = t.obj(self.layer)
                    if ev.match(cb):
                        new_segment = False
                        if last is not None and \
                           self.layer.get_param_value(self, 'mapping', last) != \
                           self.layer.get_param_value(self, 'mapping', t):
                            new_segment = True

                        # TODO also check forks/joins

                        if new_segment and data[t] is None:
                            segments[req].append(self.Segment(req))

                        last = t
                        if data[last] is not None:
                            data[last].add_requirement(req)
                        else:
                            data[last] = segments[req][-1]

                        # FIXME do not split for every exception handler
                        if cb.hid is not None:
                            segments[req].append(self.Segment(req))

                        break
                    else:
                        print("%s does not match %s" % (cb, ev))

        dummy = self.Segment()
        for obj in objects:
            if data[obj] is None:
                logging.info("Callback %s is not in any chain." % obj.untracked_obj())
                data[obj] = {dummy}
            else:
                data[obj] = {data[obj]}

        return data

    def assign(self, obj, candidates):
        return list(candidates)[0]

    def transform(self, obj, target_layer):
        if isinstance(obj, Edge):
            source = obj.source
            target = obj.target
            src_segment = self.layer.get_param_value(self, 'segment', source)
            trg_segment = self.layer.get_param_value(self, 'segment', target)
            if src_segment == trg_segment or trg_segment.dummy() or src_segment.dummy():
                return set()
            else:
                return Edge(src_segment.node, trg_segment.node)
        else:
            return GraphObj(self.layer.get_param_value(self, 'segment', obj).node,
                            params={'mapping' : self.layer.get_param_value(self, 'mapping', obj)})

    def target_types(self):
        return tuple({self.Segment})


class ExceptionEngine(AnalysisEngine):
    def __init__(self, layer, parent_layer):
        acl = { parent_layer : { 'reads' : set(['handler'])}}
        AnalysisEngine.__init__(self, layer, param='handler', acl=acl)

        self.parent_layer = parent_layer

    def has_predecessor_in_segment(self, cb, parents):
        result = False
        for e in self.parent_layer.in_edges(cb):
            if e.source in parents:
                return True

        return False

    def map(self, obj, candidates):
        assert not isinstance(obj, Edge)

        # assign handler of next segment to segment
        handler = None
        for e in self.layer.out_edges(obj):
            parents = self.layer.associated_objects(self.parent_layer.name, e.target)
            for p in parents:
                if not self.has_predecessor_in_segment(p, parents):
                    handler = self.parent_layer.get_param_value(self, 'handler', p)
                    if handler is None:
                        return {}

        return {handler}

    def assign(self, obj, candidates):
        return list(candidates)[0]

    def check(self, obj):
        assert not isinstance(obj, Edge)

        if len(list(self.layer.out_edges(obj))) > 0:
            if self.layer.get_param_value(self, 'handler', obj) is None:
                return False

        # FIXME also check fork/join constraints

        return True


class WcrtEngine(AnalysisEngine):
    def __init__(self, layer, parent_layer):
        AnalysisEngine.__init__(self, layer, param='wcrt')

        self.parent_layer = parent_layer

    def map(self, obj, candidates):
        # sum up WCRTs of callbacks (but only WCET of first callback)
        wcrt = 0
        parents = self.layer.associated_objects(self.parent_layer.name, obj)
        for p in parents:
            has_predecessor_in_segment = False
            for e in self.parent_layer.in_edges(p):
                if e.source in parents:
                    has_predecessor_in_segment = True

            # FIXME distinguish whether chain starts with receive or publish event
            if has_predecessor_in_segment:
                wcrt += p.obj(self.parent_layer).wcrt
            else:
                wcrt += p.obj(self.parent_layer).wcet

        return {wcrt}

    def assign(self, obj, candidates):
        return list(candidates)[0]


class BudgetEngine(AnalysisEngine):
    def __init__(self, layer):
        acl = { layer        : { 'reads' : {'wcrt', 'handler'}}}
        AnalysisEngine.__init__(self, layer, param='budget', acl=acl)

    def batch_map(self, data):
        # segment wcrt + exception wcrt must be below overall latency requirement
        chains = dict()

        # collect chains and their segments
        for obj in data.keys():
            segment = obj.obj(self.layer)
            for chain in segment.requirements():
                if chain not in chains:
                    chains[chain] = set()

                chains[chain].add(obj)

        model = cp_model.CpModel()
        MAX_BUDGET = 1000000000

        budgets = dict()
        min_budgets = dict()
        for chain, objects in chains.items():
            # variables and constraint for minimum budget
            first = None
            for obj in objects:
                budgets[obj] = model.NewIntVar(0, MAX_BUDGET, '%s' % obj)
                min_budgets[obj] = self.layer.get_param_value(self, 'wcrt', obj).copy()
                model.Add(budgets[obj] >= min_budgets[obj])

                if len(list(self.layer.in_edges(obj))) == 0:
                    first = obj

            assert first is not None

            # constraints for exception handling
            handler = self.layer.get_param_value(self, 'handler', first)
            current = first
            predecessors = list()
            while handler is not None:
                predecessors.append(current)
                model.Add(sum([budgets[x] for x in predecessors]) <= chain.latency() - handler.wcrt)

                for e in self.layer.out_edges(current):
                    if e.target in objects:
                        current = e.target
                        break
                handler = self.layer.get_param_value(self, 'handler', current)

        # objective function
        # FIXME implement reasonable slack distribution
        model.Maximize(sum([budgets[x] - min_budgets[x] for x in budgets.keys()]))

        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        if status == cp_model.OPTIMAL:
            for obj in data.keys():
                if obj not in budgets:
                    data[obj] = {0}
                else:
                    val = solver.Value(budgets[obj])
                    if val == MAX_BUDGET:
                        val = 0
                    data[obj] = {val}

        return data

    def assign(self, obj, candidates):
        return list(candidates)[0]


class CrossLayerModel(BacktrackRegistry):
    """ Our cross-layer model.
    """
    def __init__(self, repo):
        super().__init__()
        self.add_layer(Layer('nodes',     nodetypes={Repository.RosNode}))
        self.add_layer(Layer('callbacks',  nodetypes={Repository.Callback}))
        self.add_layer(Layer('segments',   nodetypes={SegmentEngine.Segment}))

        self.repo = repo

    def from_query(self, query_model, name='nodes'):
        q = self.by_name[name]
        self.reset(q)

        # insert nodes
        node_lookup = dict()
        for child in query_model.children():
            node_lookup[child.query()] = self._insert_query(child, q)

        # insert edges
        for o1 in node_lookup.values():
            rosnode = o1.untracked_obj()
            for topic in rosnode.subscribes():
                found = False
                for node in [o2.untracked_obj() for o2 in node_lookup.values() if o2 is not o1]:
                    if topic in node.publishes():
                        found = True
                        e = q.graph.create_edge(node_lookup[rosnode.label()], node_lookup[node.label()])
                        q.untracked_set_param_value('topic', e, topic)

                assert found, "Publisher of topic %s not found" % topic

    def _insert_query(self, child, layer):
        rosnode = self.repo.find_rosnode_by_name(child.query())
        assert rosnode, "Query of %s invalid" % child.query()
        node = layer._add_node(Layer.Node(rosnode))

        # set pre-defined mapping
        if child.ecu() is not None:
            layer.untracked_set_param_candidates('mapping', node, set([child.ecu()]))
            layer.untracked_set_param_value('mapping', node, child.ecu())

        return node

class MccBase:
    def __init__(self, repo, chronologicaltracking=False):
        self._repo = repo
        self._nonchronological = not chronologicaltracking

    def _to_callbacks(self, model):
        source_layer = model.by_name['nodes']
        target_layer = model.by_name['callbacks']
        ce = CallbackEngine(layer=source_layer,
                            target_layer=target_layer)

        model.add_step(NodeStep(Transform(ce, target_layer, 'transform to callbacks')))
        model.add_step(EdgeStep(Transform(ce, target_layer, 'connect callbacks')))

    def _to_segments(self, model, query):
        # transform callbacks into segments
        source_layer = model.by_name['callbacks']
        target_layer = model.by_name['segments']
        se = SegmentEngine(layer=source_layer,
                           target_layer=target_layer,
                           query=query)

        step = NodeStep(BatchMap(se, 'define segments'))
        step.add_operation(Assign(se, 'define segments'))
        step.add_operation(Transform(se, target_layer, 'transform to segments'))
        model.add_step(step)
        model.add_step(EdgeStep(Transform(se, target_layer, 'connect segments')))

        ee = ExceptionEngine(target_layer, parent_layer=source_layer)
        step = NodeStep(Map(ee, 'assign handler'))
        step.add_operation(Assign(ee, 'assign handler'))
        step.add_operation(Check(ee,  'check segments'))
        model.add_step(step)

    def _assign_budgets(self, model):
        layer   = model.by_name['segments']
        cblayer = model.by_name['callbacks']

        # first calculate minimum required budget of segments
        we = WcrtEngine(layer, parent_layer=cblayer)
        step = NodeStep(Map(we, 'calculate WCRTs'))
        step.add_operation(Assign(we, 'calculate WCRTs'))
        model.add_step(step)

        # assign budgets
        be = BudgetEngine(layer)
        step = NodeStep(BatchMap(be, 'calculate budgets'))
        step.add_operation(Assign(we, 'calculate budgets'))
        model.add_step(step)

    def _export_config(self):
        # TODO generate configuration files
        raise NotImplementedError

    def search_config(self, query, outpath=None, dot_mcc=True):
        """ Searches a system configuration for the given query.
        """

        # check function/composite/component references, compatibility and routes in system and subsystems

        # 1) we create a new system model
        model = CrossLayerModel(self._repo)

        # 2) create system model from query
        model.from_query(query)

        # 3) transform into callbacks
        self._to_callbacks(model)

        # 4) split into segments
        self._to_segments(model, query)

        # 5) assign latency budgets
        self._assign_budgets(model)

#        # 6) export config
#        self._export_config()

        if outpath is not None and dot_mcc:
            model.write_dot(outpath+'mcc.dot')

        try:
            model.execute(outpath, nonchronological=self._nonchronological)
        except Exception as e:
            print(e)
            export = PickleExporter(model)
            export.write(outpath+'model-error.pickle')
            raise e

        export = PickleExporter(model)
        export.write(outpath+'model.pickle')

        return model
