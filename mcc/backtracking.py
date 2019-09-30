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
                logging.info('%s failed' % cns)

                # find branch point
                culprit = self.find_culprit(cns)
                if culprit is None:
                    print("\n%s" % self.stats)
                    raise Exception('No config could be found')

                print("\nRolling back to: %s" % (culprit))

                # mark current value(s) as bad
                self.decision_graph.mark_bad(culprit)

                if outpath is not None:
                    name = 'decision-try-%d.dot' % self.backtracking_try
                    path = outpath + name
                    leaves = self.decision_graph.successors(culprit, recursive=True)
                    highlight = {cns.operation}

                    self.decision_graph.write_dot(path, leaves=None,
                                                  verbose=True,
                                                  reshape=leaves,
                                                  highlight=highlight)

                    print(" rolling back %d operations" % len(leaves))
                    self._update_stats(len(leaves))

                if outpath is not None:
                    export = PickleExporter(self)
                    export.write(outpath+'model-pretry-%d.pickle' % self.backtracking_try)

                self.invalidate_subtree(culprit)

                if outpath is not None:
                    export = PickleExporter(self)
                    export.write(outpath+'model-try-%d.pickle' % self.backtracking_try)

                self.decision_graph.next_iteration(culprit)
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
        return self._find_brancheable({cns.operation})

    def _dependencies(self, nodes):
        result = set()
        queue = list(nodes)
        while len(queue):
            n = queue.pop(0)
            dgraph = self.decision_graph
            for p in dgraph.read_params(n):
                writers = dgraph.find_writers(p.layer, p.obj, p.param)
                # avoid infinite loops by excluding already processed nodes
                for op in writers.all() - result:
                    queue.append(op)
                    result.add(op)
        return result

    def _find_brancheable(self, operations):
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
            if op not in dependencies:
                continue
            if self.decision_graph.revisable(op):
                return op

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

    def _clear_failed(self, node):
        for p in self.decision_graph.written_params(node):
            failed = p.layer.get_param_failed(p.param, p.obj)
            if failed is not None:
                failed.destroy()

    def _rollback_transform(self, node):
        op = node.operation
        src_layer, trg_layer = op.source_layer, op.target_layer
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
            # first, remove layer mapping to source obj from each target obj
            for trg in src_layer.associated_objects(trg_layer.name, node.obj):
                src_objs = trg_layer.associated_objects(src_layer.name, trg)
                new = src_objs - {node.obj}
                trg_layer._set_associated_objects(src_layer.name, trg, new)
            # now, clear source->target layer mapping completely
            src_layer._set_associated_objects(trg_layer.name, node.obj, set())

            created = set() # actually created objects
            for p in self.decision_graph.written_params(node):
                if 'obj' == p.param:
                    created.add(p.obj)
                p.layer.untracked_clear_param_value(p.param, p.obj)

            # by deleting edges first, we can log each deletion
            created_edges = {o for o in created if isinstance(o, Edge)}
            for o in list(created_edges) + list(created - created_edges):
                # Other transform op's which tried to create the already
                # existing 'o' object should have been backrolled earlier due
                # to their automatically added read access record. Thus, the
                # remaining set of associated objects should be empty now.
                assert not len(trg_layer.associated_objects(src_layer.name, o))

                self.delete_recursive(o, trg_layer)

    def invalidate_subtree(self, start):
        assert isinstance(start.operation, Assign)

        # check operations can be reached multiple times
        visited_checks = set()

        for n in self.decision_graph.reversed_subtree(start):
            if n in visited_checks:
                continue

            assert n.obj is None or n.obj in n.layer.graph.nodes() or n.obj in n.layer.graph.edges(), "CANNOT REVERSE %s: already deleted" % n

            # invalidate layer depending on what operations were involved
            op = n.operation
            if isinstance(op, Assign):
                # clear failed field if we not revise op (i.e. n == start)
                if n is not start:
                    self._clear_failed(n)
                self._rollback_assign(n)
            elif isinstance(op, Map):
                # remark: no need to clear failed because a map operation
                #         will always be succeeded by an assign, which
                #         takes care of this (see above)
                self._rollback_map(n)
            elif isinstance(op, Transform):
                # remark: no need to clear failed because there must be
                #         no Map/Assign operations that write the same
                #         params
                self._rollback_transform(n)
            elif isinstance(op, Check):
                visited_checks.add(n)
            else:
                raise NotImplementedError

            if op in self.operations and self.operations[op]:
                logging.debug("Marking %s as to-be-repeated" % op)
                self.operations[op] = False

            if n is not start:
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

