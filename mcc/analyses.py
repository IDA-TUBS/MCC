import logging
from mcc.framework import *
from mcc.graph import *
from mcc import model

class MappingEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='mapping')

    def map(self, obj, candidates):
        if candidates is None or len(candidates) == 0 or None in candidates:
            # TODO derive from connections
            return candidates

        return candidates

    def check(self, obj):
        """ check whether a platform mapping is assigned to all nodes
        """
        assert(not isinstance(obj, Edge))

        okay = self.layer.get_param_value(self, self.param, obj) is not None
        if not okay:
            logging.info("Node '%s' is not mapped to anything.", obj)

        return okay

class DependencyEngine(AnalysisEngine):
    def __init__(self, layer):
        acl = { layer : { 'reads' : set(['component']) } }
        AnalysisEngine.__init__(self, layer, param=None, acl=acl)

    def check(self, obj):
        """ Check whether all dependencies are satisfied
        """
        assert(not isinstance(obj, Edge))

        comp = self.layer.get_param_value(self, 'component', obj)

        # iterate function dependencies
        for f in comp.requires_functions():
            # find function among connected nodes
            found = False
            for con in self.layer.graph.out_edges(obj):
                comp2 = self.layer.get_param_value(self, 'component', con.target)
                if comp2.function() == f:
                    found = True
                    break

            if not found:
                logging.error("Cannot satisfy function dependency '%s' from component '%s'." % (f, comp))
                return False

        return True

class ComponentDependencyEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param=None)

    def check(self, obj):
        """ Check that a) all service requirements are satisfied and b) that service connections are local
        """
        assert(not isinstance(obj, Edge))

        # iterate function dependencies
        for s in obj.requires_services():
            # find provider among connected nodes
            found = 0
            for con in self.layer.graph.out_edges(obj):
                comp2 = con.target
                if s in comp2.provides_services():
                    found += 1
                    source_mapping = self.layer.get_param_value(self, 'mapping', obj)
                    target_mapping = self.layer.get_param_value(self, 'mapping', comp2)
                    if source_mapping != target_mapping:
                        logging.error("Service connection '%s' from component '%s' to '%s' crosses platform components." % (s, obj, comp2))
                        return False

            if found == 0:
                logging.error("Service dependency '%s' from component '%s' is not satisfied." % (s, obj))
                return False
            if found != len([x for x in obj.requires_services() if x == s]):
                logging.error("Service dependency '%s' from component '%s' is ambiguously satisfied." % (s, obj))
                return False

        return True

class ServiceEngine(AnalysisEngine):

    class Connection:
        def __init__(self, source, target, source_service, target_service):
            self.source = source
            self.target = target
            self.source_service = source_service
            self.target_service = target_service
            self.protocol_stack = None

        def assign_protocol_stack(self, protocol_stack):
            self.protocol_stack = protocol_stack

        def get_graph_objs(self):
            result = set()

            if self.protocol_stack is not None:
                raise NotImplementedError()
            else:
                result.add(GraphObj(Edge(self.source, self.target), params={ 'service' : self.source_service }))

            return result

    def __init__(self, layer, target_layer):
        acl = { layer : { 'reads' : set(['service', 'function', 'component', 'pattern', target_layer.name]) } }
        AnalysisEngine.__init__(self, layer, param='connection', acl=acl)
        self.target_layer = target_layer

    def map(self, obj, candidates):
        """ Select candidates for to-be-connected source and target nodes between components
        """
        # FIXME: make this more systematically by adding a side layer with service requirements as nodes
        #        in order to decide on each service requirement (of a component) separately

        assert(isinstance(obj, Edge))

        service  = self.layer.get_param_value(self, 'service', obj)
        function = self.layer.get_param_value(self, 'function', obj)

        # get dangling provisions
        dst = self.layer.get_param_value(self, 'component', obj.target)
        provisions = dst.provides_services()

        assert function is None or function == dst.function()
        function = dst.function()

        # get dangling requirements
        src = self.layer.get_param_value(self, 'component', obj.source)
        if function is not None and src.service_for_function(function) is not None:
            requirements = set([src.service_for_function(function)])
        else:
            requirements = src.requires_services()

        # if multiple dangling services, try to match by service or function
        if len(requirements) == 1:
            src_service = requirements.pop()
        else:
            src_service = service
            assert service in requirements, "Cannot choose from multiple dangling service requirements '%s'." % service

        if len(provisions) == 1:
            dst_service = provisions.pop()
        else:
            dst_service = service
            assert service in provisions, "Cannot choose from multiple dangling service provisions."

        # match selected services to src_candidates/dst_candidates
        src_pattern = self.layer.get_param_value(self, 'pattern', obj.source)
        dst_pattern = self.layer.get_param_value(self, 'pattern', obj.target)

        src_mapping = self.layer.get_param_value(self, self.target_layer.name, obj.source)
        dst_mapping = self.layer.get_param_value(self, self.target_layer.name, obj.target)

        # find source components in target layer
        src_comps = set()
        for c in src_pattern.requiring_components(src_service, function=function):
            found = False
            for x in src_mapping:
                if hasattr(x, 'uid'):
                    if x.uid() == c.uid():
                        src_comps.add(x)
                        found = True
            assert(found)

        # find dst component in target layer
        c = dst_pattern.providing_component(dst_service)
        found = False
        for x in dst_mapping:
            if hasattr(x, 'uid'):
                if x.uid() == c.uid():
                    dst_comp = x
                    found = True
        assert(found)
        
        candidates = set()
        for src_comp in src_comps:
            candidates.add(ServiceEngine.Connection(src_comp, dst_comp, src_service, dst_service))

        # FIXME continue here
        # TODO if services differ, insert protocol stack (separate AE?)
        # TODO add separate AE which removes candidates that do not reside on the same resource

        return candidates

    def assign(self, obj, candidates):
        """ Choose a candidate
        """
        assert(isinstance(obj, Edge))

        return list(candidates)

    def transform(self, obj, target_layer):
        """ Transform comm_arch edges into comp_arch edges
        """
        assert(isinstance(obj, Edge))

        graph_objs = set()
        for con in self.layer.get_param_value(self, self.param, obj):
            graph_objs.update(con.get_graph_objs())

        return graph_objs

class QueryEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='mapping')

    def assign(self, obj, candidates):
        if len(candidates) == 0:
            logging.error("No mapping candidate for '%s'." % (obj.label()))
            raise Exception("ERROR")
        elif len(candidates) > 1:
            logging.info("Multiple mapping candidates for '%s'." % (obj.label()))

        return list(candidates)[0]

    def source_types(self):
        return set([self.layer.nodetype])

class ComponentEngine(AnalysisEngine):
    def __init__(self, layer, repo):
        AnalysisEngine.__init__(self, layer, param='component')
        self.repo = repo

    def map(self, obj, candidates):
        assert(not isinstance(obj, Edge))

        assert(candidates is None)
        components = self.repo.find_components_by_type(obj.query(), obj.type())
        if len(components) == 0:
            logging.error("Cannot find referenced child %s '%s'." % (obj.type(), obj.query()))
        else:
            if len(components) > 1:
                logging.info("Multiple candidates found for child %s '%s'." % (obj.type(), obj.identifier()))

            return set(components)

        return set()

    def assign(self, obj, candidates):
        assert(not isinstance(obj, Edge))

        if len(candidates) == 0:
            raise Exception("no component left for assignment")

        return list(candidates)[0]

    def check(self, obj):
        return self.layer.get_param_value(self, self.param, obj) is not None

    def transform(self, obj, target_layer):
        return set([self.layer.get_param_value(self, self.param, obj)])

class PatternEngine(AnalysisEngine):
    def __init__(self, layer):
        acl = { layer : { 'reads' : set(['component']) } }
        AnalysisEngine.__init__(self, layer, param='pattern', acl=acl)

    def map(self, obj, candidates):
        assert(not isinstance(obj, Edge))

        assert(candidates is None)
        return self.layer.get_param_value(self, 'component', obj).patterns()

    def assign(self, obj, candidates):
        assert(not isinstance(obj, Edge))

        if len(candidates) == 0:
            raise Exception("no pattern left for assignment")

        return list(candidates)[0]

    def check(self, obj):
        return self.layer.get_param_value(self, self.param, obj) is not None

    def transform(self, obj, target_layer):
        return self.layer.get_param_value(self, self.param, obj).flatten()

class SpecEngine(AnalysisEngine):
    def __init__(self, layer, param='component'):
        acl = { layer : { 'reads' : set(['mapping']) } }
        AnalysisEngine.__init__(self, layer, param=param, acl=acl)

    def _match_specs(self, required, provided):
        for spec in required:
            if spec not in provided:
                return False

        return True

    def map(self, obj, candidates): 
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return candidates

        keep = set()
        for c in candidates:
            pf_comp = self.layer.get_param_value(self, 'mapping', obj)
            assert(pf_comp is not None)

            if self._match_specs(c.requires_specs(), pf_comp.specs()):
                keep.add(c)

        return keep

    def check(self, obj):
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value(self, 'mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value(self, 'component', obj)
            if comp is None:
                print(self.layer.get_param_candidates(self, 'component', obj))
            assert(comp is not None)
        else:
            comp = obj

        if not self._match_specs(comp.requires_specs(), pf_comp.specs()):
            return False

        return True

class RteEngine(AnalysisEngine):
    def __init__(self, layer, param='component'):
        acl = { layer : { 'reads' : set(['mapping']) } }
        AnalysisEngine.__init__(self, layer, param=param, acl=acl)

    def map(self, obj, candidates): 
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

    def check(self, obj):
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value(self, 'mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value(self, 'component', obj)
            if comp is None:
                print(self.layer.get_param_candidates(self, 'component', obj))
            assert(comp is not None)
        else:
            comp = obj

        if comp.requires_rte() != pf_comp.rte():
            return False

        return True

class ReachabilityEngine(AnalysisEngine):
    def __init__(self, layer, target_layer, platform_model):
        acl = { layer : { 'reads' : set(['mapping', 'service', target_layer.name]) }}
        AnalysisEngine.__init__(self, layer, param='proxy', acl=acl)
        self.platform_model = platform_model
        self.target_layer = target_layer

    def _find_carriers(self, obj):
        src_comp = self.layer.get_param_value(self, 'mapping', obj.source)
        dst_comp = self.layer.get_param_value(self, 'mapping', obj.target)

        result, carrier, pcomp = self.platform_model.reachable(src_comp, dst_comp)
        if result or carrier == self.layer.get_param_value(self, 'service', obj):
            return set([('native', pcomp)])
        else:
            return set([(carrier, pcomp)])

    def map(self, obj, candidates):
        assert(isinstance(obj, Edge))
        assert(candidates is None)

        candidates = self._find_carriers(obj)

        return candidates

    def assign(self, obj, candidates):
        assert(isinstance(obj, Edge))
        assert(len(candidates) > 0)

        return list(candidates)[0]

    def transform(self, obj, target_layer):
        assert(isinstance(obj, Edge))
        assert(target_layer == self.target_layer)

        carrier, pcomp = self.layer.get_param_value(self, self.param, obj)
        if carrier == 'native':
            return GraphObj(obj, params={ 'service' : self.layer.get_param_value(self, 'service', obj) })
        else:
            proxy = model.Proxy(carrier=carrier, service=self.layer.get_param_value(self, 'service', obj))
            result = [proxy]

            src_map = self.layer.get_param_value(self, target_layer.name, obj.source)
            dst_map = self.layer.get_param_value(self, target_layer.name, obj.target)
            assert(len(src_map) == 1)
            assert(len(dst_map) == 1)
            src = list(src_map)[0]
            dst = list(dst_map)[0]

            result.append(GraphObj(Edge(src, proxy), params={'service' : proxy.service}))
            result.append(GraphObj(Edge(proxy, dst), params={'service' : proxy.service}))

            # add dependencies to pcomp
            for n in self.layer.graph.nodes():
                if n.type() == 'function' and n.query() == pcomp:
                    if self.layer.get_param_value(self, 'mapping', n) == self.layer.get_param_value(self, 'mapping', obj.source) \
                       or self.layer.get_param_value(self, 'mapping', n) == self.layer.get_param_value(self, 'mapping', obj.target):
                           result.append(GraphObj(Edge(proxy, n), params={ 'service' : carrier }))

            return result
