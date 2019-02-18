import os
import re

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Pango

from xdot.ui.window import DotWidget
from xdot.ui.elements import Graph

from mcc.dot import DotFactory
from mcc.framework import Registry
from mcc.importexport import PickleImporter
from mcc import graph as mccgraph

class ModelItem():
    def __init__(self, layer, obj):
        self.layer = layer
        self.obj   = obj


class ParamView():
    def __init__(self):

        model     = Gtk.TreeStore(object, str, int, Pango.Style, str, Pango.Underline, bool, str)
        self.view = Gtk.TreeView.new_with_model(model)

        col = Gtk.TreeViewColumn("No Node selected", Gtk.CellRendererText(),
                                 text=1, weight=2, style=3, foreground=4, underline=5, strikethrough=6, background=7)
        self.view.append_column(col)

        self.default_style = { 'weight'     : 400,
                               'style'      : Pango.Style.NORMAL,
                               'foreground' : 'black',
                               'underline'  : Pango.Underline.NONE,
                               'strikethrough' : False,
                               'background' : 'white' }

    def treeview(self):
        return self.view

    def add_treenode(self, parent, text, style, extra_style=None, link_item=None):
        # merge style with defaults by overwriting defaults values with those of 'style'
        if extra_style is not None:
            combined_style = {**extra_style, **style}
        else:
            combined_style = style
        combined_style = {**self.default_style, **combined_style}

        return self.view.get_model().append(parent, [link_item,
                                                    text, combined_style['weight'],
                                                          combined_style['style'],
                                                          combined_style['foreground'],
                                                          combined_style['underline'],
                                                          combined_style['strikethrough'],
                                                          combined_style['background']])

    def clear(self):
        self.view.get_model().clear()

    def refresh(self, title):
        self.view.expand_all()
        self.view.get_column(0).set_title(title)

class LayerView():
    def __init__(self):
        self.view = Gtk.TreeView.new_with_model(Gtk.ListStore(str))
        col = Gtk.TreeViewColumn("Layers", Gtk.CellRendererText(), text=0)
        self.view.append_column(col)
        self.view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

    def set_layers(self, layers):
        model = self.view.get_model()
        for layer in layers:
            model.append([layer])
        self.view.get_selection().select_iter(model.get_iter_first())

    def treeview(self):
        return self.view

    def selected_layers(self):
        model, paths = self.view.get_selection().get_selected_rows()
        layers = []
        for path in paths:
            layers += [model.get_value(model.get_iter(path), 0)]
        return layers

class Page(Gtk.HPaned):

    def __init__(self, filename, window):
        self.window = window

        Gtk.HPaned.__init__(self)
        self.set_wide_handle(True)

        self.filename = filename

        self._open_pickle(filename)

        self.graph = Graph()
        self._reset_dotwidget()

        self.sidepane = Gtk.VBox()

        self.layerview = LayerView()
        select = self.layerview.treeview().get_selection()
        select.connect('changed', self.show_dot)
        self.layerview.set_layers(self.dotfactory.model.by_name.keys())

        self.paramview = ParamView()

        scroll = Gtk.ScrolledWindow()
        scroll.add_with_viewport(self.paramview.treeview())

        select = self.paramview.treeview().get_selection()
        select.connect('changed', self.on_tree_selection_changed)

        self.sidepane.pack_start(self.layerview.treeview(), False, False, 0)
        self.sidepane.pack_end(scroll, True, True, 0)

    def _reset_dotwidget(self):
        if self.get_child1() is not None: #there is no dotwidget on first call
            self.get_child1().destroy()

        self.dotwidget = DotWidget()
        self.dotwidget.connect("error", lambda e, m: self.error_dialog(m))
        self.dotwidget.connect("clicked", self.on_url_clicked)

        self.pack1(self.dotwidget, True, False)

    def _open_pickle(self, filename):
        self.model = Registry()

        # import model
        importer = PickleImporter(self.model)
        importer.read(filename)

        self.dotfactory = DotFactory(self.model)

    def show_dot(self, _selection):
        layers = self.layerview.selected_layers()
        if not len(layers):
            self._reset_dotwidget()
            self.show_all()
            return
        try:
            dot = self.dotfactory.get_layer(layers[0]).encode('utf-8')
            if self.dotwidget.set_dotcode(dot):
                self.dotwidget.zoom_to_fit()

        except IOError as ex:
            self.error_dialog(str(ex))

    def reload(self):
        self._open_pickle(self.filename)

        # TODO update layer view?

        self.show_dot(None)

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

        #If the sidepane is open and the user switches to a page which he
        #hasn't switched to before, the layer list is printed without any
        #list entries. Besides that, occasionally, the list is also printed
        #emptily if the sidepane was *not* active during the page switch.
        #The tree model data, however, are not empty. If the sidepane is closed
        #and opened again, everything is rendered properly again. So there
        #might be a problem with signals. More concretely, the "preferred size"
        #of the TreeView might be incorrect for some reasons.
        #Workaround: call the following function:
        self.layerview.treeview().get_preferred_size()

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

    def _stylize(self, param, candidates, value):
        style = dict()
        name = param
        if param in self.model.by_name.keys():
            # use italic for inter-layer relations
            style['style'] = Pango.Style.ITALIC

            if self.model.by_name[param] == self._parent_layer():
                name = 'Parent layer (%s)' % param
            elif self.model.by_name[param] == self._child_layer():
                name = 'Child layer (%s)' % param
            else:
                name = 'Layer (%s)' % param

        if len(candidates) == 0:
            # use normal font weight if there was no decision
            style['weight'] = 400

        if value is None or value == 'None':
            # strikethrough if no value assigned
            style['strikethrough'] = True

        return name, style

    def _link(self, layer, value):
        if value in layer.graph.nodes():
            return ModelItem(layer, value)

        if value in layer.graph.edges():
            return ModelItem(layer, value)

        return None

    def _add_value(self, parent, value, layer, style, extra_style=None):
        if type(value) not in {set, frozenset}:
            self.paramview.add_treenode(parent, repr(value), style, extra_style,
                                        link_item=self._link(layer, value))
        else:
            setnode = self.paramview.add_treenode(parent,
                                                  'List',
                                                  style,
                                                  extra_style)
            for element in value:
                self.paramview.add_treenode(setnode, repr(element), style, extra_style,
                                            link_item=self._link(layer, element))

    def _add_paramtree(self, parent, params):
        # TODO toggle params that store inter-layer relations
        for name, content in params.items():

            value      = content['value']
            candidates = content['candidates']

            layer = self._current_layer()
            if name in self.model.by_name.keys():
                layer = self.model.by_name[name]

            name, style = self._stylize(name, candidates, value)
            node = self.paramview.add_treenode(parent, name, style, {'underline' : Pango.Underline.SINGLE})

            self._add_value(node, value, layer, style, {'weight' : 800})

            for candidate in candidates:
                if candidate == value:
                    continue
                self._add_value(node, candidate, layer, style)

    def _parent_layer(self):
        current = self._current_layer()
        return self.model._prev_layer(current)

    def _child_layer(self):
        current = self._current_layer()
        return self.model._next_layer(current)

    def _current_layer(self):
        return self.model.by_name[self.layerview.selected_layers()[0]]

    def on_tree_selection_changed(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter is not None and model[treeiter][0] is not None:
            item = model[treeiter][0]
            if isinstance(item.obj, mccgraph.Edge):
                # TODO edge object do not have an URL in upstream xdot
                url = item.layer.graph.edge_attributes(item.obj)['id']
            else:
                url = item.layer.graph.node_attributes(item.obj)['id']

            found = False
            for element in self.dotwidget.graph.nodes + self.dotwidget.graph.edges:
                if element.url == url:
                    found = True
                    self.dotwidget.set_highlight({element}, search=True)

            if not found:
                print("Cannot find selected item %s with url %s." % (item, url))

        else:
            self.dotwidget.set_highlight(None, search=True)

    def on_url_clicked(self, widget, url, event):
        self.paramview.clear()

        # TODO put this into some class (ModelSearch)?
        current_layer = self._current_layer()
        # find node
        title = "%s not found in graph" % url
        for node in current_layer.graph.nodes():
            if current_layer.graph.node_attributes(node)['id'] == url:
                #TODO underscores aren't properly rendered
                title = 'Parameters for %s' % node.label()

                nodetree = self.paramview.add_treenode(None, "Node Parameters", dict(),
                                                       link_item=ModelItem(current_layer, node))
                params = current_layer.graph.node_attributes(node)['params']
                self._add_paramtree(nodetree, params)

                for edge in current_layer.graph.out_edges(node):
                    edgetree = self.paramview.add_treenode(None, "Edge Parameters", dict(),
                                                           link_item=ModelItem(current_layer, edge))
                    params = current_layer.graph.edge_attributes(edge)['params']
                    self._add_paramtree(edgetree, params)

        self.paramview.refresh(title)
        return True
