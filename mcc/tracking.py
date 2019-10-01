"""
Description
-----------

Implements dependency tracking.

:Authors:
    - Johannes Schlatow

"""

from mcc.framework import *

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

    def add_dependencies(self, node, read, written, force_sequential):
        read_params    = self.read_params(node)
        writers = self._raw_dependencies(node, read, written)

        old_transforms = dict()
        for p in written:
            if isinstance(node.operation, Transform):
                # if there are already writers (only possible if Transform), remember them for later check
                old_transforms[p] = self.param_store[p].transform - {node}

        # add old writers as dependencies
        for p,trafos in old_transforms.items():
            writers.update(trafos)

        # return early if there are no dependencies
        if len(writers) == 0:
            if len(written) > 0:
                self.create_edge(self.root, node)
            return

        # ignore writers that are predecessors of any other writer
        blacklist = set()
        for w in writers:
            if len(self.successors(w, recursive=True) & writers) > 0:
                blacklist.add(w)

        dependencies = writers - blacklist
        assert len(dependencies) > 0

        if isinstance(node.operation, Check) and not force_sequential:
            for d in dependencies:
                self.create_edge(d, node)
        else:
            try:
                # first, maintain tree structure
                order = sorted(dependencies, key=lambda x: x.iteration)
                main = order.pop()
                while len(order) > 0:
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