import logging
from mcc.framework import *
from mcc.graph import *
from mcc import model

class DependencyEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param=None)

    def check(self, obj):
        """ Check whether all dependencies are satisfied
        """
        assert(not isinstance(obj, Edge))

        comp = self.layer.get_param_value('component', obj)

        # iterate function dependencies
        for f in comp.requires_functions():
            # find function among connected nodes
            found = False
            for con in self.layer.graph.out_edges(obj):
                comp2 = self.layer.get_param_value('component', con.target)
                if comp2.function() == f:
                    found = True
                    break

            if not found:
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
        AnalysisEngine.__init__(self, layer, param='connection')
        self.target_layer = target_layer

    def map(self, obj, candidates):
        """ Select candidates for to-be-connected source and target nodes between components
        """
        assert(isinstance(obj, Edge))

        service  = self.layer.get_param_value('service', obj)
        function = self.layer.get_param_value('function', obj)

        # get dangling requirements
        src = self.layer.get_param_value('component', obj.source)
        if function is not None:
            requirements = set(src.service_for_function(function))
        else:
            requirements = src.requires_services()
        # FIXME exclude already connected services

        # get dangling provisions
        dst = self.layer.get_param_value('component', obj.target)
        provisions = dst.provides_services()
        # (FIXME exclude already connected services)

        # if multiple dangling services, try to match by service or function
        if len(requirements) == 1:
            src_service = requirements.pop()
        else:
            src_service = service
            assert service in requirements, "Cannot choose from multiple dangling service requirements."

        if len(provisions) == 1:
            dst_service = provisions.pop()
        else:
            dst_service = service
            assert service in provisions, "Cannot choose from multiple dangling service provisions."

        # match selected services to src_candidates/dst_candidates
        src_pattern = self.layer.get_param_value('pattern', obj.source)
        dst_pattern = self.layer.get_param_value('pattern', obj.target)

        src_mapping = self.layer.get_param_value(self.target_layer.name, obj.source)
        dst_mapping = self.layer.get_param_value(self.target_layer.name, obj.target)

        # find source components in target layer
        src_comps = set()
        for c in src_pattern.requiring_components(src_service):
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

        # TODO if services differ, insert protocol stack (separate AE?)
        # TODO add separate AE which removes candidates that do not reside on the same resource

        return candidates

    def assign(self, obj, candidates):
        """ Choose a candidate
        """
        assert(isinstance(obj, Edge))

        return list(candidates)[0]

    def transform(self, obj, target_layer):
        """ Transform comm_arch edges into comp_arch edges
        """
        assert(isinstance(obj, Edge))

        connection = self.layer.get_param_value(self.param, obj)

        return connection.get_graph_objs()

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
        return self.layer.get_param_value(self.param, obj) is not None

    def transform(self, obj, target_layer):
        return set([self.layer.get_param_value(self.param, obj)])

class PatternEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='pattern')

    def map(self, obj, candidates):
        assert(not isinstance(obj, Edge))

        assert(candidates is None)
        return self.layer.get_param_value('component', obj).patterns()

    def assign(self, obj, candidates):
        assert(not isinstance(obj, Edge))

        if len(candidates) == 0:
            raise Exception("no pattern left for assignment")

        return list(candidates)[0]

    def check(self, obj):
        return self.layer.get_param_value(self.param, obj) is not None

    def transform(self, obj, target_layer):
        return self.layer.get_param_value(self.param, obj).flatten()

class SpecEngine(AnalysisEngine):
    def __init__(self, layer, param='component'):
        AnalysisEngine.__init__(self, layer, param=param)

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
            pf_comp = self.layer.get_param_value('mapping', obj)
            assert(pf_comp is not None)

            if self._match_specs(c.requires_specs(), pf_comp.specs()):
                keep.add(c)

        return keep

    def check(self, obj):
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value('mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value('component', obj)
            if comp is None:
                print(self.layer.get_param_candidates('component', obj))
            assert(comp is not None)
        else:
            comp = obj

        if not self._match_specs(comp.requires_specs(), pf_comp.specs()):
            return False

        return True

class RteEngine(AnalysisEngine):
    def __init__(self, layer, param='component'):
        AnalysisEngine.__init__(self, layer, param=param)

    def map(self, obj, candidates): 
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return candidates

        keep = set()
        for c in candidates:

            pf_comp = self.layer.get_param_value('mapping', obj)
            assert(pf_comp is not None)

            if c.requires_rte() == pf_comp.rte():
                keep.add(c)

        return keep

    def check(self, obj):
        assert(not isinstance(obj, Edge))

        # no need to check this for proxies
        if isinstance(obj, model.Proxy):
            return True

        pf_comp = self.layer.get_param_value('mapping', obj)
        assert(pf_comp is not None)

        if self.layer.name == 'func_arch' or self.layer.name == 'comm_arch':
            comp = self.layer.get_param_value('component', obj)
            if comp is None:
                print(self.layer.get_param_candidates('component', obj))
            assert(comp is not None)
        else:
            comp = obj

        if comp.requires_rte() != pf_comp.rte():
            return False

        return True

class ReachabilityEngine(AnalysisEngine):
    def __init__(self, layer, platform_model):
        AnalysisEngine.__init__(self, layer, param='proxy')
        self.platform_model = platform_model

    def _find_carriers(self, obj):
        src_comp = self.layer.get_param_value('mapping', obj.source)
        dst_comp = self.layer.get_param_value('mapping', obj.target)

        result, carrier, pcomp = self.platform_model.reachable(src_comp, dst_comp)
        if result or carrier == self.layer.get_param_value('service', obj):
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

        carrier, pcomp = self.layer.get_param_value(self.param, obj)
        if carrier == 'native':
            return GraphObj(obj, params={ 'service' : self.layer.get_param_value('service', obj) })
        else:
            proxy = model.Proxy(carrier=carrier, service=self.layer.get_param_value('service', obj))
            result = [proxy]

            src_map = self.layer.get_param_value(target_layer.name, obj.source)
            dst_map = self.layer.get_param_value(target_layer.name, obj.target)
            assert(len(src_map) == 1)
            assert(len(dst_map) == 1)
            src = list(src_map)[0]
            dst = list(dst_map)[0]

            result.append(GraphObj(Edge(src, proxy), params={'service' : proxy.service}))
            result.append(GraphObj(Edge(proxy, dst), params={'service' : proxy.service}))

            # add dependencies to pcomp
            for n in self.layer.graph.nodes():
                if n.type() == 'function' and n.query() == pcomp:
                    if self.layer.get_param_value('mapping', n) == self.layer.get_param_value('mapping', obj.source) \
                       or self.layer.get_param_value('mapping', n) == self.layer.get_param_value('mapping', obj.target):
                           result.append(GraphObj(Edge(proxy, n), params={ 'service' : carrier }))

            return result
