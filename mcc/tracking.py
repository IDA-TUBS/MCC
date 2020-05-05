"""
Description
-----------

Implementations of :class:`mcc.framework.DecisionGraph`.

:Authors:
    - Johannes Schlatow
    - Edgard Schmidt

"""

from mcc.framework import *
from  networkx.algorithms import dag
from  networkx.algorithms import shortest_paths

from collections import deque

class LinearGraph(DecisionGraph):
    """ Discards dependencies and pushes each operation to a stack to implement
        chronological backtracking.
    """

    def __init__(self):
        super().__init__()
        self.latest = self.root

    def add_dependencies(self, node, read, written, force_sequential, extra=None):
        if extra is not None:
            raise NotImplementedError

        for p in written:
            if p not in self.param_store:
                self.param_store[p] = self.Writers()
            self.param_store[p].register(node)
        self.written_params(node).update(written)

        # avoid iterating though the graph if we already know the latest node
#        if self.latest not in self.nodes(): # this may happen after a rollback
#            self.latest = next(self.filter_leaves(self.nodes()))
        assert self.latest in self.nodes()
        self.create_edge(self.latest, node)
        self.latest = node

    def next_iteration(self, culprit):
        super().next_iteration(culprit)
        self.latest = culprit


class TopologicalGraph(DecisionGraph):
    """ Stores dependencies between decisions as graph which is
        sequentialising on demand by performing topological sort
        on the relevant subgraph.
    """

    def __init__(self):
        super().__init__()
        self.pm_cached = None

    def sort(self, node, calculate_ranks=False):
        """ execute topological sort for ordering
            all predecessors of 'node' ensuring that
            old nodes come before younger nodes.
            We also try to rate what nodes should come first. Nodes with
            dependencies unrelated to 'node' should come first so that they
            do not need to be rolled back. Actual decisions should come later.
        """

        self.pm_cached = None

        nodes = self.predecessors(node, recursive=True) | {node}
        subgraph = self.graph.subgraph(nodes)

        if calculate_ranks:
            for n in nodes:
                if hasattr(n, 'rank'):
                    del n.rank
                    del n.decisions

            next_nodes = deque()
            n = node

            # decisions denote the minimum number of revisable decisions on any path to 'node'
            n.decisions = 1 if self.revisable(n) else 0
            # rank denotes the longest path to 'node'
            n.rank = 0
            while n:
                for p in subgraph.predecessors(n):
                    add = True
                    cur_revisable = 1 if self.revisable(p) else 0
                    dec_set  = set()
                    rank_set = set()
                    for s in subgraph.successors(p):
                        if not hasattr(s, 'decisions'):
                            # only push predecessors if all their successors have been visited
                            add = False
                            break
                        else:
                            rank_set.add(s.rank+1)
                            dec_set.add(s.decisions + cur_revisable)

                    if add:
                        # propagate minimum number of decisions
                        p.decisions = min(dec_set)
                        # propagate maximum rank
                        p.rank      = max(rank_set)

                        next_nodes.append(p)

                try:
                    n = next_nodes.popleft()
                except:
                    n = None

        # FIXME key option is not working, will be fixed in networkx 2.4
        #       (see https://github.com/networkx/networkx/issues/3493)
        order = list(dag.lexicographical_topological_sort(subgraph,
                                                          key=None))
        for u,v in zip(order,order[1:]):
            for e in set(self.in_edges(v)):
                self.remove_edge(e)

            self.create_edge(u,v)

    def path_matrix(self):

        if self.pm_cached is None:
            self.pm_cached = dict()

            # initialise with adjacency matrix
            for u, nbrsdict in self.graph.adjacency():
                self.pm_cached[u] = dict()
                for v in self.nodes():
                    self.pm_cached[u][v] = 0
                for v in nbrsdict.keys():
                    self.pm_cached[u][v] = 1

            for u in self.nodes():
                for v in self.nodes():
                    if u == v:
                        continue
                    if self.pm_cached[v][u]:
                        for i in self.nodes():
                            if self.pm_cached[v][i] == 0:
                                self.pm_cached[v][i] = self.pm_cached[u][i]

        return self.pm_cached

    def update_path_matrix(self, n, adj):
        pm = self.path_matrix()

        # initialise new row/column with zeros
        pm[n] = dict()
        for u in self.nodes():
            pm[n][u] = 0
            pm[u][n] = 0

        # add adjacency
        for v in adj:
            pm[v][n] = 1

            # add path information
            for u in self.nodes():
                if pm[u][v]:
                    pm[u][n] = 1


    def reduce(self, writers):
        pm = self.path_matrix()
        blacklist = set()
        for u in writers:
            for v in writers - {u}:
                if pm[u][v] == 1:
                    blacklist.add(u)
                    break

        return writers - blacklist

    def reduceall(self):
        TR = dag.transitive_reduction(self.graph)

        for u, nbrsdict in self.graph.adjacency():
            # remove all edges
            for v in set(nbrsdict.keys()):
                self.graph.remove_edge(u,v)
            # re-add from TR
            for v in TR.successors(u):
                self.graph.add_edge(u,v)

    def remove(self, node):
        super().remove(node)
        self.pm_cached = None

    def add_dependencies(self, node, read, written, force_sequential, extra=None):
        writers = self._raw_dependencies(node, read, written)
        if extra is not None:
            assert isinstance(extra, set)
            writers.update(extra)

        old_transforms = dict()
        for p in written:
            if isinstance(node.operation, Transform):
                # if there are already writers (only possible if Transform), remember them for later check
                old_transforms[p] = self.param_store[p].transform - {node}

        # add old writers as dependencies
        for p,trafos in old_transforms.items():
            writers.update(trafos)

        # return early if there are no dependencies
        if not writers:
            if written:
                self.create_edge(self.root, node)

#            self.update_path_matrix(node, set())
            return

#        PATH-MATRIX IMPLEMENTATION
#        dependencies = self.reduce(writers)
#        self.update_path_matrix(node, dependencies)

#        if __debug__:
#            blacklist = set()
#            for w in writers:
#                if self.successors(w, recursive=True) & writers:
#                    blacklist.add(w)
#
#            assert len(dependencies) == len(writers-blacklist)
#            for d in writers-blacklist:
#                assert d in dependencies

#        TRIVIAL IMPLEMENTATION
#        blacklist = set()
#        for w in writers:
#            if self.successors(w, recursive=True) & writers:
#                blacklist.add(w)
#        dependencies = writers - blacklist

        dependencies = writers
        assert dependencies

        for d in dependencies:
            self.create_edge(d, node)

        if force_sequential:
#           CREATE TRANSITIVE REDUCTION ON DEMAND
            self.reduceall()

            assert dag.is_directed_acyclic_graph(self.graph)
            if __debug__:
                self.write_dot('/tmp/toposort_pre.dot', highlight={node})
                subgraph = self.predecessors(node, recursive=True)

            self.sort(node)

            if __debug__:
                self.write_dot('/tmp/toposort_post.dot', reshape=subgraph, highlight={node})


class DecisionTree(DecisionGraph):
    """ Stores dependencies between decisions as a tree.
    """

    def __init__(self):
        super().__init__()

    def _common_path(self, u, v):
        assert u != v

        path1 = self.root_path(u)
        path2 = self.root_path(v)

        i = 0
        while path1[i] == path2[i]:
            i += 1

        return i, path1, path2

    def _treeify(self, level, left, right):
        common_pred = left[level-1]
        left_start  = left[level]
        left_end    = left[-1]
        right_start = right[level]
        right_end   = right[-1]

        node     = None
        new_pred = None

        # can we order left branch below the right branch
        if left_start.iteration >= right_end.iteration:
            node     = left_start
            new_pred = right_end
            leaf     = left_end
        elif right_start.iteration >= left_end.iteration:
            node     = right_start
            new_pred = left_end
            leaf     = right_end
        else:
            # sanity check: starting condition
            if right[-1].iteration > left_end.iteration:
                # both should be in the same iteration
                raise NotImplementedError

            # right will be merged into left as follows:
            #   (example shows iteration numbers)
            #####################################
            #   Left        Merged        Right #
            #-----------------------------------#
            #                 0      <-     0   #
            #                 0      <-     0   #
            #    1    ->      1                 #
            #    1    ->      1                 #
            #                 2      <-     2   #
            #    2    ->      2                 #
            #    2    ->      2                 #
            #                 3      <-     3   #
            #                 4      <-     4   #
            #    4    ->      4                 #
            #####################################

            leaf = left_end
            common_pred = left[level-1]
            while right_end != common_pred:
                curr = right.pop()

                # last node in right branch is equal or older than left branch
                #  -> find node in left branch that is older than right branch
                while left[-1].iteration >= curr.iteration:
                    curl = left.pop()
                    if left[-1] == common_pred:
                        # stop at common predecessor
                        break

                # get everything that can be merged between left[-1] and curl
                #  (if left is already at common predecessor, we want to get everything)
                while right[-1].iteration > left[-1].iteration or left[-1] == common_pred:
                    if right[-1] == common_pred:
                        # stop at common predecessor
                        break
                    curr = right.pop()

                # remove left[-1] -> curl
                for e in self.in_edges(curl):
                    if e.source == left[-1]:
                        self.remove_edge(e)
                        break

                # remove right[-1] -> curr
                for e in self.in_edges(curr):
                    if e.source == right[-1]:
                        self.remove_edge(e)
                        break

                # create left[-1] -> curr
                self.create_edge(left[-1], curr)

                # create right_end -> curl
                self.create_edge(right_end, curl)

                # remember new right_end
                right_end = right[-1]

            # check iteration hierachry
            last = 0
            for n in self.root_path(leaf):
                assert n.iteration >= last
                last = n.iteration

        if node and new_pred:
            # remove edge between common_pred and node
            for e in self.in_edges(node):
                if e.source == common_pred:
                    self.remove_edge(e)
                    break

#        assert new_pred not in self.successors(node, recursive=True), "%s is reachable from %s, old predecessor was %s" % (new_pred, node, old_pred)

            # add edge between new_pred and node
            self.create_edge(new_pred, node)

        return leaf

    def add_dependencies(self, node, read, written, force_sequential, extra=None):
        read_params    = self.read_params(node)
        writers = self._raw_dependencies(node, read, written)

        if extra is not None:
            raise NotImplementedError

        old_transforms = dict()
        for p in written:
            if isinstance(node.operation, Transform):
                # if there are already writers (only possible if Transform), remember them for later check
                old_transforms[p] = self.param_store[p].transform - {node}

        # add old writers as dependencies
        for p,trafos in old_transforms.items():
            writers.update(trafos)

        # return early if there are no dependencies
        if not writers:
            if written:
                self.create_edge(self.root, node)
            return

        # ignore writers that are predecessors of any other writer
        blacklist = set()
        for w in writers:
            if self.successors(w, recursive=True) & writers:
                blacklist.add(w)

        dependencies = writers - blacklist
        assert dependencies

        if isinstance(node.operation, Check) and not force_sequential:
            for d in dependencies:
                self.create_edge(d, node)
        else:
            try:
                # first, maintain tree structure
                order = sorted(dependencies, key=lambda x: x.iteration)
                main = order.pop()
                while order:
                    best_level = 0
                    best_path1 =  None
                    for n in order:
                        level, path1, path2 = self._common_path(main, n)
                        if best_path1 is None or path1[level-1].iteration >= best_path1[best_level-1].iteration:
                            best_path1 = path1
                            best_path2 = path2
                            best_level = level

                    order.remove(best_path2[-1])
                    main = self._treeify(best_level,
                                         best_path1,
                                         best_path2)
            except:
                self.write_dot("/tmp/merge-error.dot", highlight=dependencies)
                raise Exception

            # second, the only remaining dependency is main
            self.create_edge(main, node)

        # ensure that all nodes that already depend on this writer are transitively dependent on the new node
        for p,trafos in old_transforms.items():
            # assemble readers
            readers = set()
            for t in trafos:
                for s in self.successors(t, recursive=True):
                    if p in self.read_params(s):
                        readers.add(s)

            for r in readers:
                # node must not depend on this or any of its successors
                assert node not in self.successors(r, recursive=True)
                # remove edge to predecessor and redirect it to 'node'
                for e in self.in_edges(r):
                    self.remove_edge(e)
                    self.create_edge(node, r)
