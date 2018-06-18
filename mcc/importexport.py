"""
Description
-----------

Implements Graph import and export classes.

:Authors:
    - Johannes Schlatow

"""

import logging

import mcc.graph
from mcc.framework import Layer

from networkx import write_gpickle

import pickle
import mcc.noparser

class Exporter:
    def __init__(self, registry, acl):
        self.registry = registry
        self.acl      = acl

    def write(self, filename):
        raise NotImplementedError

class Importer:
    def __init__(self, registry):
        self.registry = registry

    def read(self):
        raise NotImplementedError

#class GraphPickler(pickle.Pickler):
#
#def __init__(self, file):
#    pickle.Pickler.__init__(self, file)
#    self._mcc_objs = set()
#
#def _is_mcc_obj(self, obj):
#    if type(obj).__module__.startswith('mcc'):
#        return True
#
#    return False
#
#def persistent_id(self, obj):
#
#    if self._is_mcc_obj(obj):
#        if obj in self._mcc_objs:
#            return id(obj)
#        else:
#            self._mcc_objs.add(obj)
#
#    return None

class GraphUnpickler(pickle.Unpickler):

#    def __init__(self, file):
#        pickle.Pickler.__init__(self, file)
#        self._mcc_objs = dict()
#
#    def persistent_load(self, pid):
#        if pid in self._mcc_objs:
#
#        raise pickle.UnpicklingError("unsupported persistent object")
#
    def find_class(self, module, name):
        import sys
        hierarchy = name.split('.')
        if module == "mcc.parser":
            module = "mcc.noparser"

        current = getattr(sys.modules[module], hierarchy[0])
        for c in hierarchy[1:]:
            current = getattr(current, c)

        if current is None:
            logging.error("Cannot find %s in mcc.noparser" % name)
            return None

        return current

class PickleExporter(Exporter):

    def write(self, filename):

        export_obj = dict()

        for layer in self.acl:
            export_obj[layer.name] = layer
            layer.graph.export_filter(self.acl[layer]['reads'], self.acl[layer]['reads'])

        with open(filename, "wb") as picklefile:
            pickle.Pickler(picklefile).dump(export_obj)

class PickleImporter(Importer):

    def read(self, filename):
        with open(filename, "rb") as picklefile:
            import_obj = GraphUnpickler(picklefile).load()
            for name in import_obj:
                self.registry.by_name[name].graph = import_obj[name].graph
