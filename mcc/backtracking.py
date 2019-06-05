"""
Description
-----------

Implements backtracking-related data structures.

:Authors:
    - Dustin Frey
    - Johannes Schlatow

"""

from mcc.framework import *
from mcc.graph import *
from mcc.importexport import *


class BacktrackRegistry(Registry):
    """ Implements/manages a cross-layer model.

    Layers and transformation steps are stored, managed, and executed by this class.
    Uses Backtracking to find a valid config instead of failing
    """
    def __init__(self):
        super().__init__()
        self.dec_graph = DecisionGraph()
        self.backtracking_try = 0
        self.clear_layers = False

        # stores state (completed) of operations
        self.operations = dict()

    def complete_operation(self, operation):
        self.operations[operation] = True

    def skip_operation(self, operation):
        if operation not in self.operations:
            return False

        if isinstance(operation, Transform):
            return False

        if self.operations[operation] == True:
            logging.info("Skipping %s" % operation)

        # skip operation if marked True
        return self.operations[operation]

    def execute(self, outpath=None):
        """ Executes the registered steps sequentially.
        """

        self.decision_graph = DecisionGraph()
        self.decision_graph.initialize_tracking(self.by_order)

        while not self._backtrack_execute(outpath):
            pass

        print("Backtracking succeeded in try %s" % self.backtracking_try)

        self._output_layer(self.steps[-1].target_layer)

    def _backtrack_execute(self, outpath):
        print()

        self.backtracking_try += 1

        logging.info('Backtracking Try %s' % self.backtracking_try)
        for step in self.steps:

            previous_step = self._previous_step(step)
            if not Registry._same_layers(previous_step, step):
                logging.info("Creating layer %s" % step.target_layer)
                if previous_step is not None:
                    self._output_layer(previous_step.target_layer)

            try:
                step.execute(self)

            except ConstraintNotSatisfied as cns:
                logging.info('%s failed on layer %s in param %s:' % (cns.obj, cns.layer, cns.param))

                if outpath is not None:
                    name = 'decision-try-%d.dot' % self.backtracking_try
                    path = outpath + name
                    failed = self._failed_params(cns)
                    self.decision_graph.write_dot(path, failed, True)

                # find branch point
                culprit = self.find_culprit(cns)
                if culprit is None:
                    raise Exception('No config could be found')

                print("\nRolling back to: %s" % (culprit))

                # mark value as bad if there are other candidates
                bad = culprit.layer._get_param_value(culprit.param, culprit.obj)
                culprit.layer.add_param_failed(culprit.param, culprit.obj, bad)

                # cut-off subtree
                self.invalidate_subtree(culprit)

                if outpath is not None:
                    export = PickleExporter(self)
                    export.write(outpath+'model-try-%d.pickle' % self.backtracking_try)

                return False

            except Exception as ex:
                self._output_layer(step.target_layer, suffix='-error')
                import traceback
                traceback.print_exc()
                raise(ex)
        return True

    def find_culprit(self, cns):
        culprits = self._failed_params(cns)

        if len(culprits) == 0:
            # use leaves to find branching point
            for n in self.decision_graph.nodes():
                if len(self.decision_graph.out_edges(n)) == 0:
                    culprits.add(n)

        return self._find_brancheable(culprits)

    def _failed_params(self, cns):
        if cns.param is None:
            return self.decision_graph.search(layer=cns.layer,
                                              obj  =cns.obj)

        params = self.decision_graph.find_node(layer=cns.layer,
                                               obj  =cns.obj,
                                               param=cns.param)
        assert params is not None
        return { params }

    def _find_brancheable(self, nodes):
        for n in nodes:
            if not self.decision_graph.candidates_exhausted(n):
                return n

        # no candidates left => find previous decisions with candidates left
        #  i.e. breadth-first search in reverse direction
        # TODO reimplement graph._neightbours with a breadth-first search?
        #      this way, we could use graph.predecessors with recursive=True
        visited  = nodes
        queue    = list(nodes)
        while len(queue):
            cur = queue.pop()
            for n in self.decision_graph.predecessors(cur) - visited:
                visited.add(n)
                queue.append(n)

                if not self.decision_graph.candidates_exhausted(n):
                    return n

        return None

    def invalidate_subtree(self, start):
        # invalidate operations associated with start node
        for op in self.decision_graph.operations(start):
            if isinstance(op, Assign):
                start.layer._clear_param_value(start.param, start.obj)
                self.operations[op] = False
            elif isinstance(op, Map):
                continue
            elif isinstance(op, Transform):
                # we the start node is not a transform operation
                raise NotImplementedError

        for n in self.decision_graph.successors(start, recursive=True):
            deleted = True
            if n.obj in n.layer.graph.nodes() or n.obj in n.layer.graph.edges():
                deleted = False

            # invalidate layer depending on what operations were involved
            for op in self.decision_graph.operations(n):
                if not deleted:
                    if isinstance(op, Assign):
                        n.layer._clear_param_value(n.param, n.obj)
                    elif isinstance(op, Map):
                        n.layer._clear_param_candidates(n.param, n.obj)
                    elif isinstance(op, Transform):
                        if self.clear_layers:
                            for node in op.source_layer.graph.nodes():
                                op.source_layer._clear_param_value(op.target_layer.name, node)
                            for edge in op.source_layer.graph.edges():
                                op.source_layer._clear_param_value(op.target_layer.name, edge)
                            self.reset(op.target_layer)

                            for i in range(self.by_order.index(op.target_layer), len(self.by_order)):
                                for o in self.operations.keys():
                                    if o.target_layer == self.by_order[i]:
                                        self.operations[o] = False
                        else:
                            trg_nodes = n.layer._get_param_value(op.target_layer.name, n.obj)
                            if not isinstance(trg_nodes, set):
                                trg_nodes = {trg_nodes}

                            for trg in trg_nodes:
                                self.delete_recursive(trg, op.target_layer)

                            # clear source->target layer mapping
                            n.layer._clear_param_value(op.target_layer.name, n.obj)
                    else:
                        raise NotImplementedError

                # invalidate operations
                # FIXME some operations (e.g. Transform) are not marked as incomplete
                self.operations[op] = False
                for ae in op.analysis_engines:
                    if hasattr(ae, 'reset'):
                        ae.reset()

            # remove node from decision graph
            self.decision_graph.remove(n)

    def delete_recursive(self, obj, layer):
        if obj not in layer.graph.nodes() and obj not in layer.graph.edges():
            return

        nextlayer = self._next_layer(layer)
        if nextlayer is not None:
            nodes = layer._get_param_value(nextlayer.name, obj)
            if not isinstance(nodes, set):
                nodes = {nodes}

            for trg in nodes:
                self.delete_recursive(trg, nextlayer)

        if isinstance(obj, Edge):
            layer.remove_edge(obj)
            logging.debug("deleted %s on %s" % (obj, layer))
        else:
            layer.remove_node(obj)
            logging.debug("deleted %s on %s" % (obj, layer))


    def write_analysis_engine_dependency_graph(self, outfile='AeDepGraph.dot'):
        analysis_engines = set()
        engines_id       = set()
        layers           = set()
        read_params      = set()
        write_params     = set()

        for step in self.steps:
            for op in step.operations:
                analysis_engines.update(op.analysis_engines)

        print()

        for ae in analysis_engines:
            en = '{}'.format(type(ae).__name__)
            engines_id.add(en)

            for layer in ae.acl:
                la = str(layer).replace('-', '_')
                layers.add(la)
                if 'reads' in ae.acl[layer]:
                    for param in ae.acl[layer]['reads']:
                        if param == None:
                            continue
                        read_params.add((en, str(layer).replace('-', '_'), param.replace('-', '_')))

                if 'writes'in ae.acl[layer]:
                    for param in ae.acl[layer]['writes']:
                        if param == None:
                            continue
                        write_params.add((en, str(layer).replace('-', '_'), param.replace('-', '_')))

        # TODO we might want to force the params from the same layer to the same rank for better readability
        with open(outfile, 'w') as file:
            file.write('digraph {\n')
            file.write('rankdir=LR;\n')

            for e in engines_id:
                e = e.replace('-', '_')
                node = '{0} [label="<{0}>",shape=octagon,colorscheme=set39,fillcolor=4,style=filled];\n'.format(e)
                file.write(node)

            # add params as nodes
            for (param_id, layer, param_label) in {(param, layer, param) for (ae, layer, param) in read_params | write_params}:
                node = '{0}{1} [label="{1}.{2}", shape=oval]\n'.format(param_id, layer, param_label)
                file.write(node)

            # edge AnalysisEngine to parameter e.g. CopyeEnine -> mapping
            for (ae, param_id) in {(ae, param+layer) for (ae, layer, param) in write_params}:
                edge = '{0} -> {1}\n'.format(ae, param_id)
                file.write(edge)

            # edge AnalysisEngine to parameter e.g. mapping -> CopyEngine
            for (ae, param_id) in {(ae, param+layer) for (ae, layer, param) in read_params}:
                edge = '{1} -> {0}\n'.format(ae, param_id)
                file.write(edge)

            file.write('}\n')

