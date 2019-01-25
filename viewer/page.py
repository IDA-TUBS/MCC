import os
import re

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from xdot.ui.window import DotWidget
from xdot.ui.elements import Graph

class Page(Gtk.HPaned):

    def __init__(self, filename, window):
        self.window = window

        Gtk.HPaned.__init__(self)
        self.set_wide_handle(True)

        self._open_xml(filename)

        self.graph = Graph()

        self.dotwidget = DotWidget()
        self.dotwidget.connect("error", lambda e, m: self.error_dialog(m))

        self.sidepane = Gtk.VBox()
        combo = Gtk.ComboBoxText()
        for choice in self.dot_files.keys():
            combo.append(choice, choice)
        combo.connect('changed', self.show_dot)

        self.sidepane.pack_start(combo, True, False, 0)

        self.pack1(self.dotwidget, True, False)

        combo.set_active(0)

    def _open_xml(self, filename):
        self.dot_files = { 'func_arch' : None,
                           'comm_arch' : None,
                           'comp_arch-pre1' : None,
                           'comp_arch-pre2' : None,
                           'comp_arch' : None,
                           'comp_inst' : None }

        for f in self.dot_files:
            self.dot_files[f] = filename.replace('model.xml', '%s.dot' % f)

    def show_dot(self, box):
        name = box.get_active_id()
        filename = self.dot_files[name]
        try:
            fp = open(filename, 'rb')
            if self.dotwidget.set_dotcode(fp.read(), filename):
                self.dotwidget.zoom_to_fit()
            fp.close()

        except IOError as ex:
            self.error_dialog(str(ex))


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
