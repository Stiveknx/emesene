'''renderers for the ContactList'''
# -*- coding: utf-8 -*-

#    This file is part of emesene.
#
#    emesene is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    emesene is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with emesene; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from __future__ import division

import sys

from gi.repository import Gtk, Gdk, GObject, GdkPixbuf
from gi.repository import Pango, PangoCairo
import cairo

from gui.base import Plus
import MarkupParser
import extension
from AvatarManager import AvatarManager

import logging
log = logging.getLogger('gtkui.Renderers')

class CellRendererFunction(Gtk.CellRenderer):
    '''
CellRenderer that behaves like a label, but apply a function to "markup"
to show a modified nick. Its a base class, and it is intended to be
inherited by extensions.
'''
    __gproperties__ = {
            'markup': (GObject.TYPE_STRING,
                "text",
                "text we'll display (even with plus markup!)",
                '', #default value
                GObject.PARAM_READWRITE),
            'ellipsize': (GObject.TYPE_BOOLEAN,
                "",
                "",
                True, #default value
                GObject.PARAM_READWRITE)
            }

    property_names = __gproperties__.keys()

    def __init__(self, function):
        Gtk.CellRenderer.__init__(self)
        self.__dict__['markup'] = ''
        self.function = function

    def __getattr__(self, name):
        try:
            return self.get_property(name)
        except TypeError:
            raise AttributeError, name

    def __setattr__(self, name, value):
        try:
            self.set_property(name, value)
        except TypeError:
            self.__dict__[name] = value

    def do_get_preferred_width(self, wid):
        #FIXME: calculate real witdh
        return 100, 100

    def do_get_preferred_height(self, wid):
        height, lines = self.calculate_line_height_and_count()
        min_height = height + self.ypad * 2
        natural_height = height + self.ypad * 2
        return min_height, natural_height

    def do_get_property(self, prop):
        '''return the value of prop if exists, raise TypeError if not found'''
        if prop.name not in self.property_names:
            raise TypeError('No property named %s' % (prop.name,))

        return self.__dict__[prop.name]

    def do_set_property(self, prop, value):
        '''set the value of prop if exists, raise TypeError if not found'''
        if prop.name not in self.property_names:
            raise TypeError('No property named %s' % (prop.name,))

        if prop == 'markup': #plus formatting
            value = Plus.msnplus_to_dict

        self.__dict__[prop.name] = value

    def do_render(self, ctx, widget, bgnd_area, cell_area, flags):
        '''Called by gtk to render the cell.'''
        x_coord = cell_area.x + self.xpad
        y_coord = cell_area.y + self.ypad
        height = cell_area.height - self.ypad
        width = cell_area.width - self.xpad

        total_text_height, total_lines_count = self.calculate_line_height_and_count()
        y_padding = max(((height - total_text_height) / (total_lines_count * 2)), 0)

        #add padding to first line
        y_coord += y_padding / 2

        self.calculate_positions(ctx, widget, x_coord, y_coord)
        context = widget.get_style_context()

    def calculate_positions(self, ctx, widget, x_base=0, y_base=0):
        '''calculate x,y coord of each element'''
        current_line = 1
        lines_height = self.calculate_lines_height()

        #base coord
        x_coord = x_base
        y_coord = y_base

        context = widget.get_style_context()

        for w in self.update_markup():
            if isinstance(w, basestring):
                lines = w.split("\n")
                lines_count = len(lines)
                for i in range(0, lines_count):
                    lbl = Gtk.Label()
                    lbl.set_markup(lines[i])
                    layout = lbl.get_layout()
                    Gtk.render_layout(context, ctx, x_coord, y_coord, layout)

                    #if we aren't in last line then update coords
                    if lines_count > 1 and i != lines_count - 1:
                        x_coord = x_base
                        y_coord += lines_height[current_line]
                        #avoid moving on last line, since we can have pixbuf in it
                        current_line += i
                    else:
                        #update only x coord because we can have smileys in this line
                        x_coord += lbl.get_preferred_width()[1]
            elif isinstance(w, GdkPixbuf.Pixbuf):
                #scale image to the text height
                size = min(lines_height[current_line], w.get_width())
                pix = w.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
                Gtk.render_icon(context, ctx, pix, x_coord, y_coord)
                x_coord += pix.get_width()
            else:
                log.error("unhandled type %s" % type(i))

    def calculate_line_height_and_count(self):
        '''return the total height. Text height takes precedence,
            if there isn't any text, take image height otherwise returns 0.
            we also returns the lines count'''
        lines_height = self.calculate_lines_height()
        total_height = 0
        for i in lines_height.itervalues():
            total_height += i
        return (total_height, len(lines_height))

    def calculate_lines_height(self):
        '''calculate the height of each line'''
        current_line = 1
        lines_height = {}

        for w in self.update_markup():
            if isinstance(w, basestring):
                lines = w.split("\n")
                lines_count = len(lines)
                for i in range(0, lines_count):
                    if i < lines_count:
                        current_line += i
                    lbl = Gtk.Label()
                    lbl.set_markup(lines[i])
                    lines_height[current_line] = max(lines_height.get(current_line, 0), lbl.get_preferred_height()[1])
            elif isinstance(w, GdkPixbuf.Pixbuf):
                #if pixbuf is longer than text we scale down
                lines_height[current_line] = min(lines_height.get(current_line, 0), w.get_height())
            else:
                log.error("unhandled type %s" % type(i))

        return lines_height

    def update_markup(self):
        '''Gets the Pango layout used in the cell in a TreeView widget.'''
        try:
            decorated_markup = self.function(self.markup)
        except Exception, error: #We really want to catch all exceptions
            log.error("this nick: '%s' made the parser go crazy, striping. Error: %s" % (
                    self.markup, error))
            try:
                decorated_markup = self.function(self.markup, False)
            except Exception, error: #We really want to catch all exceptions
                log.error("Even stripping plus markup doesn't help. Error: %s" % error)
                decorated_markup = self.markup

        return decorated_markup

plus_or_noplus = 1 # 1 means plus, 0 means noplus

def plus_text_parse(item, plus=True):
    '''parse plus in the contact list'''
    global plus_or_noplus
    # get a plain string with objects
    if plus_or_noplus and plus:
        item = Plus.msnplus_parse(item)
    else:
        item = Plus.msnplus_strip(item)
    return item

def msnplus_to_list(text, plus=True):
    '''parse text and return a list of strings and GdkPixbuf.Pixbufs'''
    text = plus_text_parse(text, plus)
    text = MarkupParser.replace_markup(text)
    text_list = MarkupParser.replace_emoticons(text)
    return text_list

class CellRendererPlus(CellRendererFunction):
    '''Nick renderer that parse the MSN+ markup, showing colors, gradients and
    effects'''

    NAME = 'Cell Renderer Plus'
    DESCRIPTION = _('Parse MSN+ markup, showing colors, gradients and effects')
    AUTHOR = 'Mariano Guerra'
    WEBSITE = 'www.emesene.org'

    def __init__(self):
        global plus_or_noplus
        plus_or_noplus = 1
        CellRendererFunction.__init__(self, msnplus_to_list)

extension.implements(CellRendererPlus, 'nick renderer')

GObject.type_register(CellRendererPlus)

class CellRendererNoPlus(CellRendererFunction):
    '''Nick renderer that "strip" MSN+ markup, not showing any effect/color,
    but improving the readability'''

    NAME = 'Cell Renderer No Plus'
    DESCRIPTION = _('Strip MSN+ markup, not showing any effect/color, but improving the readability')
    AUTHOR = 'Mariano Guerra'
    WEBSITE = 'www.emesene.org'


    def __init__(self):
        global plus_or_noplus
        plus_or_noplus = 0
        CellRendererFunction.__init__(self, msnplus_to_list)

extension.implements(CellRendererNoPlus, 'nick renderer')

GObject.type_register(CellRendererNoPlus)


class SmileyLabel(Gtk.CellView):
    def __init__(self):
        Gtk.CellView.__init__(self)
        self._model = Gtk.ListStore(str)
        self.set_model(self._model)
        self.crt = extension.get_and_instantiate('nick renderer')
        self.crt.set_property('ellipsize', Pango.ELLIPSIZE_END)
        self.pack_start(self.crt, False)
        self.add_attribute(self.crt, 'markup', 0)
        self._text = ""

    def set_text(self, text=''):
        self._text = text
        self._model.clear()
        iter_ = self._model.append([text])
        path = self._model.get_path(iter_)
        self.set_displayed_row(path)

    def set_markup(self, text=''):
        self.set_text(text)

    def get_markup(self):
        return self._text

    def set_ellipsize(self, mode=Pango.ELLIPSIZE_END):
        self.crt.set_property('ellipsize', mode)

    def set_alignment(self, x=0.0, y=0.5):
        #FIXME: aligment??
#        self.x_align = x
#        self.y_align = y
        pass

    def set_angle(self, angle):
        #FIXME: add support for this in cellrenderer
        if angle in [0, 180]:
             self.set_orientation(Gtk.Orientation.HORIZONTAL)
        elif angle in [90, 270]:
            self.set_orientation(Gtk.Orientation.VERTICAL)
        else:
            log.error("unhandled angle %d" % angle)

GObject.type_register(SmileyLabel)

#from emesene1 by mariano guerra adapted by cando
#animation support by cando
#TODO add transformation field in configuration
#TODO signals in configuration for transformation changes????

class AvatarRenderer(Gtk.CellRendererPixbuf, AvatarManager):
    """Renderer for avatar """

    __gproperties__ = {
        'image': (GObject.TYPE_OBJECT, 'The contact image', '',
            GObject.PARAM_READWRITE),
        'blocked': (bool, 'Contact Blocked', '', False,
            GObject.PARAM_READWRITE),
        'dimension': (GObject.TYPE_INT, 'cell dimensions',
            'height width of cell', 0, 96, 32,
            GObject.PARAM_READWRITE),
        'offline': (bool, 'Contact is offline', '', False,
            GObject.PARAM_READWRITE),
        'radius-factor': (GObject.TYPE_FLOAT, 'radius of pixbuf',
            '0.0 to 0.5 with 0.1 = 10% of dimension', 0.0, 0.5, 0.11,
            GObject.PARAM_READWRITE),
         }

    def __init__(self, cell_dimension = 32, cell_radius = 0.11):
        GObject.GObject.__init__(self)
        AvatarManager.__init__(self, cell_dimension, cell_radius)

        #icon source used to render grayed out offline avatar
        self._icon_source = Gtk.IconSource()
        self._icon_source.set_state(Gtk.StateType.INSENSITIVE)

        self.set_property('xpad', 1)
        self.set_property('ypad', 1)

        #set up information of statusTransformation
        self._set_transformation('corner|gray')
        #self.transId = self._config.connect('change::statusTransformation',
            #self._transformation_callback)

    def destroy(self):
        self._config.disconnect(self.transId)
        Gtk.CellRendererPixbuf.destroy(self)

    def _get_padding(self):
        return (self.get_property('xpad'), self.get_property('ypad'))

    def _set_transformation(self, setting):
        transformation = setting.split('|')
        self._corner = ('corner' in transformation)
        self._alpha_status = ('alpha' in transformation)
        self._gray = ('gray' in transformation)

    def _transformation_callback(self, config, newvalue, oldvalue):
        self._set_transformation(newvalue)

    def do_get_preferred_width(self, wid):
        width = self._dimension
        min_width = width
        natural_width = width
        return min_width, natural_width

    def do_get_preferred_height(self, wid):
        height = self._dimension
        min_height = height
        natural_height = height
        return min_height, natural_height

    def func(self, model, path, iter, image_and_tree):
      image, tree = image_and_tree
      if model.get_value(iter, 0) == image:
         self.redraw = 1
         cell_area = tree.get_cell_area(path, tree.get_column(1))
         tree.queue_draw_area(cell_area.x, cell_area.y, cell_area.width,
            cell_area.height)

#FIXME: get_iter didn't function
#    def animation_timeout(self, tree, image):
#       if image.get_storage_type() == Gtk.ImageType.ANIMATION:
#          self.redraw = 0
#          image.get_data('iter').advance()
#          model = tree.get_model()
#          model.foreach(self.func, (image, tree))

#          if self.redraw:
#             GObject.timeout_add(image.get_data('iter').get_delay_time(),
#                self.animation_timeout, tree, image)
#          else:
#             image.set_data('iter', None)

    def do_render(self, ctx, widget, bg_area, cell_area, flags):
        """Prepare rendering setting for avatar"""
        xpad, ypad = self._get_padding()
        x = cell_area.x
        y = cell_area.y
        width = cell_area.width
        height = cell_area.height

        ctx.translate(x, y)

        avatar = None
        alpha = 1
        dim = self._dimension

        if self._image.get_storage_type() == Gtk.ImageType.ANIMATION:
#FIXME: this is broken on gtk3, use static pixbuf for now
#           if not self._image.get_data('iter'):
#                animation = self._image.get_animation()
#                self._image.set_data('iter', animation.get_iter())
#                GObject.timeout_add(self._image.get_data('iter').get_delay_time(),
#                   self.animation_timeout, widget, self._image)

#            avatar = self._image.get_data('iter').get_pixbuf()
            avatar = self._image.get_pixbuf()

        elif self._image.get_storage_type() == Gtk.ImageType.PIXBUF:
            avatar = self._image.get_pixbuf()
        else:
           return

        if self._gray and self._offline and avatar != None:
            alpha = 1
            source = self._icon_source
            source.set_pixbuf(avatar)
            context = widget.get_style_context()
            context.set_state(Gtk.StateFlags.INSENSITIVE)
            avatar = Gtk.render_icon_pixbuf (context, source, -1)

        if avatar:
            self.draw_avatar(ctx, avatar, width - dim, ypad, dim,
                Gdk.Gravity.CENTER, self._radius_factor, alpha)

GObject.type_register(AvatarRenderer)
