from collections import OrderedDict as Dict
import os
import shutil
import yaml
import stat

import tkinter as tkk
from tkinter import ttk, simpledialog

from configs import ATTRIBUTE_SET_FILE

from common.json_helper import ReadFromFile, SaveToFile
from common.logger import LoggerMeta
from logging import Logger
from bases.targets import Target
from bases.attrs import AttrBase, start_auto_thread, stop_auto_thread, clean_all, FreeAttr as AFreeAttr
import hashlib

from tkinter import messagebox


DEFAULT_POSTFIXES = [".mp4", ".MP4", ".avi", ".AVI", ".f4v", '.MOV', '.mov']

class SelectionDialog(simpledialog.Dialog):
    def __init__(self, title, prompt,
                 initial_index=0,
                 values=None,
                 parent = None):

        self.prompt = prompt
        self.values = values

        self.initialvalue = initial_index

        super().__init__(parent, title)

    def body(self, master):

        self.label = ttk.Label(master, text=self.prompt, justify=tkk.LEFT)
        self.selection = ttk.Combobox(master, values=self.values)
        
        self.label.grid(row=0, padx=5, sticky=tkk.W)
        self.selection.grid(row=1, padx=5, sticky=tkk.W+tkk.E)

        if self.initialvalue is not None:
            self.selection.current(0)

        return self.selection
    
    def validate(self):
        self.result = self.selection.get()

        return 1

class AttrType(object):

    _type = "single"
    
    def __init__(self, name, attr_dict: Dict) -> None:

        self._objects = attr_dict.get('__objects__', None)
        if self._objects is not None:
            attr_dict.pop('__objects__')
        else:
            self._objects = 1

        self._name: str = name
        self._dict: Dict = attr_dict      # name --> index
        self._dict_reverse: dict = {v: k for k, v in self._dict.items()}    # index --> name

    def __getitem__(self, key):
        """
        根据输入的key的类型来决定输出attr的id还是它的name
        """
        if isinstance(key, str):
            return self._dict[key]
        elif isinstance(key, int):
            return self._dict_reverse[key]
        else:
            raise ValueError(f"The key must be in type of index(int) or attribute name(str), but we got {type(key)}")

    @staticmethod
    def ReadFromFile(attrs_dict_file):
        with open(attrs_dict_file, encoding="utf-8") as f:
            content = yaml.safe_load(f)
        attr_objs_out = {}
        for k, v in content.items():
            _type = v.get('__type__', None)
            if _type is not None:
                v.pop('__type__')
            else:
                _type = 'single'  # 没有添加该属性的默认为单选（互斥）属性模式
            cls = ATTR_DICT[_type]
            obj = cls(name=k, attr_dict=v)
            key = obj.Type
            attr = attr_objs_out.get(key, None)
            if attr is None:
                attr_objs_out[key] = []
            attr_objs_out[key].append(obj)

        return attr_objs_out
        
    def get_names(self): return list(self._dict.keys())
    
    def get_indexs(self): return list(self._dict.values())

    def items(self): return self._dict.items()

    @property
    def Type(self): return self._type

    @property
    def Name(self): return self._name
    
    def __len__(self): return len(self._dict)

    def __str__(self): return f"{self._name}, {self._type}, {self._dict}"

class BoolAttr(AttrType):
    _type = "bool"

    def __init__(self, name, attr_dict):
        super().__init__(name, attr_dict)

        self._cls_name = self._dict
        self._cls_name_reverse = self._dict_reverse
        self._dict = {"添加帧": 1}
        self._dict_reverse = {1: "添加帧"}

    def get_cls_name(self, cls_id):
        return self._cls_name_reverse[cls_id]
    
    def get_cls_id(self, cls_name):
        return self._cls_name[cls_name]

class ClassAttr(AttrType):
    _type = "class"

    def make_selection(self):
        select = SelectionDialog('创建新目标', '选择类别：', values=self.get_names())
        return select.result
        

class FreeAttr(AttrType):
    _type = "free"

    def __init__(self, name, attr_dict):
        super().__init__(name, attr_dict)

        self._dict = {}
        self._dict_reverse = {}

        self._index = 1
    
    def items(self): return {"添加属性": 0}.items()

    def bind_target_attr(self, attr):
        self._dict = attr.contents
        self._dict_reverse = {v: k for k, v in self._dict.items()}
        if len(self._dict_reverse) > 0:
            self._index = max(list(self._dict_reverse)) + 1

    def delete_item(self, value: int):
        value_str = self._dict_reverse.pop(value)
        self._dict.pop(value_str)

    def _create_new(self):
        while True:
            label_name = simpledialog.askstring("新建标签", "请输入新的标签名", initialvalue='')
            if label_name is not None and (label_name.isspace() or label_name == ''):
                ans = messagebox.askretrycancel(title="错误", message='标签内容不能为空！')
                if not ans:
                    label_name = None
                    break
            else:
                break
        if label_name is None:
            raise ValueError('Cancel Create New Label!')

        tmp_index = self._dict.get(label_name, None)
        if tmp_index is None:
            self._dict_reverse[self._index] = label_name
            self._dict[label_name] = self._index
            self._index += 1
        return label_name
    
    def _change_value(self, ori_value):
        assert ori_value in self._dict.keys()

        while True:
            label_name = simpledialog.askstring("修改标签", "请输入新的标签名", initialvalue=ori_value)
            if label_name is not None and (label_name.isspace() or label_name == ''):
                ans = messagebox.askretrycancel(title="错误", message='标签内容不能为空！')
                if not ans:
                    label_name = None
                    break
            elif label_name == ori_value:
                ans = messagebox.askretrycancel(title="提示", message='新旧标签相同，将不做任何修改，是否继续？')
                if ans:
                    label_name = None
                    break
            elif self._dict.get(label_name, None) is not None:
                ans = messagebox.askyesno("警告","新标签名称已存在，继续操作将删除现有标签与其索引，是否继续？")
                if ans:
                    break
            else:
                break
        if label_name is None:
            raise ValueError('Cancel Modify Label!')

        index = self._dict.pop(ori_value)
        index_new = self._dict.get(label_name, None)
        if index_new is None:
            self._dict_reverse[index] = label_name
            self._dict[label_name] = index
        else:
            self._dict_reverse.pop(index)
        return label_name

    def __getitem__(self, key):
        """
        根据输入的key的类型来决定输出attr的id还是它的name
        """

        if isinstance(key, str):
            if key == "添加属性":
                key = self._create_new()
            else:
                key = self._change_value(ori_value=key)
            return self._dict[key]
        elif isinstance(key, int):
            if key == 0:
                return self._create_new()

            return self._dict_reverse[key]
        else:
            raise ValueError(f"The key must be in type of index(int) or attribute name(str), but we got {type(key)}")

ATTR_DICT = {
    "single": AttrType,
    "bool": BoolAttr,
    "class": ClassAttr,
    "free": FreeAttr
}

# class AttrData(object):
    

def search_files(base_dir, file_type:tuple=None ,recurse=False):

    full_names = []
    if recurse:
        for root, dir_names, file_names in os.walk(base_dir):
            for file_name in file_names:
                if file_name.endswith(file_type):
                    full_name = os.path.join(root, file_name)
                    if os.path.isfile(full_name):
                        # files.append((root, file_name))
                        full_names.append(os.path.relpath(full_name, base_dir))
    else:
        for file_name in os.listdir(base_dir):
            if file_name.endswith(file_type):
                full_name = os.path.join(base_dir, file_name)
                if os.path.isfile(full_name):
                    # files.append((base_dir, file_name))
                    full_names.append(file_name)
    return full_names

def check_exists(base_dir, files_or_directories):
    """ 检查有哪些文件不存在，并返回
    """
    unseen = []
    for f in files_or_directories:
        if not os.path.isabs(f):
            f = os.path.join(base_dir, f)
        if not os.path.exists(f):
            unseen.append(f)
    return unseen

def json_test(json_file):
    try:
        ReadFromFile(json_file)
    except:
        return False
    return True

class VideoAnnotation(metaclass=LoggerMeta):

    _L: Logger = None

    """
    视频标注状态显示，
    """
    STATE_NOT_START = 1      # 新添加的视频默认初始状态，点击视频查看视频信息不会改变该状态，len(target_names)==0
    STATE_HAS_STARTED = 0    # 打开视频并标注第一个目标len(target_names)>0，则为该状态；当删除所有目标状态会回归未开始
    STATE_FINISHED = 2      # 用户手动点击按钮操作，标记为已完成的视频会自动被排序到队列尾部
    STATE_LOST = 3        # 丢失的视频无法打开，只能手动删除或重定向文件，如果删除，则标注数据也会随之一起删除，重定向则会保留标注结果

    _NAME_ = {
        STATE_NOT_START: "未开始",
        STATE_HAS_STARTED: "进行中",
        STATE_FINISHED: "已完成",
        STATE_LOST: "视频丢失"
    }

    anno_id: str = None
    video_file: str = None
    target_names: set = None    # 存放目标名称
    state: int = None

    def state_name(self): return 

    def check(self):
        pass

    def to_dict(self):
        return {
            "anno_id": self.anno_id,
            "video_file": self.video_file,
            "target_names": list(self.target_names),
            "state": self.state
        }
    
    @classmethod
    def from_dict(cls, anno_dict):
        self = cls()
        self.anno_id = anno_dict['anno_id']
        self.video_file = anno_dict['video_file']
        self.target_names = set(anno_dict['target_names'])
        self.state = anno_dict['state']
        return self

    @classmethod
    def CreateFromDict(cls, anno_dict):
        return cls().from_dict(anno_dict)

    def __str__(self):
        s = f"anno_id: {self.anno_id}\nvideo_file: {self.video_file}\ntarget_names: {self.target_names}"
        return s
    
    def refound_videofile(self, new_path = None):
        if self.state == self.STATE_LOST:
            if new_path is not None:
                self.video_file = new_path
                self.anno_id = _get_hash_name(new_path)
            self.state = self.STATE_HAS_STARTED if len(self.target_names) > 0 else self.STATE_NOT_START

    def add_with_check(self, anno_dir):
        # just for the first time
        target_names = set()
        other_files = []
        if os.path.exists(anno_dir):
            for anno_file in os.listdir(anno_dir):
                if anno_file.startswith(self.anno_id):
                    continue
                json_like_file = os.path.join(anno_dir, anno_file)
                if json_test(json_like_file):
                    if anno_file.endswith('.meta'):
                        target_names.add(anno_file[:-5])
                    else:
                        other_files.append(anno_file)
                else:
                    os.remove(json_like_file)
                    self._L.info('[Removed] Found an unexpected file (not valid json file): %s' % json_like_file)
            
            for other_file in other_files:
                # 删除掉与已有标注目标无关的json文件，避免与新生成的文件产生冲突
                name, postfix = other_file
                if name not in target_names:
                    full_path = os.path.join(anno_dir, other_file)
                    os.remove(full_path)
                    self._L.info('[Removed] Found an unexpected file (missing related target file): %s' % full_path)

        delete_unknown = set(self.target_names) - target_names
        add_new = target_names - set(self.target_names)
        self._L.info("Update annotation directory's file list [ANNO_ID:{%s}]! Add %d Del %d" % (self.anno_id, len(add_new), len(delete_unknown)))
    
    def finished(self): self.state = self.STATE_FINISHED

    def cancel_finished(self): self.state = self.STATE_HAS_STARTED

    def load_all_annotations(self):
        Target.GetAllTargets()
        self.target_names = list(Target.targets_dict)
        unknown_objs = AttrBase.ReadAll(self.target_names)
        if len(unknown_objs) > 0:
            objstr = '\n'.join([obj.File for obj in unknown_objs])
            ans = messagebox.askyesno(title="警告", message=f"发现以下{len(unknown_objs)}个无效属性文件，是否清除？\n{objstr}")
            if ans:
                for obj in unknown_objs:
                    obj.remove()
            else:
                self._L.warning('选择保留这些异常文件')
        
        
    def start_annotation(self):
        Target.SetLength(len(SharedNamespace.video_frame_obj))
        w, h, _ = SharedNamespace.video_frame_obj.Shape
        Target.SetGlobalOffsize(0, 0, w, h)
        Target.SetTargetSeed("Targets:")
        Target.SetDefaultSavingPath(os.path.join(SharedNamespace.workspace.AnnotationFiles, self.anno_id))
        AttrBase.SetDefaultPath(os.path.join(SharedNamespace.workspace.AnnotationFiles, self.anno_id))
        AttrBase.SetLength(len(SharedNamespace.video_frame_obj))
        AttrBase.SetAttrMap(SharedNamespace.attrs)
        
        # for k, value in SharedNamespace.attrs:
        #     if value._objects == 0:
        #         SharedNamespace.attrs[].bind_target_attr
        # SharedNamespace.frameseq_panel.

        self.load_all_annotations()
        

        for k, a in AFreeAttr.attrs.items():
            if k in SharedNamespace.attrs:
                attr_f:FreeAttr = SharedNamespace.attrs[k]
                attr_f.bind_target_attr(a)

        self.auto_save_start()
        
        
    def end_annotation(self):
        self.target_names = set(Target.targets_dict)
        self.auto_save_stop()
        Target.targets_dict.clear()
        clean_all()
        
    
    def auto_save_start(self):
        if Target.auto_th is None:
            Target.start_auto()
            start_auto_thread()
        
    
    def auto_save_stop(self):
        if Target.auto_th is not None:
            Target.stop_auto()
            Target.SaveAllTargets()
            stop_auto_thread()

    def __del__(self):
        self.auto_save_stop()

def _get_hash_name(name: str):
    hash_ = hashlib.md5()
    name = name.replace('\\', '/')  # 统一路径表示，以防在不同系统中求出的值不一致
    hash_.update(('video:%s' % name).encode('utf-8'))
    code = hash_.hexdigest()
    return code

class WorkSpace(metaclass=LoggerMeta):

    _L: Logger = None

    VIDEO_HOME = 'Videos'                          # 默认视频存放路径，每次打开标注程序会自动搜索该目录中的所有文件
    ANNO_SOURCE_HOME = 'Annotations'               # 存放标注后的源文件的数据库
    PROJECT_CONFIG_FILENAME = 'workspace.proj'     # 用来存放项目相关文件索引、状态等信息
    LABELING_SETTINGS_FILENAME = 'config.yaml'     # 用来存储标注配置文件，可随时修改，控制标注类别、标签等内容

    def __init__(self, base_path):
        
        self.video_files_state: Dict[str:VideoAnnotation] = {}
        self._step1_make_all_paths(base_path)
        self._step2_initial_all_dicts()
        self.__is_closed = False
    
    def _step1_make_all_paths(self, workspace_path):
        """
        Step1:
                当Workspace目录不存在或者目录下缺少：
                    - <LABELING_SETTINGS_FILENAME>文件
                    - <VIDEO_HOME>目录
                    - <ANNO_SOURCE_HOME>目录
                时自动创建该目录和对应空白文件
        """
        self._base_path = workspace_path
        self._video_dir = os.path.join(workspace_path, self.VIDEO_HOME)
        self._anno_dir = os.path.join(workspace_path, self.ANNO_SOURCE_HOME)
        self._config_file = os.path.join(workspace_path, self.LABELING_SETTINGS_FILENAME)
        self._proj_file = os.path.join(workspace_path, self.PROJECT_CONFIG_FILENAME)

        os.makedirs(workspace_path, exist_ok=True)
        os.makedirs(self._video_dir, exist_ok=True)
        os.makedirs(self._anno_dir,exist_ok=True)

        if not os.path.exists(self._config_file):
            shutil.copy(ATTRIBUTE_SET_FILE, self._config_file)

    def _create_from_proj_file(self):
        states = ReadFromFile(self._proj_file)
        for key, v_dict in states.items():
            self.video_files_state[key] = VideoAnnotation.from_dict(v_dict)

    def _step2_initial_all_dicts(self):
        """
            Step2: 初始化内参，建立正确的索引
                搜索<VIDEO_HOME>中的所有视频，并从<PROJECT_CONFIG_FILENAME>文件中尝试恢复项目空间
                恢复完成或创建了新的空间后，将新发现的视频添加进去，并更新video_files_state
            """
        # 递归搜索到所有的视频文件，并返回它们相对于_video_dir的相对路径
        video_files = search_files(self._video_dir, tuple(DEFAULT_POSTFIXES), True)
        
        if os.path.exists(self._proj_file):
            self._create_from_proj_file()
            video_files_json = self.video_files_state
        else:
            video_files_json = {}
        
        new_files = set(video_files) - set(video_files_json)
        if len(new_files) > 0:
            answer = messagebox.askyesno(title="提示", message=f"默认视频路径中发现{len(new_files)}条新视频，是否添加它们？")
            if answer:
                self.add_videos(new_files)
        
        missing_files = set(video_files_json) - set(video_files)
        if len(missing_files) > 0:
            mfs = []
            for mf in missing_files:
                if os.path.isabs(mf):
                    if os.path.exists(mf):
                        continue
                mfs.append(mf)
                self.video_files_state[mf].state = VideoAnnotation.STATE_LOST
            
            messagebox.showwarning(title="警告", message=f"有{len(mfs)}个视频文件不见了，缺失的视频将在列表特殊显示，你可以选择删除或重定向该文件来修复这个问题!")
        
        # check lostfile
        for name, obj in self.video_files_state.items():
            if obj.state == VideoAnnotation.STATE_LOST:
                if os.path.exists(self.get_videofile(name)[1]):
                    obj.refound_videofile()
            obj.check()

    def add_videos(self, video_paths, copy_files=False):
        """
        自动检测添加的路径是否在当前basepath路径下，如果是则使用相对路径来表示，否则使用绝对路径来表示
        这样能够最大限度确保在移动了当前workspace文件夹后，仍然能够正确定位处于文件夹内或外部的所有视频文件
        """

        for video in video_paths:

            if not os.path.isabs(video):
                video = os.path.join(self._video_dir, video)
            if os.path.isfile(video):
                dirname, name = os.path.split(video)

                if copy_files and not dirname.startswith(self._video_dir):
                    i = 1
                    des_path = os.path.join(self._video_dir, name)    # 自动拷贝过来的文件只能被放在Video默认根目录下
                    name, postfix = os.path.splitext(name)
                    new_name = "%s%s" %(name, postfix)
                    while os.path.exists(des_path):
                        new_name = "%s(%d)%s" % (name, i, postfix)
                        des_path = os.path.join(self._video_dir, new_name)
                        i+=1
                    name = new_name
                    assert video != des_path
                    shutil.copy(video, des_path)
                    video = des_path
                else:
                    video = os.path.join(dirname, name)
                
                video_rel = os.path.relpath(video, self._video_dir)
                if video_rel.startswith('..'):
                    # not in workspace, which means unsafe, turn it into absolute path
                    video_rel = video

                self.video_files_state[video_rel] = self._create_annotation_obj(video_rel)
        # print(self.video_files_state)

    def _create_annotation_obj(self, video_path):
        va =  VideoAnnotation()
        va.anno_id = _get_hash_name(video_path)
        va.video_file = video_path
        va.target_names = []
        va.state = va.STATE_NOT_START
        # va.md5 = hashlib.md5()

        anno_dir = os.path.join(self._anno_dir, va.anno_id)
        if os.path.exists(anno_dir):
            va.add_with_check(anno_dir)
        else:
            os.makedirs(anno_dir)

        return va
    
    def remove_videos(self, names):
        dont_remove_videos = []
        for name in names:
            v:VideoAnnotation = self.video_files_state[name]
            if (v.state == v.STATE_LOST) or os.path.isabs(v.video_file):
                dont_remove_videos.append(v)
        
        ans = messagebox.askyesno("注意", f"即将移除{len(names)}个视频，其中有{len(names)-len(dont_remove_videos)}个视频处于项目默认Videos路径下的源视频文件将被删除，是否继续？")
        if not ans:
            self._L.info('视频移除操作被取消！')
            return
        #"注意"，f"即将移除{len(names)}个视频，其中有{len(names)-len(dont_remove_videos)}个视频处于项目默认Videos路径下的源视频文件将被删除，是否继续？"
        for name in names:

            state_dict:VideoAnnotation = self.video_files_state.pop(name)
            
            if state_dict not in dont_remove_videos:
                try:
                    os.remove(os.path.join(self._video_dir, state_dict.video_file))
                except:
                    os.chmod(os.path.join(self._video_dir, state_dict.video_file), stat.S_IWRITE)
                    os.remove(os.path.join(self._video_dir, state_dict.video_file))
                self._L.info('Remove video successfully: %s' % state_dict.video_file)

            rm_anno_dir = os.path.join(self._anno_dir, state_dict.anno_id)
            if os.path.exists(rm_anno_dir):
                if len(state_dict.target_names) > 0:
                    ans = messagebox.askyesno("注意",f"发现视频({state_dict.video_file})的标注文件(标注ID：{state_dict.anno_id})，是否要一同删除？")
                    if not ans:
                        self._L.info('[Skipped] Reserved annotation files: %s' % rm_anno_dir)
                        continue
                shutil.rmtree(rm_anno_dir)
                self._L.info('Remove annotation files successfully: %s' % rm_anno_dir)
            
        
        
    @property
    def LabelSettingsFile(self): return self._config_file

    @property
    def ProjectPath(self): return self._base_path
    
    @property
    def ProjectConfigFile(self): return self._proj_file

    @property
    def VideoHome(self): return self._video_dir

    @property
    def AnnotationFiles(self): return self._anno_dir

    @classmethod
    def OpenWorkspace(cls, workspace_path=None):
        # print(workspace_path)
        assert workspace_path is not None or SharedNamespace.workspace is not None

        if SharedNamespace.workspace is None:
            """
            项目的工作空间为单例模式下进行，当打开下一个工作空间时需要先关掉并释放上一个工作空间资源
            """
            
            workspace = cls(workspace_path)
            SharedNamespace.workspace = workspace
            return workspace
        elif workspace_path is None:
            """
            路径为空意为返回当前现有workspace
            """
            
            return SharedNamespace.workspace
        else:
            """
            此项意图为打开新的workspace，并关闭并保存原有workspace
            """
            workspace_path.close()
            workspace = cls(workspace_path)
            SharedNamespace.workspace = workspace
            return workspace
        
    @classmethod
    def CloseAll(cls):
        if SharedNamespace.workspace is not None:
            SharedNamespace.workspace.close()
            SharedNamespace.workspace = None

    def load_configs(self):
        # self._conf = os.path.join(self._base_path, self.config_file)
        if not os.path.exists(self._config_file):
            shutil.copy(ATTRIBUTE_SET_FILE, self._config_file)
        
        self._create_attrs(self._config_file)

    def _create_attrs(self, config_file):
            SharedNamespace.attrs.clear()
            attrs: dict = AttrType.ReadFromFile(config_file)
            try:
                SharedNamespace.classnames = attrs.pop("class")[0]
            except KeyError:
                raise KeyError('The "class" attribute is necessary configuration item for: %s' % config_file)
            
            for k, v in attrs.items():
                
                for v_ in v:
                    SharedNamespace.attrs[v_.Name] = v_

    def get_videofile(self, name: str):
        
        state_dict:VideoAnnotation = self.video_files_state.get(name, None)

        if state_dict is None:
            raise ValueError('Video:%s is not in list!' % name)

        # print(state_dict)

        video_file = state_dict.video_file
        if not os.path.isabs(video_file):
            video_file = os.path.join(self._video_dir, state_dict.video_file)

        return state_dict.state, video_file

    def get_video_names(self, orderd:str="None"):
        """
        orderd:
           - None: 按照默认顺序显示，不调整顺序
           - State: 按照状态优先级显示
           - Name: 按照名字字母顺序显示
        """
        def sort_with_state(name_input):
            state = self.video_files_state[name_input].state
            return "%d%s" % (state, name_input)

        names = list(self.video_files_state)
        if orderd == 'None':
            pass
        elif orderd == "State":
            names.sort(key=sort_with_state)
        elif orderd == "Name":
            names.sort()
        return [(name, self.video_files_state[name].state) for name in names]

    def save_default(self):
        dict_out = {}
        for k, anno_dict in self.video_files_state.items():
            dict_out[k] = anno_dict.to_dict() 
        SaveToFile(self._proj_file, dict_out, description="Project file saved in: %s" % self._proj_file)

    def close(self):
        self.__is_closed = True
        self.save_default()
    
    def __del__(self):
        if not self.__is_closed:
            self.close()
        self._L.info(f'退出空间: {self.ProjectPath}')
    

class SharedNamespace: 
    # global shared
    global_ctrl = None
    frameseq_panel = None

    # workspace level
    classnames: ClassAttr = None
    attrs = {}
    workspace: WorkSpace = None

    # video level
    video_frame_obj = None
    anno_obj: VideoAnnotation = None
    

    @classmethod
    def Clean(cls):
        cls.classnames = None
        cls.video_frame_obj = None
        cls.workspace = None
        cls.anno_obj = None
        cls.attrs.clear()

    @classmethod
    def Scale(cls): return cls.global_ctrl.scale.RateVar

    @classmethod
    def FrameCurrIndex(cls): return cls.global_ctrl._current_frames-1