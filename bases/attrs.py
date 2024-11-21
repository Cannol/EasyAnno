import os
from common.json_helper import JsonTransBase
from common.logger import LoggerMeta
from logging import Logger
import numpy as np

class AttrBase(JsonTransBase, metaclass=LoggerMeta):
    _L: Logger = None

    _length: int = 0
    _default_path: str = ""
    _abbr = ".attr"

    def get_target_name(self): return None

    @classmethod
    def SetLength(cls, length_total):
        cls._length = length_total

    @classmethod
    def SetDefaultPath(cls, default_path): cls._default_path = default_path 

    @classmethod
    def SetAttrMap(cls, attr_dict):
        cls.attr_map.clear()
        for dt in default_types:
            dt.clear()

        for attr_type, obj in attr_dict.items():
            attr_cls = type_map[obj._objects]
            default_types[obj._objects].append(attr_type)
            cls.attr_map[attr_type] = attr_cls
        
    attr_map = {}
    attrs = {}

    def __init__(self):
        self.type_name = ""
        self.data: np.ndarray = -np.ones(self._length, dtype=int)
        self._change_flag = False

    def __getitem__(self, indexes): return self.data[indexes]

    def __setitem__(self, indexes, value): 
        self.data[indexes] = value
        self._change_flag = True

    def __eq__(self, value): return self.data == value

    @classmethod
    def ReadAll(cls, names = None):
        if cls._default_path == "":
            raise ValueError('Please set default path first!')
        unknown_objs = []
        for file in os.listdir(cls._default_path):
            if file.endswith(cls._abbr):
                file2read = os.path.join(cls._default_path, file)
                attr_type = file.split('.')[-2]
                cls_attr:AttrBase = cls.attr_map.get(attr_type, None)
                if cls_attr is None:
                    unknown_objs.append(cls_attr)
                    continue
                obj = cls_attr.MakeNewFromJsonFile(json_file=file2read)
                if isinstance(obj, SingleAttr):
                    if names is not None and obj.target_name not in names:
                        unknown_objs.append(obj)
                        continue
                obj.register_self()
                obj._change_flag = False
        if names is not None:
            for name in names:
                SingleAttr.CheckAndCreate(name)
        FreeAttr.CheckAndCreate()
                    
        return unknown_objs

    @classmethod
    def SaveAll(cls):
        if cls._default_path == "":
            raise ValueError('Please set default path first!')
        
        for each_type in type_map:
            each_type.SaveAll()

    def register_self(self): self._change_flag = True
    def unregister_self(self): self._change_flag = False

    @property
    def Name(self): return self.type_name

    @property
    def File(self):
        return os.path.join(self._default_path, '%s%s' % (self.Name, self._abbr))

    def save_file(self):
        self.Json = self.File
        self._change_flag = False
        print(f'save file:{self.File}')

    def remove(self):
        self.unregister_self()
        if os.path.exists(self.File):
            os.remove(self.File)

    def from_dict(self, obj_dict):
        return super().from_dict(obj_dict)
    

class SingleAttr(AttrBase):

    attrs = {}

    def __init__(self):
        super().__init__()
        self.target_name = ""

    def get_target_name(self): return [self.target_name]

    @classmethod
    def CheckAndCreate(cls, target_name):
        if target_name in cls.attrs.keys():
            for type_name in default_types[1]:
                find = []
                for obj in cls.attrs[target_name]:
                    if obj.type_name == type_name:
                        find.append(obj)
                if len(find) == 1:
                    pass
                elif len(find) == 0:
                    obj = cls()
                    obj.target_name = target_name
                    obj.type_name = type_name
                    obj.register_self()
                else:
                    pass
        else:
            for type_name in default_types[1]:
                obj = cls()
                obj.target_name = target_name
                obj.type_name = type_name
                obj.register_self()
    
    @classmethod
    def DeleteTarget(cls, target_name):
        if target_name in cls.attrs.keys():
            attrs = cls.attrs.pop(target_name)
            for attr in attrs:
                attr.remove()

    def register_self(self):
        super().register_self()
        o = self.attrs.get(self.target_name, None)
        if o is None:
            self.attrs[self.target_name] = [self]
        else:
            self.attrs[self.target_name].append(self)
        
    def unregister_self(self):
        super().unregister_self()
        o:list = self.attrs.get(self.target_name, None)
        if o is not None and self in o:
            o.remove(self)
            if len(o) == 0:
                self.attrs.pop(self.target_name)

    @property
    def Name(self):
        return "%s.%s" % (self.target_name, self.type_name)
    
    @classmethod
    def SaveAll(cls):
        for _, o in cls.attrs.items():
            for o_ in o:
                o_.save_file()
        

class MultiObjAttr(AttrBase):

    """
    用来创建多个目标之间的关系，一般情况下多个事物之间的关系是一种较为稀疏的表示方式
    因此，我们可以为每一个小群体的关系建立独立的文件来保存
    """

    attrs = {}

    def get_target_name(self): return self.object_group.copy()

    def __init__(self):
        super().__init__()
        self.object_group: list[str] = []

    @property
    def Name(self): return f'{"_".join(self.object_group)}.{self.type_name}'

    def register_self(self):
        super().register_self()
        name = self.Name
        o = self.attrs.get(name, None)
        if o is None:
            self.attrs[name] = self
        else:
            raise ValueError('重复的项目:%s' % self.Name)
    
    def unregister_self(self):
        super().unregister_self()
        o = self.attrs.get(self.Name, None)
        if o is not None:
            self.attrs.pop(self.Name)

    @classmethod
    def SaveAll(cls):
        for _, o in cls.attrs.items():
            o.save_file()

class FreeAttr(AttrBase):

    attrs = {}

    def get_target_name(self): return None
        
    def __init__(self):
        super().__init__()

        self.contents = {}

    @classmethod
    def CheckAndCreate(cls):
        names = set(cls.attrs)
        names_should = set(default_types[0])
        names_add = names_should - names
        for name in names_add:
            obj = cls()
            obj.type_name = name
            
            obj.register_self()
    
    def register_self(self):
        super().register_self()
        name = self.Name
        o = self.attrs.get(name, None)
        if o is None:
            self.attrs[name] = self
        else:
            raise ValueError('重复的项目:%s' % self.Name)
        
    def unregister_self(self):
        super().unregister_self()
        name = self.Name
        o = self.attrs.get(name, None)
        if o is None:
            self.attrs.pop(name)
    
    @classmethod
    def SaveAll(cls):
        for _, o in cls.attrs.items():
            o.save_file()

    # def __getitem__(self, indexes): 
    #     label = self.data[indexes]
    #     return label, self.contents[label]

    # def __setitem__(self, indexes, value): 
    #     self.data[indexes] = value


type_map = [FreeAttr, SingleAttr, MultiObjAttr]
default_types = [[],[],[]]

thread_running = False
def auto_save_thread(sleep=0):
    import time
    global thread_running
    
    while thread_running:
        if sleep > 0:
            time.sleep(sleep)
        for type_now in type_map:
            for k, item in type_now.attrs.items():
                if isinstance(item, list):
                    for item_ in item:
                        if item_._change_flag:
                            item_.save_file()
                                            
                elif item._change_flag:
                    item.save_file()

auto_thread = None

def start_auto_thread():
    global auto_thread, thread_running
    import threading
    if auto_thread is None:
        auto_thread = threading.Thread(target=auto_save_thread, args=(5,))
        auto_thread.daemon = True
        thread_running = True
        auto_thread.start()
        # auto_thread.is_alive()
        # auto_thread.join()

def stop_auto_thread(wait_time=1):
    global auto_thread, thread_running
    if auto_thread is not None:
        thread_running = False
        auto_thread.join(wait_time)
        auto_save_thread()
        auto_thread = None

def clean_all():
    SingleAttr.attrs.clear()
    MultiObjAttr.attrs.clear()
    FreeAttr.attrs.clear()