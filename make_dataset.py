import os
from common.json_helper import ReadFromFile, SaveToFile
from bases.attrs import AttrBase, clean_all, FreeAttr, SingleAttr, MultiObjAttr
from bases.workspace import AttrType, SharedNamespace, FreeAttr as WFreeAttr
from bases.targets import Target
from bases.video_reader import VideoSequence

import cv2

# 修改参数区  =====================
"""
修改这里以配置:
 - WORKSPACE_ROOT：是workspace的根目录位置，如果在win环境，需要注意反斜杠的问题，建议在字符串前加r来避免错误转义
 - FILE_FORMAT: 输出文件的格式，其中包含三个字段，%s为视频名称，两个%04d分别为起始帧和结束帧的位置
 - USE_VIDEONAME_ONLY: 表示是否仅使用视频名称作为输出文件名称的组成
      例如：有三个文件目录中存在同一个名称的文件：
          - abc.mp4
          - aaa/abc.mp4
          - bbb/abc.mp4
      则视频名称自动保存为，即中间的路径斜杠会被下划线代替：
          - abc
          - aaa_abc
          - bbb_abc
 - SAME_FILE_SYMBOL：当没有使用USE_VIDEONAME_ONLY功能时，以上面的例子为例，则会按照出现的先后顺序加SAME_FILE_SYMBOL符号进行命名
          - abc
          - abc@1
          - abc@2
 - FRAMES_FOR_EACH_SCRIPT: 每个视频片段的截断长度（帧数），视频中不能被它整除的部分将会被舍弃
 - OUT_DIR：输出的数据集路径根目录位置
 - POST_FIX: 输出的视频帧图像后缀名称，如：jpg, png等，不要加“.”
"""

WORKSPACE_ROOT = r"C:\new_project"
FILE_FORMAT = r'%s#%04d-%04d'  # videoname#startframe-endframe
USE_VIDEONAME_ONLY = True
SAME_FILE_SYMBOL = '@'
FRAMES_FOR_EACH_SCRIPT = 25
POST_FIX = "jpg"

OUT_DIR = r"c:\output_path"
SKIP_EMPTY = True
# ============= END ==============

# 生成所有需要的预设路径
OUT_VIDEO_CLIPS = os.path.join(OUT_DIR, 'video_clips')
OUT_ANNO_FILES = os.path.join(OUT_DIR, "annotation_clips")
# os.makedirs(OUT_VIDEO_CLIPS, exist_ok=True)
# os.makedirs(OUT_ANNO_FILES, exist_ok=True)

WORKSPACE_VIDEOS = os.path.join(WORKSPACE_ROOT, 'Videos')
WORKSPACE_ANNOS = os.path.join(WORKSPACE_ROOT, 'Annotations')

PROJECT_FILE = os.path.join(WORKSPACE_ROOT, 'workspace.proj')
CONFIG_FILE = os.path.join(WORKSPACE_ROOT, 'config.yaml')

project_dict:dict = ReadFromFile(PROJECT_FILE)

def _create_attrs(config_file):
    attrs: dict = AttrType.ReadFromFile(config_file)
    try:
        SharedNamespace.classnames = attrs.pop("class")[0]
    except KeyError:
        raise KeyError('The "class" attribute is necessary configuration item for: %s' % config_file)
    
    for k, v in attrs.items():
        
        for v_ in v:
            SharedNamespace.attrs[v_.Name] = v_

video_names_saved = {}

def _video_name_transfer(name: str):
    pure_name = os.path.basename(name)
    if USE_VIDEONAME_ONLY:
        name = pure_name
    else:
        name = name.replace('/', '_')
        name = name.replace('\\', '_')
        name = name.replace('__', '_')   # 应对某些场景中存在双斜杠的情况
    out_name = os.path.splitext(name)[0]
    has_count = video_names_saved.get(out_name, 0)
    video_names_saved[out_name] = has_count+1
    if has_count > 0:
        pre_name = out_name
        out_name = "%s%s%d" % (pre_name, SAME_FILE_SYMBOL, has_count)
        print(f'[WARNING!] Same file name "{pre_name}" has been renamed to "{out_name}')
  
    return os.path.splitext(pure_name)[0], out_name

def _make_one_frame_info(frame_num, video_name, target_names):
    # target_ids = list(range(1, len(target_names)+1))
    valid_target = []
    ids = []
    bboxes = []
    category_id = []

    attr_types = {}
    for type_name, item_class in SharedNamespace.attrs.items():
        if isinstance(item_class, WFreeAttr):
            attr_types[f"{type_name}"] = []
        else:
            attr_types[f"{type_name}_id"] = []
    # for type_name in SharedNamespace.attrs

    for i, target_name in enumerate(target_names):
        target_obj:Target = Target.targets_dict[target_name]
        bbox = target_obj.get_bbox(frame_num-1)
        if bbox is None:
            continue
        valid_target.append(target_name)
        ids.append(i+1)
        bboxes.append(bbox)
        # print(target_obj.class_name)
        class_name = target_obj.class_name
        # print(class_name)
        class_id = SharedNamespace.classnames[class_name]
        # print(class_id)
        category_id.append(class_id)

        s_attrs:list[SingleAttr] = SingleAttr.attrs.get(target_name)
        for attr in s_attrs:
            value = int(attr[frame_num-1])
            attr_type = attr.type_name
            attr_types[f"{attr_type}_id"].append(value)

    r_attrs = MultiObjAttr.attrs
    for type_name, attr in r_attrs.items():
        # print(type_name, attr)
        # attr = MultiObjAttr()

        type_id = int(attr[frame_num-1])
        if type_id < 0:
            continue

        obj_id_in_relations = []
        for obj_name in attr.object_group:
            if obj_name in valid_target:
                obj_id_in_relations.append(target_id_map[obj_name])
        if len(obj_id_in_relations) == len(attr.object_group):
            attr_types[f"{attr.type_name}_id"].append(obj_id_in_relations + [type_id])
        # print(attr_types)
        # exit()

    f_attrs = FreeAttr.attrs
    # print(f_attrs)
    for type_name, attr in f_attrs.items():
        type_id = int(attr[frame_num-1])
        if type_id < 0:
            continue
        # print(attr.contents)
        type_obj = SharedNamespace.attrs[type_name]
        f_attr_content = type_obj[type_id]
        attr_types[f"{attr.type_name}"].append(f_attr_content)
    
    out_dict = {
        "frame": frame_num,
        "video_name": video_name,
        "id": ids,
        "bbox": bboxes,
        "category_id": category_id
    }

    for k, v in attr_types.items():
        out_dict[k] = v

    # print(out_dict)

    # exit()

    # if len(out_dict["captions"]) > 0:
    #     print(out_dict)

    return out_dict

def _save_video_frame(save_path, frame):
    # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    # img = Image.fromarray(frame)
    # img.save(save_path)
    cv2.imencode(".%s" % POST_FIX, frame)[1].tofile(save_path)

# print(_video_name_transfer('asdfa/abc.mp4'))
# print(_video_name_transfer('abc.mp4'))
# print(_video_name_transfer('afaf/abc.mp4'))

# exit(0)

_create_attrs(CONFIG_FILE)

AttrBase.SetAttrMap(SharedNamespace.attrs)

for video_name, contents in project_dict.items():
    target_names = contents['target_names']
    video_id = contents['anno_id']
    video_file = contents['video_file']
    

    if SKIP_EMPTY and len(target_names) == 0:
        print(f"[{video_name}] video_name:{video_file} id:{video_id} Targets: {target_names} --> Empty Skipped!")
    else:
        print(f"[{video_name}] video_name:{video_file} id:{video_id} Targets: {target_names}")

    anno_dir = os.path.join(WORKSPACE_ANNOS, video_id)

    if not os.path.isabs(video_file):
        video_file = os.path.join(WORKSPACE_VIDEOS, video_file)
    videoscript = VideoSequence(video_file_path=video_file)
    iter_frame = videoscript.iter_read(FRAMES_FOR_EACH_SCRIPT)
    length = len(videoscript)
    AttrBase.SetLength(length)
    Target.SetLength(length)
    AttrBase.SetDefaultPath(anno_dir)
    Target.SetDefaultSavingPath(anno_dir)
    w, h, _ = videoscript.Shape
    Target.SetGlobalOffsize(0,0,w,h)

    AttrBase.ReadAll(names=target_names)
    if len(FreeAttr.attrs) > 0:
        for type_name, attr_obj in FreeAttr.attrs.items():
            if type_name in SharedNamespace.attrs:
                type_obj: WFreeAttr = SharedNamespace.attrs[type_name]
                type_obj.bind_target_attr(attr_obj)
    Target.GetAllTargets()

    target_id_map = {}
    for i, target_name in enumerate(target_names):
        target_id_map[target_name] = i+1

    p_videoname, video_name_real = _video_name_transfer(video_name)

    for i, frame in iter_frame:

        """
        out_json_dicts格式如下：
            - 由FRAMES_FOR_EACH_SCRIPT个dict对象组成
            - 每个dict构成，举例如下：
               - {
                  "frame": 1, 
                  "video_name": "MVI_20011", 
                  "id": [1, 2, 3, 4, 5, 6, 7], 
                  "bbox": [[592.75, 378.8, 160.05, 162.2], [557.65, 120.98, 47.2, 43.06], [545.2, 88.27, 35.25, 30.08], [508.35, 67.5, 28.0, 25.925], [553.0, 70.095, 29.55, 19.695], [731.1, 114.23, 52.4, 39.95], [902.15, 250.12, 58.85, 107.99]], 
                  "category_id": [1, 1, 1, 1, 1, 1, 1], 
                  "relations": [[1, -1, 0], [2, -1, 0], [3, 5, 1], [3, -1, 0], [4, -1, 0], [5, -1, 0], [6, -1, 0], [7, -1, 0]]
                  }
        """
        
        if i % FRAMES_FOR_EACH_SCRIPT == 0:
            miniscript_name = FILE_FORMAT % (video_name_real, i+1, i+FRAMES_FOR_EACH_SCRIPT)
            out_json_dicts = []
            video_clip_save_dir = os.path.join(OUT_VIDEO_CLIPS, miniscript_name)
            os.makedirs(video_clip_save_dir, exist_ok=True)
        
        dict_out = _make_one_frame_info(i+1, video_name_real, target_names)
        out_json_dicts.append(dict_out)

        if len(out_json_dicts) == FRAMES_FOR_EACH_SCRIPT:
            # print("SAVE:", os.path.join(OUT_ANNO_FILES, "%s.json" % miniscript_name))
            SaveToFile(full_path=os.path.join(OUT_ANNO_FILES, "%s.json" % miniscript_name),
                       dict_obj=out_json_dicts,
                       create_dir=True)
            
        # save video
        frame_save_file = os.path.join(video_clip_save_dir, "img%05d_%s.%s" % (i+1, p_videoname, POST_FIX))
        # print(frame_save_file)
        # print(frame.shape)
        _save_video_frame(frame_save_file, frame)
        # exit()
        
    # clear all
    clean_all()
    del videoscript, iter_frame
    
