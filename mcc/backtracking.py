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

#        self.variables = list()
#        self.failed    = list()

        self.stats = { 'iterations'             : 0,
                       'rolled-back operations' : 0,
                       'cut-off combinations'   : 0,
                       'variables'              : 0,
                       'combinations'           : 0 }

    def _find_variables(self):
        variables = set()
        for n in self.decision_graph.nodes():
            for p in self.decision_graph.decisions(n):
                variables.add(p)

        return variables

#    def _check_variables(self):
#        if len(self.variables) == 0:
#            self.variables = list(self._find_variables())
#        else:
#            cur_variables = self._find_variables()
#            assert len(cur_variables) == len(self.variables)
#            for v in cur_variables:
#                assert v in self.variables
#
#    def _record_failed(self):
#        self._check_variables()
#
#        failed = list()
#        for v in self.variables:
#            failed.append(str(v.layer.untracked_get_param_value(v.param, v.obj)))
#
#        if failed in self.failed:
#            logging.error("Already failed on the following set of parameters: ")
#            for i in range(len(self.variables)):
#                logging.error("%s: %s" % (self.variables[i], failed[i]))
#
#
#            for f in self.failed:
#                print(f)
#
#            assert False
#
#        self.failed.append(failed)
#
#        print("Problem has %d variables, failed on %d" % (len(self.variables), len(self.failed)))
#        if len(self.failed) == 1:
#            print(self.variables)
#            print(self.failed)

    def complete_operation(self, operation):
        self.operations[operation] = True

    def skip_operation(self, operation):
        if operation not in self.operations:
            return False

        # FIXME workaround: repeat all check operations
        if isinstance(operation, Check):
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
            self.decision_graph.next_iteration()
            pass

        print("Backtracking succeeded in try %s" % self.backtracking_try)
        print(self.stats)

        self._output_layer(self.steps[-1].target_layer)

    def _backtrack_execute(self, outpath):
        print()

        self.backtracking_try += 1
        self.stats['iterations'] = self.backtracking_try

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
#                self._record_failed()
                logging.info('%s failed on layer %s in param %s:' % (cns.obj, cns.layer, cns.param))

                # find branch point
                culprit = self.find_culprit(cns)
                if culprit is None:
                    print("\n%s" % self.stats)
                    raise Exception('No config could be found')

                print("\nRolling back to: %s" % (culprit))

                # mark value as bad if there are other candidates
                bad = culprit.layer.untracked_get_param_value(culprit.param, culprit.obj)
                culprit.layer.add_param_failed(culprit.param, culprit.obj, bad)

                # cut-off subtree
                node = self.decision_graph.find_assign(culprit.layer, culprit.obj, culprit.param)
                print("   assigned by operation: %s" % (node))

                if outpath is not None:
                    name = 'decision-try-%d.dot' % self.backtracking_try
                    path = outpath + name
                    leaves = self.decision_graph.successors(node, recursive=True)
                    highlight = set()
                    p = self._failed_param(cns)
                    highlight.update(self.decision_graph.find_writers(p.layer, p.obj, p.param).all())

                    self.decision_graph.write_dot(path, leaves=None,
                                                  verbose=True,
                                                  reshape=leaves,
                                                  highlight=highlight)

                    print(" rolling back %d operations" % len(leaves))
                    self._update_stats(len(leaves))

                if outpath is not None:
                    export = PickleExporter(self)
                    export.write(outpath+'model-pretry-%d.pickle' % self.backtracking_try)

                self.invalidate_subtree(node)

                if outpath is not None:
                    export = PickleExporter(self)
                    export.write(outpath+'model-try-%d.pickle' % self.backtracking_try)

                return False

            except Exception as ex:
                self._output_layer(step.target_layer, suffix='-error')
                print("\n%s" % self.stats)
                import traceback
                traceback.print_exc()
                raise(ex)
        return True

    def _update_stats(self, num_operations):
        self.stats['rolled-back operations'] += num_operations
        variables = self._find_variables()
        if len(variables) > self.stats['variables']:
            self.stats['variables'] = len(variables)

        combinations = 1
        for v in variables:
            combinations = combinations * len(v.layer.untracked_get_param_candidates(v.param, v.obj))

        if combinations > self.stats['combinations']:
            self.stats['cut-off combinations'] += (self.backtracking_try-1) * \
                                                  (combinations - self.stats['combinations'])
            self.stats['combinations'] = combinations
        else:
            self.stats['cut-off combinations'] += self.stats['combinations'] - combinations

    def find_culprit(self, cns):
        culprit = self._failed_param(cns)

        # can we change the culprit?
        if not self.decision_graph.candidates_exhausted(culprit):
            return culprit

        return self._find_brancheable(culprit)

    def _failed_param(self, cns):
        if cns.param is None:
            cns.param = 'obj'

        return self.decision_graph.param(cns.layer, cns.obj, cns.param)

    def _dependencies(self, nodes):
        result = set()
        for n in nodes:
            for p in self.decision_graph.read_params(n):
                for op in self.decision_graph.find_writers(p.layer, p.obj, p.param).all():
                    result.add(op)
                    result.update(self._dependencies({op}))

        return result

    def _find_brancheable(self, param):
        # collect all corresponding operations
        operations = self.decision_graph.find_writers(param.layer, param.obj, param.param).all()

        # find the latest operation
        latest_path  = None
        max_length   = 0
        for op in operations:
            path = self.decision_graph.root_path(op)
            if len(path) > max_length:
                latest_path = path
                max_length = len(path)

        # only look at operations that affect the culprit
        # we do this by first building the transitive set of
        # read_params (i.e.\ their writers) and skipping all 
        # ops in the path that are not in this set
        dependencies = self._dependencies(operations)

        # go backwards until we have found a changeable operation
        while len(latest_path) > 0:
            op = latest_path.pop()
            for p in self.decision_graph.written_params(op):
                if not self.decision_graph.candidates_exhausted(p):
                    if op not in dependencies:
                        logging.INFO("Skipping independent decision %s" % op)
                        continue
                    return p

        return None

    def _rollback_assign(self, node):
        for p in self.decision_graph.written_params(node):
            p.layer.untracked_clear_param_value(p.param, p.obj)

    def _rollback_map(self, node):
        for p in self.decision_graph.written_params(node):
            p.layer.untracked_clear_param_candidates(p.param, p.obj)

        # reset state partially, if map is rolled back
        # (we assume that state is only modified by Map operations)
        for ae in node.operation.analysis_engines:
            if hasattr(ae, 'reset'):
                ae.reset(node)

    def _rollback_transform(self, node):
        op = node.operation
        if self.clear_layers:
            for node in op.source_layer.graph.nodes():
                op.source_layer._set_associated_objects(op.target_layer.name, node, set())
            for edge in op.source_layer.graph.edges():
                op.source_layer._set_associated_objects(op.target_layer.name, edge, set())
            self.reset(op.target_layer)

            for i in range(self.by_order.index(op.target_layer), len(self.by_order)):
                for o in self.operations.keys():
                    if o.target_layer == self.by_order[i]:
                        self.operations[o] = False
        else:
            trg_nodes = op.source_layer.associated_objects(op.target_layer.name, node.obj)
            for trg in trg_nodes:
                self.delete_recursive(trg, op.target_layer)

            # clear source->target layer mapping
            op.source_layer._set_associated_objects(op.target_layer.name, node.obj, set())

    def invalidate_subtree(self, start):
        assert isinstance(start.operation, Assign)

        for n in self.decision_graph.reversed_subtree(start):
            assert n.obj in n.layer.graph.nodes() or n.obj in n.layer.graph.edges(), "CANNOT REVERSE %s: already deleted" % n

            # invalidate layer depending on what operations were involved
            op = n.operation
            if isinstance(op, Assign):
                self._rollback_assign(n)
            elif isinstance(op, Map):
                self._rollback_map(n)
            elif isinstance(op, Transform):
                self._rollback_transform(n)
            else:
                raise NotImplementedError

            if op in self.operations and self.operations[op]:
                logging.debug("Marking %s as to-be-repeated" % op)
                self.operations[op] = False

            # remove node from decision graph
            self.decision_graph.remove(n)

    def delete_recursive(self, obj, layer):
        if obj not in layer.graph.nodes() and obj not in layer.graph.edges():
            return

        nextlayer = self._next_layer(layer)
        if nextlayer is not None:
            nodes = layer.associated_objects(nextlayer.name, obj)

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

