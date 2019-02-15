import os
import re

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from xdot.ui.window import DotWidget
from xdot.ui.elements import Graph

from mcc.dot import DotFactory
from mcc.framework import Registry
from mcc.importexport import PickleImporter

class Page(Gtk.HPaned):

    def __init__(self, filename, window):
        self.window = window

        Gtk.HPaned.__init__(self)
        self.set_wide_handle(True)

        self.filename = filename

        self._open_pickle(filename)

        self.graph = Graph()

        self.dotwidget = DotWidget()
        self.dotwidget.connect("error", lambda e, m: self.error_dialog(m))
        self.dotwidget.connect("clicked", self.on_url_clicked)

        self.sidepane = Gtk.VBox()
        self.combo = Gtk.ComboBoxText()
        for choice in self.dotfactory.model.by_name.keys():
            self.combo.append(choice, choice)
        self.combo.connect('changed', self.show_dot)

        self.paramview = Gtk.TreeView.new_with_model(Gtk.TreeStore(str, int))
        col = Gtk.TreeViewColumn("No Node selected", Gtk.CellRendererText(),
                                 text=0, weight=1)
        self.paramview.append_column(col)
        scroll = Gtk.ScrolledWindow()
        scroll.add_with_viewport(self.paramview)

        self.sidepane.pack_start(self.combo, False, False, 0)
        self.sidepane.pack_end(scroll, True, True, 0)

        self.pack1(self.dotwidget, True, False)

        self.combo.set_active(0)

    def _open_pickle(self, filename):
        self.model = Registry()

        # import model
        importer = PickleImporter(self.model)
        importer.read(filename)

        self.dotfactory = DotFactory(self.model)

    def show_dot(self, box):
        name = box.get_active_id()
        try:
            if self.dotwidget.set_dotcode(self.dotfactory.get_layer(name).encode('utf-8')):
                self.dotwidget.zoom_to_fit()

        except IOError as ex:
            self.error_dialog(str(ex))

    def reload(self):
        self._open_pickle(self.filename)

        # TODO update combo box?

        self.show_dot(self.combo)

    def pane_active(self):
        return self.get_child2() is not None

    def toggle_info(self, button, window):
        x = button
        w = window
        p = self
        c = self.sidepane
        if x.get_active():
            p.pack2(c, True, True)
            w,_h = w.get_size()
            p.set_position(int(.7*w))
        else:
            p.remove(c)

        self.show_all()

    def find_text(self, entry_text):
        found_items = []
        dot_widget = self.dotwidget
        regexp = re.compile(entry_text)
        for element in dot_widget.graph.nodes + dot_widget.graph.edges:
            if element.search_text(regexp):
                found_items.append(element)
        return found_items

    def error_dialog(self, message):
        dlg = Gtk.MessageDialog(parent=self.window,
                                type=Gtk.MessageType.ERROR,
                                message_format=message,
                                buttons=Gtk.ButtonsType.OK)
        dlg.set_title(self.window.get_title())
        dlg.run()
        dlg.destroy()

    def _gen_hashable_value(self, value):
        #TODO make the objects hashable directly? Currently, we might lose
        #information about the number of elements if the string representation
        #of an object is ambiguous.
        if type(value) in {set, frozenset}:
            return frozenset(map(self._gen_hashable_value, value))
        return repr(value)

    def _add_paramtree(self, parent, params):
        # TODO filter out params that store inter-layer relations
        for name, content in params.items():
            node = self._add_treenode(parent, name)

            value = self._gen_hashable_value(content['value'])
            candidates = self._gen_hashable_value(content['candidates'])

            #Make sure that the selected value is in the possibly empty set of
            #candidates.
            for candidate in candidates | {value}:
                selected = candidate == value

                if frozenset != type(candidate):
                    self._add_treenode(node, candidate, selected)
                    continue
                setnode = self._add_treenode(node, 'List', selected)
                for element in candidate:
                    self._add_treenode(setnode, element, selected)

    def _add_treenode(self, parent, text, is_bold=False):
        weight = 800 if is_bold else 400
        return self.paramview.get_model().append(parent, [text, weight])

    def on_url_clicked(self, widget, url, event):
        self.paramview.get_model().clear()

        # TODO put this into some class (ModelSearch)?
        current_layer = self.model.by_name[self.combo.get_active_id()]
        # find node
        title = "%s not found in graph" % url
        for node in current_layer.graph.nodes():
            if current_layer.graph.node_attributes(node)['id'] == url:
                #TODO underscores aren't properly rendered
                title = 'Parameters for %s' % node.label()

                nodetree = self._add_treenode(None, "Node Parameters")
                params = current_layer.graph.node_attributes(node)['params']
                self._add_paramtree(nodetree, params)

                for edge in current_layer.graph.out_edges(node):
                    edgetree = self._add_treenode(None, "Edge Parameters")
                    params = current_layer.graph.edge_attributes(edge)['params']
                    self._add_paramtree(edgetree, params)

        self.paramview.expand_all()
        self.paramview.get_column(0).set_title(title)
        return True
