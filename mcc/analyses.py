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

    def map(self, obj):
        components = self.repo.find_components_by_type(obj.query(), obj.type())
        if len(components) == 0:
            logging.error("Cannot find referenced child %s '%s'." % (obj.type(), obj.query()))
        else:
            if len(components) > 1:
                logging.info("Multiple candidates found for child %s '%s'." % (obj.type(), obj.identifier()))

            return set(components)

        return set()

# TODO class SpecEngine(AnalysisEngine):

# TODO class RteEngine(AnalysisEngine):
#    def __init__(self, layer):
#        AnalysisEngine.__init__(self, layer, param='component')
#
#    def check(self, obj, layer):
#
#        if not isinstance(obj, Edge):
#            pf_comp = layer.get_param_value('mapping', obj)
#            assert(pf_comp is not None)
#
#            if layer.name == 'func_arch' or layer.name == 'comm_arch':
#                comp = layer.get_param_value('component', obj)
#                assert(comp is not None)
#            else:
#                comp = obj
#
#            if comp.requires_rte() != pf_comp.rte():
#                return False
#
#            return True
