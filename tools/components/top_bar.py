from logging import Logger
import tkinter as tkk
from tkinter import messagebox
from common.logger import LoggerMeta
from tkinter import filedialog

from bases.workspace import WorkSpace, SharedNamespace
from tools.components.panels import ShapeBase
from bases.attrs import MultiObjAttr, default_types

class TopBar(tkk.Frame, metaclass=LoggerMeta):
    _L: Logger = None

    def __init__(self, master, cnf={}, **kw):
        if kw.get('bg') is None:
            kw['bg'] = 'Grey'
        super().__init__(master, cnf, **kw)
        bg = kw['bg']

        # 打开文件夹，当打开的文件夹中不存在.proj文件的时候，会在该目录创建新的项目，否则直接使用该文件加载项目
        self._workspace_panel = None
        self._btn_open = tkk.Button(self, bg=bg, command=self._open, width=16, text='新建/打开项目', relief='flat')
        self._btn_refresh = tkk.Button(self, bg=bg, command=self._refresh, width=16, text='刷新项目内容', relief='flat')
        self.__is_open = False

        self._btn_generate_dataset = tkk.Button(self, bg=bg, command=self._gen_datasets,  width=20, text='生成数据集', relief='flat')
        self._btn_new_target = tkk.Button(self, bg=bg, command=self._multi_targets_annotations, width=10, text='新建目标', relief='flat')
        self._btn_relations = tkk.Button(self, bg=bg, command=self._build_relations, width=15, text='创建两个目标关系', relief='flat')

        self._construct()

        self.controler = None
        self.project_panel = None
        self.seq_panel = None

        self.set_None()
        self.__project_folder = ""

    def set_None(self):
        self._btn_open['state'] = tkk.NORMAL
        self._btn_generate_dataset['state'] = tkk.DISABLED
        self._btn_new_target['state'] = tkk.DISABLED
        self._btn_relations['state'] = tkk.DISABLED
        self._btn_refresh['state'] = tkk.DISABLED
        self._btn_open['text'] = '新建/打开项目'
    
    def set_Videos(self):
        self._btn_open['state'] = tkk.NORMAL
        self._btn_generate_dataset['state'] = tkk.NORMAL
        self._btn_new_target['state'] = tkk.DISABLED
        self._btn_relations['state'] = tkk.DISABLED
        self._btn_refresh['state'] = tkk.NORMAL
        self._workspace_panel.close()
        self._btn_open['text'] = '保存并关闭项目'
        self.seq_panel.close()
        self.seq_panel.initialize(length=100, block_height=20, block_width=10)

    def set_Annos(self):
        self._btn_open['state'] = tkk.DISABLED
        self._btn_generate_dataset['state'] = tkk.DISABLED
        self._btn_new_target['state'] = tkk.NORMAL
        self._btn_relations['state'] = tkk.NORMAL
        self._btn_refresh['state'] = tkk.DISABLED
        self._workspace_panel.open()
        # self.seq_panel['state'] = tkk.NORMAL
        self.seq_panel.set_menu(SharedNamespace.attrs)
        self.seq_panel.initialize(length=len(SharedNamespace.video_frame_obj), block_height=20, block_width=10)
        self.seq_panel.refresh()

    def bind_workspace(self, workspace_panel): self._workspace_panel = workspace_panel
    
    def _multi_targets_annotations(self):

        if self._workspace_panel:
            self._workspace_panel.CreateNewMode = True

        return 1

    def _construct(self):
        self._btn_open.pack(side=tkk.LEFT, fill=tkk.Y)
        self._btn_refresh.pack(side=tkk.LEFT, fill=tkk.Y)
        self._btn_new_target.pack(side=tkk.LEFT, fill=tkk.Y)
        self._btn_relations.pack(side=tkk.LEFT, fill=tkk.Y)
        self._btn_generate_dataset.pack(side=tkk.RIGHT, fill=tkk.Y)
        
        
    def _open(self, project_folder=None):
        if self.__is_open:
            WorkSpace.CloseAll()
            self.project_panel.refresh_list()
            self.project_panel.clear()
            self.set_None()
            self.__is_open = False
        else:
            if project_folder is None:
                project_folder = filedialog.askdirectory(title='选择一个文件夹作为项目的工作空间')
                if project_folder == '':
                    return

            ws = WorkSpace.OpenWorkspace(project_folder)
            # ws.load_configs()
            self.project_panel.set_workspace_path(ws.ProjectPath)
            self.project_panel.refresh_list()
            self.__is_open = True
            self.set_Videos()
            self.__project_folder = project_folder
            ws.load_configs()
            # self.seq_panel.configurate_menus(SharedNamespace.attrs)

    def _refresh(self):
        if self.__is_open:
            self._open()
            self._open(self.__project_folder)

    def _gen_datasets(self):
        pass

    def _build_relations(self):
        if len(ShapeBase.SELECTED_OBJECTS) == 2:
            rects = ShapeBase.SELECTED_OBJECTS
            self._L.info(f"建立目标组属性: {rects[0].Name} + {rects[1].Name}")
            obj = MultiObjAttr()

            obj.type_name = default_types[2][0]
            
            obj.object_group = [rects[0].Name, rects[1].Name]

            obj.register_self()
            
            self.seq_panel.refresh(True)
        
        elif len(ShapeBase.SELECTED_OBJECTS) > 2:
            messagebox.showerror("错误","当前版本不支持对两个以上的目标建组！")
        
        else:
            messagebox.showerror("错误","一个以上的目标才能建组")