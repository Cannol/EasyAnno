from logging import Logger
import tkinter as tkk
from tkinter import messagebox
from bases.workspace import SharedNamespace, AttrType, FreeAttr as WFreeAttr
from bases.attrs import SingleAttr, FreeAttr, MultiObjAttr

from functools import partial

from common.logger import LoggerMeta


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

class SeqenceAttributePanel(tkk.Frame, metaclass=LoggerMeta):
    
    _L: Logger = None

    controler = None

    EMPTY_ELEMS = {
        "fill": "Grey",
        "outline": "black",
        "width": 1
    }

    SELECTED_ELEMS = {
        "fill": "Cyan",
        "outline": "black",
        "width": 1
    }

    VALUED_ELEMS = {
        "fill": "YellowGreen",
        "outline": "black",
        "width": 1
    }

    def __init__(self, master, cnf={}, **kw):
        if kw.get('bg') is None:
            kw['bg'] = 'Grey'
        super().__init__(master, cnf, **kw)

        # ==== inner params
        self._left_width = 200
        self._scale_ruler_height = 20
        self._ruler_height_tick = 10
        self._ruler_height_mini = 5
        self._text_font_ruler = ('Arial', 7)
        self._text_font_left = ('Arial', 10)
        self._text_font_right = ('Arial', 10)

        self._block_height = 10
        self._block_width = 5
        self._block_width_var = tkk.IntVar()
        self._block_width_var.set(self._block_width)
        self._length = -1
        self._start_x_right = 0

        self._zero_attrs = FreeAttr.attrs     # 显示在最前面
        self._one_attrs = SingleAttr.attrs      # 与目标绑定，显示在中间位置
        self._many_attrs = MultiObjAttr.attrs     # 与多个目标绑定，显示在最后面

        self._MIN_BLOCK_WIDTH = 3
        self._MAX_BLOCK_WIDTH = 20

        # ==== layout conponents
        self.scale_bar = tkk.Scale(self, orient='horizontal',showvalue=False,
                                   from_=self._MIN_BLOCK_WIDTH, to=self._MAX_BLOCK_WIDTH,
                                   resolution=1, variable=self._block_width_var,
                                   command=self._set_block_width)
        self.ruler_bar = tkk.Canvas(self, height=self._scale_ruler_height, bg=kw['bg'], highlightthickness=0)
        
        self.left_name_panel = tkk.Canvas(self, width=self._left_width, bg=kw['bg'], highlightthickness=0)
        self.seq_panel = tkk.Canvas(self, bg=kw['bg'], highlightthickness=0)

        def combine_leftpanel(*args):
            self.seq_panel.yview(*args)
            self.left_name_panel.yview(*args)

        self.right_scroll = tkk.Scrollbar(self, orient='vertical', command=combine_leftpanel)
        self.seq_panel.configure(yscrollcommand=self.right_scroll.set)

        def combine_ruler(*args):
            self.seq_panel.xview(*args)
            self.ruler_bar.xview(*args)

        # self.left_name_panel.configure(yscrollcommand=self.right_scroll.set)
        self.bottom_left_scroll = tkk.Scrollbar(self, orient='horizontal', command=self.left_name_panel.xview)
        self.left_name_panel.configure(xscrollcommand=self.bottom_left_scroll.set)
        self.bottom_right_scroll = tkk.Scrollbar(self, orient='horizontal', command=combine_ruler)
        self.seq_panel.configure(xscrollcommand=self.bottom_right_scroll.set)
        # self.ruler_bar.configure(xscrollcommand=self.bottom_right_scroll.set)

        self.rows = -1
        self.height_total = -1
        self.width_total = -1
        # # --- menus
        self._menu_dict = {}
        self._pop_menu = {}
        self._row_data = {}

        # interact params
        self._selected_row = -1
        self._button_down = False
        self._n_start = -1
        self._n_end = -1
        self._select_rect_obj = None
        self._right_click_mode = -1

        # current pointer
        self._current_frame = 0
        self._pointer = None

        # events
        self.seq_panel.bind("<Button-1>", self._mouse_down)
        self.seq_panel.bind("<B1-Motion>", self._mouse_move)
        self.seq_panel.bind("<ButtonRelease-1>", self._mouse_release)
        self.seq_panel.bind("<Button-3>", self._change_value)

        self.left_name_panel.bind("<Button-3>", self._namepanel_mouse_down)

        # left panel operations
        self._left_panel_popmenu = PopSelectMenu(self.left_name_panel, 
                                                 selections={"删除": self._left_panel_rclick})
        self._selected_row_left = -1

        # controller
        self._video_ctrl = None
    
    def bind_controller(self, ctrl):
        self._video_ctrl = ctrl

    def _namepanel_mouse_down(self, event):
        if self.rows > 0 and event.y < self.height_total:

            self._selected_row_left = int(event.y / self._block_height + self._get_offy_n())
            self._left_panel_popmenu.post(event.x_root, event.y_root)
    
    def _left_panel_rclick(self):
        data = self._row_data[self._selected_row_left][1]
        if isinstance(data, MultiObjAttr):
            if messagebox.askyesno(f'即将删除组属性{data.Name}，相应的文件也会一同被删除，是否继续？'):
                data.remove()
                self.refresh(force=True)
        elif isinstance(data, FreeAttr):
            self._L.error('该属性为必要属性，无法删除！')
        else:
            self._L.error('该属性与目标绑定，删除目标即可删除该属性，不支持单独删除！')
        
    def _set_block_width(self, event):
        self._block_width = self._block_width_var.get()
        # print(self._block_width)
        # x1, x2 = self.seq_panel.xview()
        self.__destory_ruler()
        self.__draw_ruler()
        self.quick_refresh_seq_panel()
        # print(self._row_data)
        # self.seq_panel.xview_moveto(x1)

    def _change_value(self, event):
        if self._selected_row >= 0:
            self._mouse_end_ops()
            return
        
        if self.rows > 0 and event.y < self.height_total:

            self._selected_row = int(event.y / self._block_height + self._get_offy_n())

            n = int(event.x / self._block_width + self._get_offx_n())

            value = self._row_data[self._selected_row][1][n]
            if value == -1:
                self._mouse_end_ops()
                return
            
            _data_array = self._row_data[self._selected_row][1]

            start = n
            while start >= 0 and _data_array[start] == value:
                start -= 1
            start += 1
            end = n
            while end < self._length and _data_array[end] == value:
                end += 1
            end -= 1
            
            self._n_start = start
            self._n_end = end
            
            x0 = start * self._block_width
            y0 = self._selected_row *self._block_height
            x1 = (end + 1) * self._block_width
            y2 = y0 + self._block_height

            self._select_rect_obj = self.seq_panel.create_rectangle(
                x0, y0,
                x1,
                y2,
                **self.SELECTED_ELEMS
            )
            self._right_click_mode = int(value)
            self._pop_menu[self._selected_row].post(event.x_root, event.y_root)

    def _get_offx_n(self): return self.seq_panel.xview()[0] * self._length
    def _get_offy_n(self): return self.seq_panel.yview()[0] * self.rows

    def set_frame_no_recall(self, index):
        if index == self._current_frame:
            return
        self._current_frame = index
        
        start, end = self.seq_panel.xview()
        
        # start = start * self.width_total
        offx_rate = index * self._block_width / self.width_total

        # print(start, offx_rate, end)

        if start <= offx_rate <= end:
            pass
        else:
            self.seq_panel.xview_moveto(offx_rate)
            self.ruler_bar.xview_moveto(offx_rate)
        self.__draw_pointer()

    @property
    def CurrFrame(self): return self._current_frame

    @CurrFrame.setter
    def CurrFrame(self, index):
        self._current_frame = index
        self.__draw_pointer()
        self._video_ctrl.change_frame(index+1)

    def __draw_pointer(self):
        pointer_width = 1
        x0 = x1 = (self._current_frame+0.5) * self._block_width
        y0 = 0
        y1 = self.height_total

        if self._pointer is None:
            # print('create pointer: ', x0, x1, y0, y1)
            self._pointer = self.seq_panel.create_line(
                x0, y0, x1, y1,
                fill='red', width=pointer_width
            )
        else:
            # print('move pointer: ', x0, x1, y0, y1)
            self.seq_panel.coords(self._pointer, x0, y0, x1, y1)
            self.seq_panel.tag_raise(self._pointer)
            # print(self._pointer)
            # print(self.seq_panel.find_all())

    def _mouse_down(self, event):

        if self._selected_row >= 0:
            self._mouse_end_ops()
            return
        
        if self.rows > 0 and event.y < self.height_total:

            self._selected_row = int(event.y / self._block_height + self._get_offy_n())
            self._n_start = int(event.x / self._block_width + self._get_offx_n())
            print(self._n_start, event.x, self._block_width, self._get_offx_n())
            x0 = self._n_start*self._block_width
            y0 = self._selected_row*self._block_height
            
            self._select_rect_obj = self.seq_panel.create_rectangle(
                x0, y0,
                x0 + self._block_width,
                y0 + self._block_height,
                **self.SELECTED_ELEMS
            )
            self._button_down = True
            self._n_end = self._n_start

            self.CurrFrame = self._n_start

    def _mouse_move(self, event):
        if self._button_down:
            # print(self.seq_panel.xview())
            if event.x >= self.seq_panel.winfo_width():
                self.seq_panel.xview_scroll(1, 'units')
            elif event.x <= 0:
                self.seq_panel.xview_scroll(-1, 'units')

            n = int(event.x / self._block_width + self._get_offx_n())
            n = min(max(0, n), self._length-1)

            if self._n_end == n:
                return

            if n > self._n_start:
                x0 = self._n_start*self._block_width
                x1 = (n+1)*self._block_width
            
            elif n < self._n_start:
                x0 = n*self._block_width
                x1 = (self._n_start+1)*self._block_width
            
            else:
                x0 = self._n_start*self._block_width
                x1 = x0 + self._block_width

            y0 = self._selected_row*self._block_height
            y1 = y0 + self._block_height

            self.seq_panel.coords(self._select_rect_obj,
                                  x0,y0,x1,y1)
            self._n_end = n
            self.CurrFrame = n

    def _mouse_release(self, event):
        if self._button_down:
            self._button_down = False
            # print(self._n_start, self._n_end)
            self._pop_menu[self._selected_row].post(event.x_root, event.y_root)

    def _mouse_end_ops(self):
        self._n_start = -1
        self._n_end = -1
        self.seq_panel.delete(self._select_rect_obj)
        self._selected_row = -1
        self._right_click_mode = -1
        self.__draw_pointer()

    def __draw_ruler(self):
        n = 5 if self._block_width >= 5 else 10
        pos = self._start_x_right
        for i in range(self._length+1):
            if i % n == 0:
                height = self._ruler_height_tick
                texts = self.ruler_bar.create_text(pos, height+6, 
                                                   text="%d"%i, 
                                                   tags='ticktext',
                                                   font=self._text_font_ruler)
            else:
                height = self._ruler_height_mini
            
            if i % 5 == 0:
                height = self._ruler_height_tick
            lines = self.ruler_bar.create_line(pos, 0, pos, height,
                                                tags = 'ruler',
                                                fill= 'black'
                                            )
            
            pos += self._block_width

    def __destory_ruler(self):
        self.ruler_bar.delete('all')

    def __draw_one_bar(self, row, name, data, color='white'):
        y1_locate = row * self._block_height
        y2_locate = y1_locate + self._block_height

        tag = name

        if self._row_data.get(row, None) is not None:
            self.seq_panel.delete(tag)
            # self._L.info('删除原有条块')
        
        else:
            self.left_name_panel.create_rectangle(0, y1_locate, self._left_width, y2_locate,
                                                fill=color)
            
            self.left_name_panel.create_text(self._left_width-2, y1_locate+self._block_height/2, 
                                            text=name,
                                            tags=tag, 
                                            font=self._text_font_left,
                                            anchor='e')
        start_x = self._start_x_right
        value_last = -2
        index_start = -1
        index_end = -1

        def _draw():
            if value_last >= 0:
                self.seq_panel.create_rectangle(start_x + index_start*self._block_width, 
                                                    y1_locate, 
                                                    start_x + (index_end+1)*self._block_width, 
                                                    y2_locate, 
                                                    tags=tag, **self.VALUED_ELEMS)
                        
                self.seq_panel.create_text(start_x + index_start*self._block_width + 2,
                                    y1_locate+self._block_height/2,
                                    text=SharedNamespace.attrs[data.type_name][value_last],
                                    anchor='w', font=self._text_font_right,tag=tag)

        
        for i in range(self._length):

            value = int(data[i])
            
            if value < 0:
                _draw()
                    
                self.seq_panel.create_rectangle(start_x + i*self._block_width, 
                                                y1_locate, 
                                                start_x + (i+1)*self._block_width, 
                                                y2_locate, 
                                                tags=tag, **self.EMPTY_ELEMS)
                value_last = value

            elif value == value_last:
                index_end = i
            else:
                _draw()
                index_start = index_end = i
                value_last = value
        
            
    def initialize(self, length, block_height: int, block_width: int):
        self._length = length
        self._block_height = block_height
        self._block_width = max(min(block_width, self._MAX_BLOCK_WIDTH),self._MIN_BLOCK_WIDTH)
        self._block_width_var.set(self._block_width)
        self.__destory_ruler()
        self.__draw_ruler()
        # self.CurrFrame = 0

    def refresh_one_row(self, row):
        name, data, attr_type = self._row_data[row]

        if attr_type is None:
            self.__draw_one_bar(row, name, data)
        else:
            self.__draw_one_bar(row, '%s.%s' % (name, attr_type), data)

    def quick_refresh_seq_panel(self):
        for row in range(self.rows):
            self.refresh_one_row(row)
        self.__draw_pointer()
        self._bar_change_refresh()

    def refresh(self, force=False):
        if force:
            self._row_data.clear()
        self.clear_all()
        rows = 0
        # zeros
        for name, item in self._zero_attrs.items():
            # print(name, item)
            self.insert_new(row=rows, name=name, data=item)
            rows += 1

        # one_target
        for name, item in self._one_attrs.items():
            for attr_obj in item:
                # print(name, item, attr_obj)
                self.insert_new(row=rows, name=name, attr_type=attr_obj.type_name, data=attr_obj)
                rows += 1

        # many_targets
        for name, item in self._many_attrs.items():
            print(name, item)
            self.insert_new(row=rows, name=name, data=item)
            rows += 1
        
        self.rows = rows

        self._bar_change_refresh()

    def _bar_change_refresh(self):
        if self.rows > 0:
            x1, y1, x2, y2 = self.seq_panel.bbox('all')
            self.seq_panel.configure(scrollregion=(0, 0, x2, y2))
            x1, y1, _, y2 = self.ruler_bar.bbox('all')
            self.ruler_bar.configure(scrollregion=(0, 0, x2, y2))
            x1, y1, x2, y2 = self.left_name_panel.bbox('all')
            self.left_name_panel.configure(scrollregion=(0, 0, x2, y2))
        else:
            self.ruler_bar.configure(scrollregion=(0, 0, 0, 0))
            self.seq_panel.configure(scrollregion=(0, 0, 0, 0))
            self.left_name_panel.configure(scrollregion=(0, 0, 0, 0))

        self.height_total = self._block_height * self.rows
        self.width_total = self._block_width * self._length
        self.__draw_pointer()
    
    def clear_all(self):
        self.seq_panel.delete('all')
        self.left_name_panel.delete('all')
        self._pointer = None

    def close(self):
        self.clear_all()
        self._row_data.clear()
        
    def insert_new(self, row, name, data, attr_type=None):

        if attr_type is None:
            self.__draw_one_bar(row, name, data)
            pop_name = name.split('.')[-1]
            self._pop_menu[row] = self._menu_dict[pop_name]
        else:
            self.__draw_one_bar(row, '%s.%s' % (name, attr_type), data)
            self._pop_menu[row] = self._menu_dict[attr_type]
        
        self._row_data[row] = (name, data, attr_type)
        
    def construct(self):
        
        # layout construct
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self.scale_bar.grid(row=0, column=0, sticky=tkk.NSEW)
        self.ruler_bar.grid(row=0, column=1, sticky=tkk.NSEW)
        self.left_name_panel.grid(row=1, column=0, sticky=tkk.NSEW)
        self.seq_panel.grid(row=1, column=1, sticky=tkk.NSEW)
        self.right_scroll.grid(row=0, rowspan=2, column=2, sticky=tkk.NSEW)
        self.bottom_left_scroll.grid(row=2, column=0, sticky=tkk.NSEW)
        self.bottom_right_scroll.grid(row=2, column=1, columnspan=2, sticky=tkk.NSEW)

    @property
    def RowHeight(self): return self._block_height

    @RowHeight.setter
    def RowHeight(self, height): self._block_height = height

    @property
    def BlockWidth(self): return self._block_width

    @BlockWidth.setter
    def BlockWidth(self, width): self._block_width = width

    @property
    def LeftPanelWidth(self): return self._left_width

    @LeftPanelWidth.setter
    def LeftPanelWidth(self, width): self._left_width = width

    @property
    def RightStartY(self): return self._ruler_height + 2
        

    def set_menu(self, menu_items: dict):
        """ following the project settings
        """
        self._menu_dict.clear()
        if menu_items is not None:
            for menu_type, selections in menu_items.items():
                # print(menu_items)
                selection_with_func = {}
                for k, _ in selections.items():
                    selection_with_func[k] = partial(self._select_menu_item, k, selections)
                
                selection_with_func["--"] = None   # 表示横线
                selection_with_func["删除属性标记"] = partial(self._delete_between, selections)
                selection_with_func["取消选择"] = self._roll_back
                self._menu_dict[menu_type] = PopSelectMenu(self, selections=selection_with_func)

    def _select_menu_item(self, value, obj: AttrType):
        try:
            if isinstance(obj, WFreeAttr) and (self._right_click_mode >= 0):
                value = obj[self._right_click_mode]

            target_value = obj[value]
            # print(f'select: {value} {obj} {target_value} {self._right_click_mode}')

            if isinstance(obj, WFreeAttr) and self._right_click_mode >=0 and self._right_click_mode != target_value:
                data = self._row_data[self._selected_row][1]
                # print(self._row_data[self._selected_row][1][:100])
                # print(data == self._right_click_mode)
                data[data == self._right_click_mode] = target_value
                # print(self._row_data[self._selected_row][1][:100])
            else:
                if self._n_start < self._n_end:
                    self._row_data[self._selected_row][1][self._n_start:self._n_end+1] = target_value
                else:
                    self._row_data[self._selected_row][1][self._n_end:self._n_start+1] = target_value
            self.refresh_one_row(self._selected_row)
        except Exception as e:
            self._L.warning(e)
        finally:
            self._mouse_end_ops()
        
    def _delete_between(self, obj: AttrType):
        
        data = self._row_data[self._selected_row][1]
        
        if self._n_start < self._n_end:
            data[self._n_start:self._n_end+1] = -1
        else:
            data[self._n_end:self._n_start+1] = -1
        self.refresh_one_row(self._selected_row)

        if isinstance(obj, WFreeAttr):
            value = self._right_click_mode

            if sum(data == value) == 0:
                obj.delete_item(value)
        
        # print(f'delete: {value} {obj} {self._right_click_mode}')
                
        self._mouse_end_ops()

    def _roll_back(self):
        self._mouse_end_ops()


