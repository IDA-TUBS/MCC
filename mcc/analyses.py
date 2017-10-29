import logging
from mcc.framework import *
from mcc.graph import *

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
        if len(candidates) == 0:
            raise Exception("no component left for assignment")

        return list(candidates)[0]

class SpecEngine(AnalysisEngine):
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='component')

    def _match_specs(self, required, provided):
        for spec in required:
            if spec not in provided:
                return False

        return True

    def map(self, obj, candidates): 
        keep = set()
        for c in candidates:
            pf_comp = self.layer.get_param_value('mapping', obj)
            assert(pf_comp is not None)

            if self._match_specs(c.requires_specs(), pf_comp.specs()):
                keep.add(c)

        return keep

    def check(self, obj):

        if not isinstance(obj, Edge):
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
    def __init__(self, layer):
        AnalysisEngine.__init__(self, layer, param='component')

    def map(self, obj, candidates): 
        keep = set()
        for c in candidates:
            pf_comp = self.layer.get_param_value('mapping', obj)
            assert(pf_comp is not None)

            if c.requires_rte() == pf_comp.rte():
                keep.add(c)

        return keep

    def check(self, obj):

        if not isinstance(obj, Edge):
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
