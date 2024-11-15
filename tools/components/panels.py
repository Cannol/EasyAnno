from logging import Logger
import tkinter as tkk
from tkinter import ttk
from tkinter import simpledialog, filedialog, messagebox
# from math import ceil, modf
from bases.video_reader import VideoSequence
from bases.workspace import SharedNamespace, AttrType, VideoAnnotation
from bases.attrs import SingleAttr, MultiObjAttr
import os
# import sys

# from typing import Literal
# import yaml
from functools import partial

from PIL import Image, ImageTk

from common.logger import LoggerMeta
# from .plugs import MemoryValidateTag

from bases.targets import Target

import numpy as np

# from threading import Lock
import time

class ScrollPanel(object):
    
    _L: Logger = None

    def __init__(self, common_master, scroll_canvas: tkk.Canvas, x=True, y=True, cnf={}, **kw):

        self._master = common_master

        self._use_x = x
        self._use_y = y

        self._scroll_canvas = scroll_canvas
        if x:
            self._scroll_x_bar = tkk.Scrollbar(self._master, orient='horizontal', command=self._scroll_canvas.xview)
            self._scroll_canvas.configure(xscrollcommand=self._scroll_x_bar.set)
        if y:
            self._scroll_y_bar = tkk.Scrollbar(self._master, orient='vertical', command=self._scroll_canvas.yview)
            self._scroll_canvas.configure(yscrollcommand=self._scroll_y_bar.set)

    def construct_all(self):
        if self._use_x:
            self._scroll_x_bar.pack(side=tkk.BOTTOM, fill=tkk.X)
        if self._use_y:
            self._scroll_y_bar.pack(side=tkk.RIGHT, fill=tkk.Y)
        self._scroll_canvas.pack(anchor=tkk.NW, fill=tkk.BOTH, expand=True)
        

class PopSelectMenu(tkk.Menu, metaclass=LoggerMeta):
    _L: Logger = None

    def __init__(self, master, selections:dict, cnf={}, **kw):
        if kw.get('bg') is None:
            kw['bg'] = 'Grey'
        super().__init__(master, cnf, tearoff=0, **kw)

        self._selections = selections

        for s, func in self._selections.items():
            if func is None:
                self.add_separator()
            else:
                self.add_command(label=s, command=func)


def EMPTY_FRAME_CTRL_HOOK(self, i: int): pass
def EMPTY_EVENT_HOOK(self, event = None): pass

class SequencePanel(tkk.Canvas, metaclass=LoggerMeta):
    
    _L: Logger = None

    EMPTY_ELEMS = {
        "fill": "orange",
        "outline": "red",
        "width": 1
    }

    SELECTED_ELEMS = {
        "fill": "Cyan",
        "outline": None,
        "width": 0
    }

    VALUED_ELEMS = {
        "fill": "YellowGreen",
        "outline": None,
        "width": 0
    }

    def __init__(self, master, block_height, block_width, block_nums=-1, menu_items=None, cnf={}, **kw):
        if kw.get('bg') is None:
            kw['bg'] = 'Grey'
        super().__init__(master, cnf, **kw)

        self._master = master
        self._menu_dict = {}
        self._menu_items = menu_items

        self._data_matrix = []     # each row is a numpy object
        self._data_name = []       # the name is connected to the items in left panel
        # self._attr_type = []       # link to a AttrType object
        self._pop_menu = []        # save pop menu component pointer
        self._rectanges = []       # block objects in canvas

        self._rows = 0             # 当前的总条目数
        self._cols = block_nums     # 每个条目的长度

        self._change_indexes = []  # 每次操作的帧索引
        self._selected_row = -1
        self._selected_type = None
        self._rects = None

        self._text_list = []
        self._label_list = []

        self._mini_height = block_height   # 每一个帧方块的高
        self._mini_width = block_width     # 每一个帧方块的宽
        self._width_total = self._mini_width * self._cols
        self._height_total = 0

        self._video_frame_locate_hook = EMPTY_FRAME_CTRL_HOOK      # 帧变化钩子函数
        # self._bar_changed_event_hook = EMPTY_EVENT_HOOK

        # control params
        self._button_down = False
        self._n_justnow = -1

        self.bind("<Button-1>", self.mouse_down)
        self.bind("<B1-Motion>", self.mouse_move)
        self.bind("<ButtonRelease-1>", self.mouse_release)
        self.bind("<Button-3>", self._change_value)

        if menu_items:
            self._create_menu(menu_items)

    def set_items(self, attrs): 
        self._create_menu(attrs)

    def set_length(self, length): self._cols = length

    @property
    def RowHeight(self): return self._mini_height

    def _create_menu(self, menu_items: dict):
        self._menu_dict.clear()
        if menu_items is not None:
            for menu_type, selections in menu_items.items():
                # print(menu_items)
                selection_with_func = {}
                for k, _ in selections.items():
                    selection_with_func[k] = partial(self._select_menu_item, k, selections)
                
                selection_with_func["--"] = None   # 表示横线
                selection_with_func["删除属性标记"] = self._delete_between
                selection_with_func["取消选择"] = self._roll_back
                self._menu_dict[menu_type] = PopSelectMenu(self._master, selections=selection_with_func)
    
    def _select_menu_item(self, value, obj: AttrType):
        # print(f'select: {value}')
        self._selected_type = obj
        target_value = obj[value]
        for i in self._change_indexes:
            self._data_matrix[self._selected_row][i] = target_value
            self.itemconfig(self._rects[i], **self.VALUED_ELEMS)

        self._L.debug("set value from %d to %d: %s (%d)" % (min(self._change_indexes), max(self._change_indexes), obj[target_value], target_value))
        self._change_indexes.clear()
        self.refresh_text()

    def _delete_between(self):
        
        for i in self._change_indexes:
            self.itemconfig(self._rects[i], **self.EMPTY_ELEMS)
            self._data_matrix[self._selected_row][i] = -1

        self._change_indexes.clear()
        self.refresh_text()

        # print(f"delete from {min(self._change_indexes)} to {max(self._change_indexes)}")
    
    def refresh_text(self):
        _text_list = self._text_list[self._selected_row]
        _label_list = self._label_list[self._selected_row]

        for text in _text_list:
            self.delete(text)

        _text_list.clear()
        _label_list.clear()

        pre_v = -2
        for i, v in enumerate(self._data_matrix[self._selected_row]):
            if pre_v != v:
                pre_v = v
                _label_list[i] = v
        for i, v in _label_list.items():
            if v >= 0:
                text = self.create_text(i*self._mini_width, self._selected_row*self._mini_height, 
                                        anchor="nw",
                                        text=self._selected_type[int(v)], 
                                        fill='black', 
                                        font=('Arial', 10))
                _text_list.append(text)
    
    def bind_controller(self, controller: callable):
        self._video_frame_locate_hook = controller

    def _bar_change_refresh(self):
        if self._rows > 0:
            x1, y1, x2, y2 = self.bbox('all')
            self.configure(scrollregion=(0, 0, x2, y2))
        else:
            self.configure(scrollregion=(0, 0, 0, 0))

    def _draw_bar(self):
        self._L.info(f'Draw bar row: {self._rows}')
        y1_locate = self._rows * self._mini_height
        y2_locate = y1_locate + self._mini_height
        
        rects = []
        for i in range(self._cols):
            rects.append(
                self.create_rectangle(i*self._mini_width, y1_locate, (i+1)*self._mini_width, y2_locate, **self.EMPTY_ELEMS))
        self._rectanges.append(rects)
        self._rows += 1
        self._height_total = self._rows * self._mini_height

        self._bar_change_refresh()

        self._text_list.append([])
        self._label_list.append({})

    def _delete_bar(self, index: int):
        try:
            rects = self._rectanges.pop(index)
        except Exception as e:
            self._L.error("try to delete a bar that not exist.")
            return
        for rect in rects:
            self.delete(rect)
        self._rows -= 1

        self._bar_change_refresh()
        
    def add_bar(self, name: str, seq_type: str, seq_data: np.ndarray = None):
        if seq_data is None:
            seq_data = -np.ones(self._cols, dtype=int)
        
        self._data_matrix.append(seq_data)
        self._data_name.append(name)
        self._pop_menu.append(self._menu_dict[seq_type])
        self._draw_bar()

        self._L.info("Add new name: %s" % name)
        return seq_data

    def remove_bar(self, index: int):
        if self._rows > 0:
            self._data_matrix.pop(index)
            self._data_name.pop(index)
            self._pop_menu.pop(index)
            self._delete_bar(index)
            
    def get_off_x(self): return self.xview()[0]
    def get_off_y(self): return self.yview()[0]

    def _change_value(self, event):

        if len(self._change_indexes) > 0:
            self._roll_back()
            return
        
        if self._rows > 0 and event.y < self._height_total:
            offy = self.get_off_y() * self._height_total
            self._selected_row = int((event.y + offy) // self._mini_height)

            offx = self.get_off_x() * self._width_total
            n = int((event.x + offx) // self._mini_width)
            value = self._data_matrix[self._selected_row][n]
            if value == -1:
                return
            
            _data_array = self._data_matrix[self._selected_row]
            self._rects = self._rectanges[self._selected_row]

            start = n
            while start >= 0 and _data_array[start] == value:
                start -= 1
            start += 1
            end = n
            while end < self._cols and _data_array[end] == value:
                end += 1
            end -= 1
            for i in range(start, end+1):
                self.itemconfig(self._rects[i], **self.SELECTED_ELEMS)
                self._change_indexes.append(i)
            self._pop_menu[self._selected_row].post(event.x_root, event.y_root)

    def mouse_down(self, event):
        if len(self._change_indexes) > 0:
            self._roll_back()
            return

        if self._rows > 0 and event.y < self._height_total:

            offy = self.get_off_y() * self._height_total
            self._selected_row = int((event.y + offy) // self._mini_height)

            offx = self.get_off_x() * self._width_total
            n = int((event.x + offx) // self._mini_width)

            self._rects = self._rectanges[self._selected_row]
            self._change_indexes.append(n)
            self.itemconfig(self._rects[n], **self.SELECTED_ELEMS)
            self._n_justnow = n
            self._button_down = True
        
    def mouse_move(self, event):
        if self._button_down:
            offx = self.get_off_x() * self._width_total
            n = int((event.x + offx) // self._mini_width)
            n = min(max(0, n), self._cols-1)
            if n >= self._n_justnow:
                for i in range(self._n_justnow, n+1):
                    self.itemconfig(self._rects[i], **self.SELECTED_ELEMS)
                    self._change_indexes.append(i)
            else:
                for i in range(n, self._n_justnow+1):
                    self.itemconfig(self._rects[i], **self.SELECTED_ELEMS)
                    self._change_indexes.append(i)
            self._n_justnow = n

    def mouse_release(self, event):
        if self._button_down:
            self._button_down = False
            self._pop_menu[self._selected_row].post(event.x_root, event.y_root)


    def _roll_back(self):
        if len(self._change_indexes) > 0:
            for i in self._change_indexes:
                if self._data_matrix[self._selected_row][i] == -1:
                    self.itemconfig(self._rects[i], **self.EMPTY_ELEMS)
                else:
                    self.itemconfig(self._rects[i], **self.VALUED_ELEMS)
            self._change_indexes.clear()

# class NamePanel(tkk.Canvas, metaclass=LoggerMeta):
#     _L: Logger = None

#     EMPTY_ELEMS = {
#         "fill": "orange",
#         "outline": "red",
#         "width": 1
#     }

#     def __init__(self, master, bind_sequence_panel: SequencePanel, width, cnf={}, **kw):
#         if kw.get('bg') is None:
#             kw['bg'] = 'Grey'
#         super().__init__(master, cnf, width=width, **kw)
        
#         self._seq_panel = bind_sequence_panel
#         self._mini_height = self._seq_panel.RowHeight
#         self._bar_width = width - 2
#         self._text_padding = 2
#         self._start_x = 1
#         self._name_list = []
#         self._bar_rects = []
#         self._attr_objs = []
#         self._rows = 0

#         self._bar_change_refresh()

#     def _draw_bar(self):
#         y1_locate = self._rows * self._mini_height
#         y2_locate = y1_locate + self._mini_height
        
#         rect = self.create_rectangle(self._start_x, y1_locate, self._bar_width, y2_locate, **self.EMPTY_ELEMS)
#         self._bar_rects.append(rect)

#         name = self.create_text(self._start_x, y1_locate, 
#                                 anchor="nw",
#                                 text=self._attr_objs[self._rows], 
#                                 fill='black', 
#                                 font=('Arial', 10))
#         self._name_list.append(name)

#         self._rows += 1
#         self._height_total = self._rows * self._mini_height

#     def add_item(self, attr_obj_name):
#         self._attr_objs.append(attr_obj_name)
#         self._draw_bar()
#         self._bar_change_refresh()

#     def _bar_change_refresh(self):
#         if self._rows > 0:
#             x1, y1, x2, y2 = self.bbox('all')
#             self.configure(scrollregion=(0, 0, x2, y2))
#         else:
#             self.configure(scrollregion=(0, 0, 0, 0))

        # self.addtag_enclosed
# class FrameSelectionPanel(tkk.Frame, metaclass=LoggerMeta):
    
#     _L: Logger = None

#     controler = None
     
#     def __init__(self, master, cnf={}, **kw):
#         if kw.get('bg') is None:
#             kw['bg'] = 'Grey'
#         super().__init__(master, cnf, **kw)
#         win = self
#         self.root = tkk.Frame(win)
#         self.left = tkk.Frame(win, width=240, bg="red")

#         self.seq_panel = SequencePanel(self.root, 20, 10, 100)

#         self.scroll_panel = ScrollPanel(self.root, self.seq_panel)

#         # self.name_panel = NamePanel(self.left, self.seq_panel, 200)

#         # self.scroll_panel_left = ScrollPanel(self.left, self.name_panel, y=False)
#         # # tkk.Button(root, command=seq)

#         # # scroll_panel.pack(anchor=tkk.NW, fill=tkk.BOTH, expand=True)
#         # self.left.pack(side=tkk.LEFT, fill=tkk.Y, expand=False)
#         # name_panel.pack(side=tkk.LEFT, fill=tkk.BOTH, expand=True)
#         self.root.pack(side=tkk.RIGHT, fill=tkk.BOTH, expand=True)
#         self.scroll_panel.construct_all()
#         # self.scroll_panel_left.construct_all()

#     def configurate_menus(self, menu_items):
        
#         self.seq_panel.set_items(menu_items)

#     def configurate_length(self, length):
#         self.seq_panel.set_length(length)
    
#     def add_item(self, name, seq_type, seq_data=None):
#         return self.seq_panel.add_bar(name, seq_type, seq_data)

def justify_xy(x1, y1, x2, y2):
    if x1 > x2:
        return (x2, y2, x1, y1) if y1 > y2 else (x2, y1, x1, y2)
    else:
        return (x1, y2, x2, y1) if y1 > y2 else (x1, y1, x2, y2)

def SHAPE_CHANGE_EVENT_HOOK(name, new_points, *args): print(name, new_points)

class ShapeBase(object):
    DRAW_LOCK = False
    SELECTED_OBJECTS = []
    _root: tkk.Canvas = None
    # _map = {}

    def __init__(self, name):
        self._name = name
        self._anonymous = True if self._name=='' else False

        self._mouse_x_start = -1
        self._mouse_y_start = -1

        self._mouse_x_start_pre = -1
        self._mouse_y_start_pre = -1

        self.__moving = False

        self._shape_change_hook = SHAPE_CHANGE_EVENT_HOOK
    
    def remove(self):
        self._name = None
        self._anonymous = None

        self.__moving = False

        self._shape_change_hook = None
        if self in self.SELECTED_OBJECTS:
            self.SELECTED_OBJECTS.remove(self)

    @property
    def Name(self): return self._name

    def bind_shape_change_hook(self, func): self._shape_change_hook = func
    
    def __on_mouse_left_press(self, event):
        self.__moving = True
        self._mouse_x_start_pre = self._mouse_x_start = event.x
        self._mouse_y_start_pre = self._mouse_y_start = event.y

    def __on_mouse_left_btn_move(self, event):

        if self.__moving:

            if ShapeBase.DRAW_LOCK:
                return
            
            dx = event.x - self._mouse_x_start
            dy = event.y - self._mouse_y_start

            self._mouse_x_start, self._mouse_y_start = event.x, event.y

            self._root.move(self._name, dx, dy)
    
    def _moved_hook(self, dx, dy): pass
    
    def __on_mouse_release(self, event):
        if self.__moving:
            self._moved_hook(dx = self._mouse_x_start - self._mouse_x_start_pre,
                            dy = self._mouse_y_start - self._mouse_y_start_pre)
            self.__moving = False

    def move(self, x, y):
        self._root.moveto(self._name, x, y)
    
    @classmethod
    def ClearSelection(cls):
        cls.SELECTED_OBJECTS.clear()
        cls._root.itemconfig('handle', state='hidden')

    @classmethod
    def BindCanvasRoot(cls, root: tkk.Canvas): cls._root = root

    def open_parent_events(self):
        self._root.tag_bind(self._name, sequence="<Button-1>", func=self.__on_mouse_left_press)
        self._root.tag_bind(self._name, sequence="<B1-Motion>",func=self.__on_mouse_left_btn_move)
        self._root.tag_bind(self._name, sequence="<ButtonRelease-1>", func=self.__on_mouse_release)

class TRectangle(ShapeBase):

    def __init__(self, name, x1, y1, x2, y2, alpha=1.0, handle_r=3, **kwargs):
        super().__init__(name)
        
        self._image = None
        self._image_tk = None
        self._rect = None
        self._alpha = int(alpha * 255)
        self._fill_name = kwargs.get('fill', 'red')
        self._outline = kwargs.get('outline', 'red')
        # if self._fill_name == '':
        #     self._fill = None
        # else:
        self._fill = self._root.winfo_rgb(self._fill_name) + (self._alpha,)
        self._width = kwargs.get('width', 1)

        self._points = []

        self._update_inner_params(x1, y1, x2, y2)
        
        # assert self._inner_h > 0 and self._inner_w > 0

        self.draw_rect()
        self.fill_color()

        self._handle = []

        self._change_handle = None
        
        self._anchor_point = None
        self._handle_r = handle_r

        if not self._anonymous:
            self._root.addtag_withtag(self._name, self._rect)
            self._root.addtag_withtag(self._name, self._image_tk)
            self.make_handle(r=self._handle_r, fill='yellow', outline='white', state='hidden', tag=[self._name, 'handle'])

            self.open_parent_events()
            self._root.tag_bind(self._name, sequence="<Button-1>", func=self._on_mouse_left_click, add=True)
            self._root.tag_bind(self._name, sequence="<Shift-Button-1>", func=self._on_mouse_left_click_with_shift, add=True)

            # self._root.tag_bind('handle', sequence="<Button-1>", func=self._handle_left_btn)
            
            # self._root.tag_bind(self._name, sequence="<Leave>", func=self._on_mouse_leave)

    def _moved_hook(self, dx, dy):
        if dx == 0 and dy == 0: return
        self._x1 += dx
        self._x2 += dx
        self._y1 += dy
        self._y2 += dy
        self._update_inner_params_fast()
        self._shape_change_hook(name=self._name, new_points=np.array(self._points))

    def _on_handle_click(self, event, which):
        ShapeBase.DRAW_LOCK = True
        t_index = (which+2)%4
        self._anchor_point = self._points[t_index]
        self._change_handle = self._points[which]
        
    def _on_handle_move(self, event):
        # self._root.moveto(self._change_handle, event.x, event.y)
        self.coords(self._anchor_point[0], self._anchor_point[1], event.x, event.y)

    def _on_handle_release(self, event):
        ShapeBase.DRAW_LOCK = False
        self._shape_change_hook(name=self._name, new_points=np.array(self._points))

    def _on_mouse_left_click(self, event):
        if ShapeBase.DRAW_LOCK: return
        
        self.ClearSelection()
        self.show_handle()
        self.SELECTED_OBJECTS.append(self)

    def _on_mouse_left_click_with_shift(self, event):
        if ShapeBase.DRAW_LOCK: return
        self.show_handle()
        self.SELECTED_OBJECTS.append(self)

    def show_handle(self):
        for _handle in self._handle:
            self._root.itemconfig(_handle, state='normal')

    def hidden_handle(self, indexes):
        for _handle in indexes:
            self._root.itemconfig(self._handle[_handle], state='hidden')

    def draw_rect(self):
        if self._rect is None:
            self._rect = self._root.create_rectangle(self._x1, self._y1, self._x2, self._y2, 
                                                     outline=self._outline, 
                                                     width=self._width)
        else:
            self._root.itemconfig(self._rect, outline=self._outline, width=self._width)
    
    def _update_inner_params(self, x1, y1, x2, y2):
        self._x1, self._y1, self._x2, self._y2 = justify_xy(x1, y1, x2, y2)
        self._update_inner_params_fast()
        # self._w = self._x2 - self._x1
        # self._h = self._y2 - self._y1
        # self._points.clear()
        # self._points += [
        #     (self._x1, self._y1), (self._x2, self._y1), (self._x2, self._y2), (self._x1, self._y2)
        # ]
    
    def _update_inner_params_fast(self):
        self._w = self._x2 - self._x1
        self._h = self._y2 - self._y1
        self._points.clear()
        self._points += [
            (self._x1, self._y1), (self._x2, self._y1), (self._x2, self._y2), (self._x1, self._y2)
        ]

    def make_handle(self, r, **kwargs):
        for x, y in self._points:
            # print(x, y)
            self._handle.append(self._create_handle_point(x, y, r, kwargs))
        for i, _handle in enumerate(self._handle):
            self._root.tag_bind(_handle, sequence="<Button-1>", func=partial(self._on_handle_click, which=i))
            self._root.tag_bind(_handle, sequence="<B1-Motion>", func=partial(self._on_handle_move))
            self._root.tag_bind(_handle, sequence="<ButtonRelease-1>", func=partial(self._on_handle_release))
        return self._handle
    
    # def redraw_color(self, fill, alpha, outline, width):
    #     self.fill_color()
    #     self.draw_rect()
    
    def clear_handle(self):
        for handle in self._handle:
            self._root.delete(handle)
        self._handle.clear()
    
    def handle_color(self, fill, outline):
        for handle in self._handle:
            self._root.itemconfig(handle, fill=fill, outline=outline)

    def clear_fill(self):
        if self._image_tk is not None:
            self._root.delete(self._image_tk)
            del self._image
            self._image = None
            self._image_tk = None

    def fill_color(self, fill=None, alpha=None):
        self.clear_fill()
        
        if alpha:
            self._alpha = int(alpha * 255)
        if fill:
            self._fill = self._root.winfo_rgb(fill) + (self._alpha,)

        if self._fill:
            self._image = ImageTk.PhotoImage(image=Image.new('RGBA', (self._w, self._h), self._fill))

            if self._anonymous:
                self._image_tk = self._root.create_image(self._x1, self._y1, image=self._image, anchor='nw')
            else:
                self._image_tk = self._root.create_image(self._x1, self._y1, image=self._image, anchor='nw', tag=self._name)
    
    # @classmethod
    # def FindByID(cls, rect_id):
    #     return cls._map.get(rect_id, None)

    def set_outline(self, outline_color, width=1, **kwargs):
        kwargs['fill'] = ''
        self._root.itemconfig(self._rect, outline=outline_color, width=width, **kwargs)

    def _coords_handles(self, r):
        for _handle, (x, y) in zip(self._handle, self._points):
            self._root.coords(_handle, x-r, y-r, x+r, y+r)
            self._root.tag_raise(_handle, self._image_tk)
            self._root.tag_raise(_handle, self._rect)

    def coords(self, x1, y1, x2, y2):
        self._update_inner_params(x1, y1, x2, y2)
        self._root.coords(self._rect, self._x1, self._y1, self._x2, self._y2)
        self.fill_color()
        self._coords_handles(self._handle_r)
        
    def _create_handle_point(self, x, y, r, kwargs):
        # return self._root.create_oval(x-r, y-r, x+r, y+r, **kwargs)
        return self._root.create_oval(x-r, y-r, x+r, y+r, **kwargs)

    def remove(self):
        # print('delete')
        self.clear_fill()
        self.clear_handle()
        self._root.delete(self._rect)
        
        self._image = None
        self._image_tk = None
        self._rect = None
        self._alpha = None
        self._fill_name = None
        self._outline = None
        # if self._fill_name == '':
        #     self._fill = None
        # else:
        self._fill = None
        self._width = None

        self._points = None

        self._handle = None

        self._change_handle = None
        
        self._anchor_point = None
        super().remove()



class ImageDrawPanel(tkk.Canvas, metaclass=LoggerMeta):
    _L: Logger = None

    DRAW_RECT_COLOR = {
        "fill": "red",
        "outline": "red",
        "width": 1,
        'alpha': 0.5
    }

    SELECT_RECT_COLOR = {
        "fill": "red",
        "outline": "white",
        "width": 2,
        "alpha":0.3
    }

    def __init__(self, master, cnf={}, **kw):
        if kw.get('bg') is None:
            kw['bg'] = 'Grey'
        super().__init__(master, cnf, **kw)
        self.rects = {}
        self._target_list = Target.targets_dict

        self._create_new_mode = False
        
        self.bind("<Button-1>", self._mouse_down)
        self.bind("<B1-Motion>", self._mouse_move)
        self.bind("<ButtonRelease-1>", self._mouse_release)
        # self.bind("<Shift-Button-1>", EMPTY_EVENT_HOOK)
        self.bind("<KeyRelease-BackSpace>", self.delete_keypoints)
        # self.bind("<Button-3>", self._change_value)
        self.bind("<KeyRelease-Delete>", self.remove_target)

        self._start_x = -1
        self._start_y = -1
        self._rect = None

        self._selected_rects = set()

        self._is_open = False

        # DATA
        # self.data_matirx = {}
        # self.data_refresh = {}

    def close(self):
        if self._is_open:
            self._is_open = False
            for name, rect in self.rects.items():
                rect.remove()
                del rect
                
            self.rects.clear()
            # SharedNamespace.frameseq_panel.close_and_save()
            self._create_new_mode = False
            

    def open(self):
        if not self._is_open:
            self._is_open = True

            # SharedNamespace.frameseq_panel.initialize()
            # self._add_new_attrs(None, objects=0)
            
            self.refresh()

    # def restore_all_attrs_data(self):
    #     for target in Target.targets_dict:
    #         attr_file = os.path.join(Target.GetDefaultPath, target.name)
    
    def target_shape_change(self, name, new_points):
        t_obj:Target = self._target_list[name]
        t_obj.set_key_point(frame_index=self.CurrFrame, poly_points=new_points/self.Scale)
        self.refresh()

    def frame_change(self):
        self.refresh()

    def remove_target(self, event):
        for rect in ShapeBase.SELECTED_OBJECTS:
            target: Target = self._target_list[rect.Name]
            ans = messagebox.askyesno(title="警告！", message="即将删除目标%s(%s)与相应已标注文件，是否继续？" % (target.name, target.class_name))
            if ans:
                Target.RemoveTarget(target)
                SingleAttr.DeleteTarget(target.name)
            else:
                self._L.info('删除操作已取消！')
        self.refresh()
        SharedNamespace.frameseq_panel.refresh(True)

    def delete_keypoints(self, event):
        # print(event, len(ShapeBase.SELECTED_OBJECTS))
        for rect in ShapeBase.SELECTED_OBJECTS:
            target: Target = self._target_list[rect.Name]
            if target.remove_key_point_at(self.CurrFrame):
                self._L.info('删除目标%s（%s）位于第%s帧的关键帧' % (rect.Name, target.class_name, self.CurrFrame))
                self.refresh()

    # def _try_read_from_file(self, filename):


    # def _add_new_attrs0(self, name):
    #     for attr_type in SharedNamespace.attrs:
    #         attr: AttrType = SharedNamespace.attrs[attr_type]
    #         if attr._objects == 0:
    #             attr_name = attr_type if name is None else "%s-%s" % (name, attr_type)
    #             data = self.data_matirx.get(attr_name, None)
                
    #             if data is None:
    #                 data = SharedNamespace.frameseq_panel.add_item(attr_name, attr_type)
    #                 self.data_matirx[attr_name] = data
    #             else:
    #                 data = SharedNamespace.frameseq_panel.add_item(attr_name, attr_type, data)

    def refresh(self):
        if self._is_open:
            # print(self._target_list)
            for name, t_obj in self._target_list.items():
                # print("targets ", name)
                # print(name, self.Scale, self.CurrFrame)
                rect: TRectangle = self.rects.get(name, None)
                # print(name)
                
                # t_obj = Target()
                exist, rect_curr = t_obj.get_rect_poly(self.CurrFrame)
                state = t_obj.get_frame_flag(self.CurrFrame)    # -1 未知 1 关键帧 0 非关键帧 2 自动帧
                x1, y1 = rect_curr[0] * self.Scale
                x2, y2 = rect_curr[2] * self.Scale
                # print(x1,y1,x2,y2)

                if rect is None:
                    # create new
                    rect = TRectangle(name, int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))
                    rect.bind_shape_change_hook(self.target_shape_change)
                    self.rects[name] = rect

                    # self._add_new_attrs(name, objects=1)
                            
                            

                else:
                    rect.coords(int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))
                
                if exist:
                    rect.fill_color('red', 0.5)
                else:
                    rect.fill_color('grey', 0.5)
                
                if state == 1:
                    rect.handle_color(fill='yellow', outline='orange')
                elif state == 0:
                    rect.handle_color(fill='blue', outline='white')
                else:
                    rect.handle_color(fill='grey', outline='white')
            
            remove_item = set(self.rects) - set(self._target_list)
            for name in remove_item:
                r_obj = self.rects.pop(name)
                # self.delete(r_obj)
                # del r_obj
                r_obj.remove()
                r_obj = None
                
                # print("del: ", name)
            # print(self.find_all())

    @property
    def CurrFrame(self): return SharedNamespace.FrameCurrIndex()

    @property
    def Scale(self): return SharedNamespace.Scale()

    @property
    def CreateNewMode(self): return self._create_new_mode

    @CreateNewMode.setter
    def CreateNewMode(self, value: bool): 
        ShapeBase.DRAW_LOCK = value
        self._create_new_mode = value

    def _mouse_down(self, event):
        self.focus_set()
        if self._create_new_mode:
            ShapeBase.ClearSelection()
            self._start_x, self._start_y = event.x, event.y
            self._rect = TRectangle('', self._start_x, self._start_y, self._start_x+1, self._start_y+1, **self.DRAW_RECT_COLOR)
        else:
            if len(self.find_overlapping(event.x-1, event.y-1, event.x+1, event.y+1)) < 2:
                ShapeBase.ClearSelection()

    def _mouse_move(self, event):
        if self._rect is not None:
            self._rect.coords(self._start_x, self._start_y, event.x, event.y)

    def _mouse_release(self, event):
        if self._rect is not None:
            if self._create_new_mode:
                
                self._create_new_target(self._start_x, self._start_y, event.x, event.y)

                self._rect.remove()
                self._rect = None
                
                self.CreateNewMode = False
    

    def _create_new_target(self, left_x, left_y, right_x, right_y):

        class_name = SharedNamespace.classnames.make_selection()

        points = np.array([[left_x, left_y], [right_x, left_y],
                        [right_x, right_y], [left_x, right_y]]) / self.Scale
        # print(points)
        t = Target.New(points=points,
                       start_index=self.CurrFrame,
                       class_name=class_name)
        
        SingleAttr.CheckAndCreate(t.name)
        
        self.refresh()
        SharedNamespace.frameseq_panel.refresh(True)
        # # self._target_list[target.name] = target
        # rect = TRectangle(target.name, left_x, left_y, right_x, right_y, **self.DRAW_RECT_COLOR)
        # rect.bind_shape_change_hook(self.target_shape_change)
        # self.rects[target.name] = rect

class TargetInfoPanel(tkk.Frame):
    def __init__(self, master, cnf={}, **kw):
        if kw.get('bg') is None:
            kw['bg'] = 'Grey'
        super().__init__(master, cnf, **kw)


class WorkspacePanel(tkk.Frame):

    def __init__(self, master, cnf={}, **kw):
        if kw.get('bg') is None:
            kw['bg'] = 'Grey'
        super().__init__(master, cnf, **kw)

        # tree = ttk.Treeview(self, height=height, show="headings", columns=("□","视频"))
        # tree.pack()

        self._var_path = tkk.StringVar()
        self._vidoe_path_var = tkk.StringVar()

        self.workspace_title = tkk.Label(self, text='项目空间：')
        
        self.workspace_dir = tkk.Entry(self, textvariable=self._var_path, state='readonly')
        self._var_path.set('')
        
        self.list_frame = tkk.Frame(self)
        self.list_video = tkk.Listbox(self.list_frame, width=30)
        self.list_scroll = ScrollPanel(self.list_frame, self.list_video)

        self.add_new_btn = tkk.Button(self, text='添加', width=10, command=self._add_new_videos)
        self.delete_btn = tkk.Button(self, text='移除', width=10, command=self._delete_videos)
        self.sign = tkk.Button(self, text='标记完成', width=10, command=self._sign_flag)
        self.seq_line = ttk.Separator(self)
        self.video_info_title = tkk.Label(self, text='视频信息')
        self.video_path = tkk.Label(self, text='文件路径：')
        self.video_path_entry = tkk.Entry(self, textvariable=self._vidoe_path_var, state='readonly')
        self.video_cc = tkk.Label(self, text='编码格式：')
        self.video_cc_entry = tkk.Label(self, anchor="w")
        self.video_fps = tkk.Label(self, text='帧频FPS：')
        self.video_fps_entry = tkk.Label(self, anchor="w")
        self.video_size = tkk.Label(self, text='视频尺寸：')
        self.video_size_entry = tkk.Label(self, anchor="w")
        self.video_length = tkk.Label(self, text='视频长度：')
        self.video_legnth_entry = tkk.Label(self, anchor="w")
        self.seq_line2 = ttk.Separator(self)
        self.create_new_anno_btn = tkk.Button(self, text='开始标注该视频', command=self.start_anno)

        self.workspace_title.grid(row=0, column=0, sticky=tkk.EW)
        self.workspace_dir.grid(row=0, column=1, columnspan=2, sticky=tkk.NSEW)
        self.list_frame.grid(row=1, columnspan=3, sticky=tkk.NSEW)
        self.add_new_btn.grid(row=2, column=0)
        self.delete_btn.grid(row=2,column=1)
        self.sign.grid(row=2, column=2)
        self.seq_line.grid(row=3, column=0 ,columnspan=3, sticky=tkk.NSEW)
        self.video_info_title.grid(row=4, column=0, columnspan=3, sticky=tkk.NSEW)

        self.video_path.grid(row=5, column=0, sticky=tkk.EW)
        self.video_path_entry.grid(row=5, column=1, columnspan=2, sticky=tkk.NSEW)
        self.video_cc.grid(row=6, column=0, sticky=tkk.EW)
        self.video_cc_entry.grid(row=6, column=1, columnspan=2, sticky=tkk.NSEW)
        self.video_fps.grid(row=7, column=0, sticky=tkk.EW)
        self.video_fps_entry.grid(row=7, column=1, columnspan=2, sticky=tkk.NSEW)
        self.video_size.grid(row=8, column=0, sticky=tkk.EW)
        self.video_size_entry.grid(row=8, column=1, columnspan=2, sticky=tkk.NSEW)
        self.video_length.grid(row=9,column=0, sticky=tkk.EW)
        self.video_legnth_entry.grid(row=9, column=1, columnspan=2, sticky=tkk.NSEW)
        self.seq_line2.grid(row=10, column=0, columnspan=3, sticky=tkk.NSEW)
        self.create_new_anno_btn.grid(row=11, column=0, columnspan=3, sticky=tkk.NSEW)

        self.list_scroll.construct_all()

        # self.list_video.event_add("<abc>", "<Button-1>")
        # self.list_video.bind("<Button-1>", self._on_click_item)
        self.list_video.bind("<ButtonRelease-1>", self._on_click_item)
        self.list_video.bind("<ButtonRelease-3>", self._on_right_click)

        self.controler = None
        self.top_bar = None
        # self.locker = Lock()
        self.__click_time = 0
        self.__last_name = ""

        self._is_started = False

        self.clear()

    # def _on_moving(self):
    #     self.list_video.event_add()
    def _sign_flag(self):
        indexes = self.list_video.curselection()
        name = self._inner_list[indexes[0]]
        sd:VideoAnnotation = SharedNamespace.workspace.video_files_state[name]
        if sd.state == sd.STATE_FINISHED:
            sd.state = sd.STATE_HAS_STARTED
        elif sd.state == sd.STATE_HAS_STARTED:
            sd.state = sd.STATE_FINISHED
        self.refresh_list()

    def _delete_videos(self):
        indexes = self.list_video.curselection()
        names = []
        for i in indexes:
            names.append(self._inner_list[i])

        SharedNamespace.workspace.remove_videos(names)
        self.refresh_list()

    def start_anno(self):
        if self._is_started:
            self.create_new_anno_btn['text'] = "开始标注该视频"
            self._is_started = False
            self.list_video['state'] = tkk.NORMAL
            SharedNamespace.video_frame_obj.stop_read()
            SharedNamespace.anno_obj.end_annotation()
            SharedNamespace.anno_obj = None
            
            # self.controler.set_data([])
            self.delete_btn['state'] = tkk.NORMAL
            self.add_new_btn['state'] = tkk.NORMAL
            self.__last_name = ""
            self._on_click_item(None)
            self.top_bar.set_Videos()
            
        else:
            self.controler.start_use()
            self.create_new_anno_btn['text'] = "结束标注并保存"
            self.list_video['state'] = tkk.DISABLED
            self._is_started = True
            self.delete_btn['state'] = tkk.DISABLED
            self.add_new_btn['state'] = tkk.DISABLED
            
            SharedNamespace.video_frame_obj.read(asyn=True)
            SharedNamespace.anno_obj = SharedNamespace.workspace.video_files_state[self.__last_name]
            # SharedNamespace.anno_obj.read_all_annotations()
            SharedNamespace.anno_obj.start_annotation()

            self.top_bar.set_Annos()
            
            
            
    def _select_nothing(self):
        self.add_new_btn['text'] = '添加'
        self.delete_btn['state'] = tkk.NORMAL
        self.sign['state'] = tkk.DISABLED
        self.sign['text'] = "未选视频"
        self.create_new_anno_btn['state'] = tkk.DISABLED
        self.create_new_anno_btn['text'] = "请选择视频"
        self.__last_name = ""

    def _select_video_new(self):
        self.add_new_btn['text'] = '添加'
        self.delete_btn['state'] = tkk.NORMAL
        self.sign['state'] = tkk.DISABLED
        self.sign['text'] = "无法标记"
        self.create_new_anno_btn['state'] = tkk.NORMAL
        self.create_new_anno_btn['text'] = "开始标注该视频"

    def _select_video_not_exist(self):
        self.add_new_btn['text'] = '找回'
        self.delete_btn['state'] = tkk.NORMAL
        self.sign['state'] = tkk.DISABLED
        self.create_new_anno_btn['state'] = tkk.DISABLED
        self.create_new_anno_btn['text'] = "无法标注不存在的视频"
        self.sign['text'] = "无法标记"

    def _select_video_isstarted(self):
        self.add_new_btn['text'] = '添加'
        self.delete_btn['state'] = tkk.NORMAL
        self.sign['state'] = tkk.NORMAL
        self.create_new_anno_btn['state'] = tkk.NORMAL
        self.create_new_anno_btn['text'] = "继续标注该视频"
        self.sign['text'] = "标记完成"

    def _select_video_finished(self):
        self.add_new_btn['text'] = '添加'
        self.delete_btn['state'] = tkk.NORMAL
        self.sign['state'] = tkk.NORMAL
        self.create_new_anno_btn['state'] = tkk.DISABLED
        self.create_new_anno_btn['text'] = "该视频已结束标注"
        self.sign['text'] = "取消标记"

    def _on_right_click(self, event):
        self.refresh_list()
        
    def _on_click_item(self, event):
        click = time.time() - self.__click_time
        self.__click_time = time.time()
        if click < 0.2:
            return
        indexes = self.list_video.curselection()

        if len(indexes) > 0:
            name = self._inner_list[indexes[0]]
            if name == self.__last_name:
                return
            self.__last_name = name
            state, video_path = SharedNamespace.workspace.get_videofile(name)
            v_pre = SharedNamespace.video_frame_obj

            if state == VideoAnnotation.STATE_LOST:
                # lost item
                self.controler.set_data([])
                if v_pre is not None:
                    SharedNamespace.video_frame_obj = None
                    del v_pre

                self.set_video_info()
                self._select_video_not_exist()
                return 

            if v_pre is None:
                v = VideoSequence(video_path, progress_bar=self.controler.progress_bar)
                self.set_video_info(v.video_info)
                SharedNamespace.video_frame_obj = v
                # v.read(asyn=True)
                self.controler.set_data(v, pre_show=True)
            else:
                # with self.locker:
                # v_pre.stop_read()
                v = VideoSequence(video_path, progress_bar=self.controler.progress_bar)
                self.set_video_info(v.video_info)
                SharedNamespace.video_frame_obj = v
                # v.read(asyn=True)
                self.controler.set_data(v, pre_show=True)
                del v_pre

            if state == VideoAnnotation.STATE_NOT_START:
                self._select_video_new()
            elif state == VideoAnnotation.STATE_HAS_STARTED:
                self._select_video_isstarted()
            elif state == VideoAnnotation.STATE_FINISHED:
                self._select_video_finished()

    def _add_new_videos(self):
        files = filedialog.askopenfilenames(title='添加新的视频（可多选）')
        if len(files) > 0:
            filedir = os.path.dirname(files[0])
            answer = False
            if filedir != SharedNamespace.workspace.ProjectPath:
                answer = messagebox.askyesno(title="询问", message="检测到添加文件的路径与项目路径不在同一个文件夹下，是否要拷贝这些视频到项目目录？")
                
            SharedNamespace.workspace.add_videos(files, copy_files=answer)
            self.refresh_list()
    
    _list_colors = {
        VideoAnnotation.STATE_FINISHED: {"bg": "green"},
        VideoAnnotation.STATE_HAS_STARTED: {"bg": "white"},
        VideoAnnotation.STATE_LOST: {"bg": "red"},
        VideoAnnotation.STATE_NOT_START: {"bg": "LightYellow"}
    }

    _inner_list = []

    _state_names = {
        VideoAnnotation.STATE_FINISHED: "√完成",
        VideoAnnotation.STATE_HAS_STARTED: "进行中",
        VideoAnnotation.STATE_LOST: "X丢失",
        VideoAnnotation.STATE_NOT_START: "*新"
    }

    def refresh_list(self):
        self.list_video.delete(0, "end")
        if SharedNamespace.workspace is None:
            return
        items = SharedNamespace.workspace.get_video_names(None)
        self._inner_list.clear()
        for item, state in items:
            self.list_video.insert("end", "[%s] %s" % (self._state_names[state], item))
            self._inner_list.append(item)
            self.list_video.itemconfig("end", **self._list_colors[state])
        self._select_nothing()
        

    def clear(self):
        self._var_path.set("未打开项目")

        self._vidoe_path_var.set("")
        self.video_cc_entry['text'] = ""
        self.video_fps_entry['text'] = ""
        self.video_legnth_entry['text'] = ""
        self.video_size_entry['text'] = ""
        self.add_new_btn['state'] = tkk.DISABLED
        self.delete_btn['state'] = tkk.DISABLED
        self.sign['state'] = tkk.DISABLED
        self.create_new_anno_btn['state'] = tkk.DISABLED
        self._select_nothing()

    def set_workspace_path(self, path):
        if path is None:
            self.clear()
        else:
            self._var_path.set(path)
            self.add_new_btn['state'] = tkk.NORMAL
            # self.delete_btn['state'] = tkk.NORMAL

    def set_video_info(self, new_dict=None):
        """
        
        self.video_info = {'source_path': self._video_file_path,
                            "video_name": self._video_name,
                            'fourcc': struct.pack('i', int(cap.get(cv2.CAP_PROP_FOURCC))).decode('ascii'),
                            'fps': int(cap.get(cv2.CAP_PROP_FPS)),
                            'frame_count': self._frame_count,
                            'width': self._video_width,
                            'height': self._video_height,
                            'is_rgb': not bool(cap.get(cv2.CAP_PROP_CONVERT_RGB))
                            }
        """
        if new_dict is None:
            self._vidoe_path_var.set("Unknown")
            self.video_cc_entry['text'] = "N/A"
            self.video_fps_entry['text'] = "N/A"
            self.video_legnth_entry['text'] = "N/A"
            self.video_size_entry['text'] = "N/A"
            return
        # new_dict = VideoSequence()
        # new_dict.video_info
        self._vidoe_path_var.set(new_dict['source_path'])
        self.video_cc_entry['text'] = f"{new_dict['fourcc']} (彩色)" if new_dict['is_rgb'] else f"{new_dict['fourcc']} (黑白)"
        self.video_fps_entry['text'] = new_dict['fps']
        self.video_legnth_entry['text'] = new_dict['frame_count']
        self.video_size_entry['text'] = f"{new_dict['width']}像素宽 x {new_dict['height']}像素高"