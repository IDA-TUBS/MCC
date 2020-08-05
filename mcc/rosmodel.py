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
import yaml

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

            if isinstance(rhs, str):
                return self.name == rhs

            if not isinstance(rhs, Repository.Topic):
                return False
            return self.name == rhs.name

        def __hash__(self):
            return hash(self.name)


    class RosNode:
        def __init__(self, xml_node, repo):
            self.repo = repo
            self.xml_node = xml_node

        def commands(self):
            return [cmd.text for cmd in self.xml_node.findall('./start/command')]

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

        def has_event(self, etype, topic):
            for ev in self.events():
                if ev.etype == etype and ev.topic == topic:
                    return True

            return False

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
        def __init__(self, requirement=None, network=False):
            self.node = Layer.Node(self)
            self.requirement = requirement
            self.network=network

        def label(self):
            return '%s' % self.requirement

        def __repr__(self):
            return self.label()

        def dummy(self):
            return not self.requirement

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

                        if new_segment:
                            segments[req].append(self.Segment(req))

                        last = t
                        if data[last] is None:
                            data[last] = set()
                        data[last].add(segments[req][-1])

                        break
                    else:
                        print("%s does not match %s" % (cb, ev))

        dummy = self.Segment()
        for obj in objects:
            if data[obj] is None:
                logging.info("Callback %s is not in any chain." % obj.untracked_obj())
                data[obj] = {frozenset({dummy})}
            else:
                data[obj] = {frozenset(data[obj])}

        return data

    def assign(self, obj, candidates):
        return list(candidates)[0]

    def transform(self, obj, target_layer):
        if isinstance(obj, Edge):
            source = obj.source
            target = obj.target
            src_segments = self.layer.get_param_value(self, 'segment', source)
            trg_segments = self.layer.get_param_value(self, 'segment', target)
            edges = set()
            for src_segment in src_segments:
                for trg_segment in trg_segments:
                    if trg_segment.requirement == src_segment.requirement:
                        if trg_segment != src_segment and not trg_segment.dummy() and not src_segment.dummy():
                            edges.add(Edge(src_segment.node, trg_segment.node))

            return edges
        else:
            graph_objs = set()
            segments = self.layer.get_param_value(self, 'segment', obj)
            for segment in segments:
                mapping = self.layer.get_param_value(self, 'mapping', obj) if not segment.network else None
                graph_objs.add(GraphObj(segment.node, params={'mapping' : mapping}))

            return graph_objs

    def target_types(self):
        return tuple({self.Segment})

class NetworkEngine(AnalysisEngine):

    def __init__(self, layer, target_layer):
        acl = { layer        : { 'reads'  : set(['mapping'])},
                target_layer : { 'writes' : set(['mapping'])}}
        AnalysisEngine.__init__(self, layer, param='netsegment', acl=acl)

        self.target_layer = target_layer

    def map(self, obj, candidates):

        assert isinstance(obj, Edge)

        src_mapping = self.layer.get_param_value(self, 'mapping', obj.source)
        trg_mapping = self.layer.get_param_value(self, 'mapping', obj.target)

        if src_mapping != trg_mapping:
            return {SegmentEngine.Segment(obj.source.obj(self.layer).requirement, True)}

        return {None}

    def assign(self, obj, candidates):
        assert isinstance(obj, Edge)
        return list(candidates)[0]

    def transform(self, obj, target_layer):
        assert isinstance(obj, Edge)

        segment = self.layer.get_param_value(self, 'netsegment', obj)
        if segment is not None:
            graph_objs = {GraphObj(segment.node, params={ 'mapping' : 'Network'})}
            graph_objs.add(Edge(obj.source, segment.node))
            graph_objs.add(Edge(segment.node, obj.target))
            return graph_objs
        else:
            return obj

    def target_types(self):
        return tuple({SegmentEngine.Segment})


class ExceptionEngine(AnalysisEngine):
    def __init__(self, layer, parent_layers):
        acl = { parent_layers[-1] : { 'reads' : set(['handler'])}}
        AnalysisEngine.__init__(self, layer, param='handler', acl=acl)

        self.parent_layers = parent_layers

    def indirect_parents(self, node):
        cur_layer = self.layer
        parent_list = [{node}]
        for layer in self.parent_layers:
            parent_list.append(set())
            for n in parent_list[-2]:
                if isinstance(n, Edge): continue
                parent_list[-1].update(cur_layer.associated_objects(layer.name, n))
            cur_layer = layer

        return parent_list[-1]

    def has_predecessor_in_segment(self, cb, parents, parent_layer):
        result = False
        for e in parent_layer.in_edges(cb):
            if e.source in parents:
                return True

        return False

    def has_successor_in_segment(self, cb, parents, parent_layer):
        result = False
        for e in parent_layer.out_edges(cb):
            if e.target in parents:
                print(e.target)
                return True

        return False

    def map(self, obj, candidates):
        assert not isinstance(obj, Edge)

        # if network segment: assign first handler of next segment
        # else: assign last handler within segment
        # FIXME currently, we do not distinguish whether a handler handles the late receive or late publish event
        handler = set()

        if not obj.obj(self.layer).network:
            parents = self.indirect_parents(obj)
            for p in parents:
                if not self.has_successor_in_segment(p, parents, self.parent_layers[-1]):
                    if not self.parent_layers[-1].isset_param_value(self, 'handler', p):
                        logging.error("Monitoring gap: Callback %s has no handler." % p)
                    else:
                        tmp = self.parent_layers[-1].get_param_value(self, 'handler', p)
                        handler.add(tmp)
        else:
            for e in self.layer.out_edges(obj):
                parents = self.indirect_parents(e.target)
                for p in parents:
                    if not self.has_predecessor_in_segment(p, parents, self.parent_layers[-1]):
                        if not self.parent_layers[-1].isset_param_value(self, 'handler', p):
                            logging.error("Monitoring gap: Callback %s has no handler." % p)
                        else:
                            tmp = self.parent_layers[-1].get_param_value(self, 'handler', p)
                            handler.add(tmp)

        return {frozenset(handler)}

    def assign(self, obj, candidates):
        return list(candidates)[0]

    def check(self, obj):
        assert not isinstance(obj, Edge)

        if len(list(self.layer.out_edges(obj))) > 0:
            if not self.layer.get_param_value(self, 'handler', obj):
                return False

        # FIXME also check fork/join constraints

        return True


class WcrtEngine(AnalysisEngine):
    def __init__(self, layer, parent_layers, net_delay_us=3500):
        AnalysisEngine.__init__(self, layer, param='wcrt')

        self.parent_layers = parent_layers
        self.net_delay_us = net_delay_us

    def indirect_parents(self, node):
        cur_layer = self.layer
        parent_list = [{node}]
        for layer in self.parent_layers:
            parent_list.append(set())
            for n in parent_list[-2]:
                if isinstance(n, Edge): continue
                parent_list[-1].update(cur_layer.associated_objects(layer.name, n))
            cur_layer = layer

        return parent_list[-1]

    def map(self, obj, candidates):

        wcrt = 0
        if obj.obj(self.layer).network:
            # we assume network segments have a constant WCRT
            wcrt = self.net_delay_us

        elif not obj.obj(self.layer).dummy():
            # sum up WCRTs of callbacks

            parents = self.indirect_parents(obj)
            for p in parents:
                # FIXME distinguish whether chain starts with receive or publish event
                wcrt += p.obj(self.parent_layers[-1]).wcrt

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
            if segment.dummy():
                continue
            chain = segment.requirement
            if chain not in chains:
                chains[chain] = set()

            chains[chain].add(obj)

        model = cp_model.CpModel()
        MAX_BUDGET = 1000000000

        budgets = dict()
        min_budgets = dict()
        slack = model.NewIntVar(0, MAX_BUDGET, 'Slack')
        for chain, objects in chains.items():
            # variables and constraint for minimum budget
            first = None
            for obj in objects:
                budgets[obj] = model.NewIntVar(0, MAX_BUDGET, '%s' % obj)
                min_budgets[obj] = self.layer.get_param_value(self, 'wcrt', obj).copy()
                if obj.obj(self.layer).network:
                    # do not add complete slack to network segments
                    model.Add(budgets[obj] >= min_budgets[obj])
                else:
                    model.Add(budgets[obj] >= min_budgets[obj] + slack)

                if len(list(self.layer.in_edges(obj))) == 0:
                    first = obj

            assert first is not None

            # FIXME the last segment is not monitorable but the budget is calculated as if it would be monitored
            #       (the ConfigEngine will subtract the WCRT of the last callback from the budget of the last segment)

            # constraints for exception handling
            current = first
            predecessors = list()
            local_predecessors = None
            while current:
                predecessors.append(current)

                handlers = self.layer.get_param_value(self, 'handler', current)
                for handler in handlers:
                    model.Add(sum([budgets[x] for x in predecessors]) <= chain.latency() - handler.wcrt)

                tmp = current
                current = None
                for e in self.layer.out_edges(tmp):
                    if e.target in objects:
                        current = e.target
                        break

        # objective function
        # FIXME implement reasonable slack distribution
        model.Maximize(slack)

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

class ConfigEngine(AnalysisEngine):
    def __init__(self, model, ecus, outpath):
        acl = { model.by_name['nodes']    : { 'reads' : {'mapping'}},
                model.by_name['netsegments'] : { 'reads' : {'mapping', 'handler', 'budget'}}}
        AnalysisEngine.__init__(self, model.by_name['netsegments'], param=None, acl=acl)

        self.model = model
        self.outpath = outpath
        self.ecus = ecus

    def _indirect_parents(self, node, layer, parent_layers):
        cur_layer = layer
        parent_list = [{node}]
        for layer in parent_layers:
            parent_list.append(set())
            for n in parent_list[-2]:
                if isinstance(n, Edge): continue
                parent_list[-1].update(cur_layer.associated_objects(layer.name, n))
            cur_layer = layer

        return parent_list[-1]

    def _determine_earliest_event(self, cb, chain):
        # take subscription of callback if present
        # else: take published topic of callback
        clayer = self.model.by_name['callbacks']
        nlayer = self.model.by_name['nodes']

        topic  = None
        node   = None
        action = None
        head_wcrt = 0
        if cb.obj(clayer).cbtype == "subscriber_callback":
            action = 'subscribe'
            topic = cb.obj(clayer).trigger
            assert chain.has_event('receive', topic.name)
            topic = topic.name.split('/')[-1]
        else:
            action = 'publish'
            for t in cb.obj(clayer).publishes:
                if chain.has_event('publish', t.name):
                    topic = t.name.split('/')[-1]
            head_wcrt = cb.obj(clayer).wcrt

        for p in clayer.associated_objects(nlayer.name, cb):
            assert node is None, 'node already set: %s' % node
            node = p.obj(nlayer)

        return action, topic, node, head_wcrt

    def _determine_latest_event(self, cb, chain):
        # take published topic of callback if present
        # else: take subscription of callback
        clayer = self.model.by_name['callbacks']
        nlayer = self.model.by_name['nodes']

        topic  = None
        node   = None
        action = None
        tail_wcrt = 0
        if len(cb.obj(clayer).publishes) > 0:
            action = 'publish'
            for t in cb.obj(clayer).publishes:
                if chain.has_event('publish', t.name):
                    topic = t.name.split('/')[-1]
        else:
            assert cb.obj(clayer).cbtype == 'subscriber_callback'
            action = 'subscribe'
            topic = cb.obj(clayer).trigger
            assert chain.has_event('receive', topic.name)
            tail_wcrt = cb.obj(clayer).wcrt

        for p in clayer.associated_objects(nlayer.name, cb):
            assert node is None, 'node already set: %s' % node
            node = p.obj(nlayer)

        return action, topic, node, tail_wcrt

    def _find_handling_callback(self, segment, handler):
        clayer = self.model.by_name['callbacks']
        slayer   = self.model.by_name['segments']
        netlayer = self.model.by_name['netsegments']

        for cb in self._indirect_parents(segment, netlayer, [slayer, clayer]):
            if cb.obj(clayer).hid == handler.name:
                return cb

        return None

    def _find_first_callback(self, segment):
        clayer   = self.model.by_name['callbacks']
        slayer   = self.model.by_name['segments']
        netlayer = self.model.by_name['netsegments']

        parents = self._indirect_parents(segment, netlayer, [slayer,clayer])
        for cb in parents:
            if not len(list(clayer.in_edges(cb))):
                return cb
            for e in clayer.in_edges(cb):
                if e.source not in parents:
                    return cb

        return None

    def _find_period_us(self, segment):
        clayer = self.model.by_name['callbacks']
        slayer = self.model.by_name['segments']
        netlayer = self.model.by_name['netsegments']

        pred = list(netlayer.in_edges(segment))[0].source
        buf = self._indirect_parents(pred, netlayer, [slayer, clayer])
        cb = buf.pop()
        while cb:
            if len(list(clayer.in_edges(cb))) == 0:
                assert cb.obj(clayer).cbtype == "timer_callback"
                return cb.obj(clayer).trigger * 1000
            else:
                buf.update([e.source for e in clayer.in_edges(cb)])
            cb = buf.pop()

        return None

    def _write_startnodes(self, ecu, rosnodes):
        root = ET.Element("rosnodes")
        for rosnode in rosnodes:
            for cmd in rosnode.commands():
                ET.SubElement(root, "rosnode", command=cmd)

        tree = ET.ElementTree(root)
        tree.write('%srosnodes-%s.xml' % (self.outpath, ecu), pretty_print=True)

    def _baretopic(self, topic):
        if topic[0] == '/':
            return topic[1:]
        else:
            return topic

    def _write_monitor_yaml(self, ecu, segments, budgets, cid, sid):
        slayer = self.model.by_name['netsegments']
        nlayer = self.model.by_name['nodes']
        clayer = self.model.by_name['callbacks']
        ecunodes = dict()

        for s in segments:
            for h in slayer.get_param_value(self, 'handler', s):
                # find latest event for the callback of this handler
                cb = self._find_handling_callback(s, h)
                assert cb is not None
                action, topic, node, tail_wcrt = self._determine_latest_event(cb, s.obj(slayer).requirement)
                nodename = node.label()

                # configure owned segment
                if nodename not in ecunodes:
                    ecunodes[nodename] = dict()

                config = { 'id'     : sid[s],
                           'topic'  : '%s' % topic,
                           'action' : action,
                           'budget' : budgets[s] - tail_wcrt,
                           'type1'  : h.etype == 'type1',
                           'type2'  : h.etype == 'type2' }

                # find the earliest monitorable event in this segment
                cb = self._find_first_callback(s)
                assert cb is not None, 'cannot find first callback in %s ' % s
                action, topic, node, head_wcrt = self._determine_earliest_event(cb, s.obj(slayer).requirement)

                # remove head_wcrt from budget if earliest event is a publish event
                if head_wcrt > 0:
                    config['budget'] -= head_wcrt

                # skip if start event = end event
                if action == config['action'] and self._baretopic(topic) == self._baretopic(config['topic']) and nodename == node.label():
                    continue

                ecunodes[nodename]['id'] = cid[node]

                if 'owned_segments' not in ecunodes[nodename]:
                    ecunodes[nodename]['owned_segments'] = list()

                ecunodes[nodename]['owned_segments'].append(config)
                nodename = node.label()

                # configure publisher segment
                if nodename not in ecunodes:
                    ecunodes[nodename] = dict()

                if 'triggered_segments' not in ecunodes[nodename]:
                    ecunodes[nodename]['triggered_segments'] = list()

                config = { 'id'       : sid[s],
                           'topic'    : '%s' % topic,
                           'action'   : action,
                           'consumer' : cid[node] }
                ecunodes[nodename]['triggered_segments'].append(config)


        # set priorities of all nodes
        for o in nlayer.nodes():
            if nlayer.get_param_value(self, 'mapping', o).copy() != ecu:
                continue

            max_prio = 0
            for cb in nlayer.associated_objects(clayer.name, o):
                max_prio = max(max_prio, cb.obj(clayer).prio)

            rosnode = o.obj(nlayer)
            name = rosnode.label()
            if name not in ecunodes:
                ecunodes[name] = dict()

            ecunodes[name]['monitor_priority']  = 90
            ecunodes[name]['executor_priority'] = max_prio

        # write yaml
        with open('%sDEFAULT_MONITOR_CONFIG-%s.yaml' % (self.outpath, ecu), 'w') as file:
            yaml.dump(ecunodes, file)

    def _write_qos_xml(self, ecu, segments):
        slayer = self.model.by_name['netsegments']

        dds = ET.Element("dds", xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles")
        profiles = ET.SubElement(dds, 'profiles')
        added_profiles = set()
        for s in segments:
            chain = s.obj(slayer).requirement
            handlers = slayer.get_param_value(self, 'handler', s)
            budget   = slayer.get_param_value(self, 'budget', s).copy()
            period   = self._find_period_us(s)

            for h in handlers:
                next_seg = list(slayer.out_edges(s))[0].target
                action, topic, node, head_wcrt = self._determine_earliest_event(
                        self._find_handling_callback(next_seg, h), chain)
                if action == 'subscribe':
                    profile = '%s/%s' % (node.label(), topic)

                if profile in added_profiles:
                    continue

                added_profiles.add(profile)

                sub = ET.SubElement(profiles, 'subscriber', profile_name=profile, is_default_profile='false')
                mon = ET.SubElement(sub, 'monitoring', implementation_type='sync')
                if h.etype == 'type1':
                    ET.SubElement(mon, 'type1_enable').text = 'true'
                    ET.SubElement(mon, 'type2_enable').text = 'false'
                else:
                    ET.SubElement(mon, 'type1_enable').text = 'false'
                    ET.SubElement(mon, 'type2_enable').text = 'true'


                latency = budget
                latency_us = latency % 1000000
                latency_s  = int(latency / 1000000)
                lat = ET.SubElement(mon, 'monitoring_latency')
                ET.SubElement(lat, 'sec').text = str(latency_s)
                ET.SubElement(lat, 'nanosec').text = str(latency_us * 1000)

                period_us = period % 1000000
                period_s  = int(period / 1000000)
                per = ET.SubElement(mon, 'monitoring_period')
                ET.SubElement(per, 'sec').text = str(period_s)
                ET.SubElement(per, 'nanosec').text = str(period_us * 1000)

        tree = ET.ElementTree(dds)
        tree.write("%sDEFAULT_FASTRTPS_PROFILES-%s.xml" % (self.outpath, ecu), pretty_print=True)

    def batch_check(self, objects):
        nodes_layer    = self.model.by_name['nodes']
        segments_layer = self.model.by_name['netsegments']

        # extract nodes to start from nodes layer
        rosnodes = dict()
        for ecu in self.ecus:
            rosnodes[ecu] = set()

        for o in nodes_layer.nodes():
            ecu = nodes_layer.get_param_value(self, 'mapping', o)
            if ecu not in rosnodes:
                rosnodes[ecu] = set()
                print("%s not in %s" % (ecu, rosnodes))

            rosnodes[ecu].add(o.obj(nodes_layer))

        # output XML
        for ecu, nodes in rosnodes.items():
            self._write_startnodes(ecu, nodes)

        # define consumer id for every rosnode
        consumers = dict()
        cid = 1
        for ecu, nodes in rosnodes.items():
            for n in nodes:
                consumers[n] = cid
                cid += 1

        # extract segments to monitor from segments layer
        #     - every segment with set handler and budget > 0 gets a segment id
        #     - if next segment is on different ECU, do inter-ECU
        inter_segments = dict()
        intra_segments = dict()
        budgets = dict()
        for o in segments_layer.nodes():
            if not len(segments_layer.get_param_value(self, 'handler', o).copy()):
                continue
            budget = segments_layer.get_param_value(self, 'budget', o).copy()
            if budget == 0:
                continue

            segment = o.obj(segments_layer)
            budgets[o] = budget

            if segment.network:
                for e in segments_layer.out_edges(o):
                    next_ecu = segments_layer.get_param_value(self, 'mapping', e.target)

                    if next_ecu not in inter_segments:
                        inter_segments[next_ecu] = set()
                    inter_segments[next_ecu].add(o)
            else:
                ecu = segments_layer.get_param_value(self, 'mapping', o)

                if ecu not in intra_segments:
                    intra_segments[ecu] = set()
                intra_segments[ecu].add(o)

        # define segment id for every intra segment
        sid = 1
        segments = dict()
        for ecu, segs in intra_segments.items():
            for s in segs:
                segments[s] = sid
                sid += 1

        for ecu, segs in intra_segments.items():
            self._write_monitor_yaml(ecu.copy(), segs, budgets, consumers, segments)

        for ecu in self.ecus - set([k.copy() for k in intra_segments.keys()]):
            # set priorities for ECUs if not handled by the previous call
            self._write_monitor_yaml(ecu, set(), None, None, None)

        # create XML for eProsima QoS parameters
        for ecu, segs in inter_segments.items():
            self._write_qos_xml(ecu.copy(), segs)

        return True


class CrossLayerModel(BacktrackRegistry):
    """ Our cross-layer model.
    """
    def __init__(self, repo):
        super().__init__()
        self.add_layer(Layer('nodes',       nodetypes={Repository.RosNode}))
        self.add_layer(Layer('callbacks',   nodetypes={Repository.Callback}))
        self.add_layer(Layer('segments',    nodetypes={SegmentEngine.Segment}))
        self.add_layer(Layer('netsegments', nodetypes={SegmentEngine.Segment}))

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
    def __init__(self, repo, ecus, chronologicaltracking=False):
        self._repo = repo
        self._nonchronological = not chronologicaltracking
        self._ecus = ecus

    def _to_callbacks(self, model):
        source_layer = model.by_name['nodes']
        target_layer = model.by_name['callbacks']
        ce = CallbackEngine(layer=source_layer,
                            target_layer=target_layer)

        model.add_step(NodeStep(Transform(ce, target_layer, 'transform to callbacks')))
        model.add_step(EdgeStep(Transform(ce, target_layer, 'connect callbacks')))

    def _to_segments(self, model, query):
        # transform callbacks into segments
        cb_layer     = model.by_name['callbacks']
        seg_layer    = model.by_name['segments']
        net_layer    = model.by_name['netsegments']
        se = SegmentEngine(layer=cb_layer,
                           target_layer=seg_layer,
                           query=query)

        step = NodeStep(BatchMap(se, 'define segments'))
        step.add_operation(Assign(se, 'define segments'))
        step.add_operation(Transform(se, seg_layer, 'transform to segments'))
        model.add_step(step)
        model.add_step(EdgeStep(Transform(se, seg_layer, 'connect segments')))

        source_layer = model.by_name['segments']
        ne = NetworkEngine(layer=seg_layer,
                           target_layer=net_layer)

        step = CopyNodeStep(seg_layer, net_layer, {'mapping'})
        model.add_step(step)
        step = EdgeStep(Map(ne, 'network segments'))
        step.add_operation(Assign(ne, 'network segments'))
        step.add_operation(Transform(ne, net_layer, 'split arcs'))
        model.add_step(step)

        ee = ExceptionEngine(net_layer, parent_layers=[seg_layer, cb_layer])
        step = NodeStep(Map(ee, 'assign handler'))
        step.add_operation(Assign(ee, 'assign handler'))
        step.add_operation(Check(ee,  'check segments'))
        model.add_step(step)

    def _assign_budgets(self, model):
        layer   = model.by_name['netsegments']
        seglayer= model.by_name['segments']
        cblayer = model.by_name['callbacks']

        # first calculate minimum required budget of segments
        we = WcrtEngine(layer, parent_layers=[seglayer, cblayer])
        step = NodeStep(Map(we, 'calculate WCRTs'))
        step.add_operation(Assign(we, 'calculate WCRTs'))
        model.add_step(step)

        # assign budgets
        be = BudgetEngine(layer)
        step = NodeStep(BatchMap(be, 'calculate budgets'))
        step.add_operation(Assign(be, 'calculate budgets'))
        model.add_step(step)

    def _export_config(self, model, outpath):
        layer = model.by_name['segments']
        ce = ConfigEngine(model, self._ecus, outpath)

        model.add_step(NodeStep(BatchCheck(ce, 'export configs')))

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

        # 6) export config
        self._export_config(model, outpath)

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
