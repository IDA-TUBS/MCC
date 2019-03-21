import os
import re

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

from xdot.ui.window import DotWidget
from xdot.ui.elements import Graph

from viewer.page import Page
from viewer import param_clause


class Window(Gtk.ApplicationWindow):

    ui="""
    <?xml version="1.0" encoding="UTF-8"?>
    <!-- Generated with glade 3.22.1 -->
    <interface>
      <requires lib="gtk+" version="3.20"/>
      <object class="GtkBox" id="vbox">
        <property name="visible">True</property>
        <property name="can_focus">False</property>
        <property name="orientation">vertical</property>
        <child>
          <object class="GtkToolbar" id="toolbar">
            <property name="visible">True</property>
            <property name="can_focus">False</property>
            <child>
              <object class="GtkToolButton" id="reload">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="action_name">win.reload</property>
                <property name="label" translatable="yes">Reload</property>
                <property name="use_underline">True</property>
                <property name="stock_id">gtk-refresh</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkToolButton" id="print">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="tooltip_text" translatable="yes">Prints the currently visible part of the graph</property>
                <property name="action_name">win.print</property>
                <property name="label" translatable="yes">Print</property>
                <property name="use_underline">True</property>
                <property name="stock_id">gtk-print</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkSeparatorToolItem">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkToolButton" id="ZoomIn">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="action_name">win.ZoomIn</property>
                <property name="label" translatable="yes">ZoomIn</property>
                <property name="use_underline">True</property>
                <property name="stock_id">gtk-zoom-in</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkToolButton" id="ZoomOut">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="action_name">win.ZoomOut</property>
                <property name="label" translatable="yes">ZoomOut</property>
                <property name="use_underline">True</property>
                <property name="stock_id">gtk-zoom-out</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkToolButton" id="ZoomFit">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="action_name">win.ZoomFit</property>
                <property name="label" translatable="yes">ZoomFit</property>
                <property name="use_underline">True</property>
                <property name="stock_id">gtk-zoom-fit</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkToolButton" id="Zoom100">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="action_name">win.Zoom100</property>
                <property name="label" translatable="yes">Zoom100</property>
                <property name="use_underline">True</property>
                <property name="stock_id">gtk-zoom-100</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkSeparatorToolItem">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkToolItem" id="Find">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="tooltip_text" translatable="yes">Find a node by name or parameter</property>
                <child>
                  <object class="GtkEntry" id="textentry">
                    <property name="visible">True</property>
                    <property name="can_focus">True</property>
                    <property name="activates_default">True</property>
                    <property name="primary_icon_stock">gtk-find</property>
                  </object>
                </child>
              </object>
              <packing>
                <property name="expand">True</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
            <child>
              <object class="GtkToolButton" id="Help">
                <property name="visible">True</property>
                <property name="can_focus">False</property>
                <property name="action_name">win.Help</property>
                <property name="label" translatable="yes">Help</property>
                <property name="use_underline">True</property>
                <property name="stock_id">gtk-help</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="homogeneous">True</property>
              </packing>
            </child>
          </object>
          <packing>
            <property name="expand">False</property>
            <property name="fill">True</property>
            <property name="position">0</property>
          </packing>
        </child>
        <child>
          <object class="GtkNotebook" id="notebook">
            <property name="visible">True</property>
            <property name="can_focus">True</property>
            <property name="enable_popup">True</property>
            <child type="action-start">
              <object class="GtkToolButton" id="new">
                <property name="stock_id">gtk-close</property>
                <property name="visible">True</property>
                <property name="can_focus">True</property>
                <property name="action_name">win.close</property>
              </object>
              <packing>
                <property name="tab_fill">False</property>
              </packing>
            </child>
            <child type="action-end">
              <object class="GtkToggleToolButton" id="hide-pane">
                <property name="stock_id">gtk-index</property>
                <property name="visible">True</property>
                <property name="can_focus">True</property>
              </object>
              <packing>
                <property name="tab_fill">False</property>
              </packing>
            </child>
          </object>
          <packing>
            <property name="expand">True</property>
            <property name="fill">True</property>
            <property name="position">1</property>
          </packing>
        </child>
      </object>
    </interface>
    """

    help_text = """
Search has two possible modes. Depending on the existence of a colon in the \
search text, either labels or parameters are searched through. All matching \
nodes (or edges) are highlighted. Syntax errors are indicated by a highlighted \
search box (usually in red). If only one graph element is highlighted and the \
return key is pressed, the graph viewer scrolls to that graph element. Regular \
expressions are executed by Python's <tt>re.search</tt> method. If the search \
text is empty, nothing is highlighted.

<b>Label search</b> (no colon in search text):
Search for all nodes and edges whose labels are matched by the regular \
expression specified by the search text.

<b>Parameter search</b> (search text contains a colon):
Search for nodes and edges with the specified parameters. In this mode, the \
search text is divided into <u>clauses</u> with whitespace as separator. A \
graph element is highlighted if its parameters satisfy at least one \
<u>clause</u>.

A clause, in turn, is divided into three <u>clause parts</u> with a colon as \
separator. Each <u>part</u> specifies a regular expression for a separate \
"aspect" of the parameters. A node/edge satisfies a <u>clause</u> iff it \
satisfies each of the <u>clause parts</u>. The three <u>parts</u> are \
matched against the following parameter "aspects", respectively:

1. parameter name
2. parameter value category, e.g. "candidate" or "value"
3. parameter value

Note that the third <u>part</u> of a <u>parameter clause</u> is matched \
against a string representation of the parameter value. Thus, the clause \
<tt>::z$</tt> does not match a parameter value <tt>{"abc", "xyz"}</tt> even \
if the strings "abc" and "xyz" are listed separately on the sidepane.

Since whitespace is used as <u>clause</u> separator, use <tt>\s</tt> in order \
to match against whitespace in <u>clause parts</u>.

<b>Examples</b>:

Elements with the substring "CLOUD" in the label:
<tt>CLOUD</tt>

Elements with a trailing number in the label:
<tt>[0-9]$</tt>

Elements with "zynq" in the value of the parameter "mapping"
mapping:value:zynq

Elements which either have a trailing number in a parameter or "right" in a \
service parameter.
::[0-9]$ service::right
"""

    def __init__(self, application, title, width=500, height=500):
        Gtk.Window.__init__(self, title=title, application=application)
        self.set_default_size(width, height)

        builder = Gtk.Builder.new_from_string(self.ui, -1)
        self.add(builder.get_object('vbox'))

        self.last_open_dir = "."
        self.notebook = builder.get_object('notebook')

        # connect toolbar actions
        self._add_simple_action('reload', self.on_reload)
        self._add_simple_action('print', self.on_print)
        self._add_simple_action('ZoomIn', self.on_zoom_in)
        self._add_simple_action('ZoomOut', self.on_zoom_out)
        self._add_simple_action('ZoomFit', self.on_zoom_fit)
        self._add_simple_action('Zoom100', self.on_zoom_100)
        self._add_simple_action('Help', self.on_help)
        self._add_simple_action('close', self.on_close)

        # connect textentry actions
        textentry = builder.get_object('textentry')
        textentry.connect("activate", self.textentry_activate, textentry);
        textentry.connect("changed",  self.textentry_changed,  textentry);

        # connect toggle action
        panebutton = builder.get_object('hide-pane')
        panebutton.connect("toggled", self.toggle_info, panebutton)

        self.notebook.connect('switch-page', self.on_switch_page, panebutton)

        self.show_all()

    def _add_simple_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)

    def on_reload(self, action, param):
        self.current_page().reload()

    def on_zoom_in(self, action, param):
        self.current_widget().on_zoom_in(action)

    def on_zoom_out(self, action, param):
        self.current_widget().on_zoom_out(action)

    def on_zoom_fit(self, action, param):
        self.current_widget().on_zoom_fit(action)

    def on_zoom_100(self, action, param):
        self.current_widget().on_zoom_100(action)

    def on_help(self, action, param):
        #we don't use Dialog's labels because we need scrollable text
        text = Gtk.Label()
        text.set_markup(self.help_text)
        text.set_line_wrap(True)

        scrolled = Gtk.ScrolledWindow()
        scrolled.add_with_viewport(text)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_propagate_natural_width(True)
        #increase readability by limiting line length
        scrolled.set_max_content_width(600)

        dialog = Gtk.MessageDialog(self, 0,
                                   Gtk.MessageType.INFO, Gtk.ButtonsType.OK)
        dialog.set_markup('<b>Search Help</b>')
        dialog.get_message_area().pack_end(scrolled, True, True, 0)
        scrolled.show_all()
        dialog.run()
        dialog.destroy()

    def on_print(self, action, param):
        self.current_widget().on_print(action)

    def on_close(self, action, param):
        self.notebook.remove_page(self.notebook.get_current_page())

    def on_switch_page(self, notebook, page, page_num, panebutton):
        page.toggle_info(panebutton, window=self)

    def toggle_info(self, action, button):
        self.current_page().toggle_info(button, window=self)

    def current_page(self):
        return self.notebook.get_nth_page(self.notebook.get_current_page())

    def current_widget(self):
        return self.current_page().dotwidget

    def _find_items(self, search_text):
        if not len(search_text):
            return []
        try:
            if not param_clause.has_clause(search_text):
                regex = re.compile(search_text)
                return list(self.current_page().find_by_name(regex))

            clauses = list(param_clause.parse(search_text))
            return list(self.current_page().find_by_param(clauses))
        except (re.error, param_clause.SyntaxError):
            return None

    def _highlight_items(self, search_text):
        found_items = self._find_items(search_text)
        to_highlight = [] if found_items is None else found_items
        self.current_widget().set_highlight(to_highlight, search=True)
        return found_items

    def textentry_changed(self, widget, entry):
        context = entry.get_style_context()
        css_class = Gtk.STYLE_CLASS_WARNING
        context.add_class(css_class)
        if self._highlight_items(entry.get_text()) is not None:
            context.remove_class(css_class)

    def textentry_activate(self, widget, entry):
        found_items = self._highlight_items(entry.get_text())
        if(found_items is not None and len(found_items) == 1):
            self.current_widget().animate_to(found_items[0].x, found_items[0].y)

    def open_file(self, filename):
        page = Page(filename, self)
        self.notebook.append_page(page, Gtk.Label(label=os.path.basename(filename)))
        self.notebook.set_tab_reorderable(page, True)
        self.show_all()


    def on_open(self, action):
        chooser = Gtk.FileChooserDialog(parent=self,
                                        title="Open Model",
                                        action=Gtk.FileChooserAction.OPEN,
                                        buttons=(Gtk.STOCK_CANCEL,
                                                 Gtk.ResponseType.CANCEL,
                                                 Gtk.STOCK_OPEN,
                                                 Gtk.ResponseType.OK))
        chooser.set_default_response(Gtk.ResponseType.OK)
        chooser.set_current_folder(self.last_open_dir)
        filter = Gtk.FileFilter()
        filter.set_name("Pickle files")
        filter.add_pattern("*.pickle")
        chooser.add_filter(filter)
        filter = Gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        chooser.add_filter(filter)
        if chooser.run() == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            self.last_open_dir = chooser.get_current_folder()
            chooser.destroy()
            self.open_file(filename)
        else:
            chooser.destroy()
