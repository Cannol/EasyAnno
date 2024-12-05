import numpy as np
import os

from bases.attrs import AttrBase
from bases.targets import Target
from bases.workspace import WorkSpace, SharedNamespace

VERSION = '1.0 beta'

Target.SetTargetSeed('Targets:')

def make_dataset_v1_0(save_dir, workspace_dir):
    space = WorkSpace.OpenWorkspace(workspace_dir)

    for video_name, anno_obj in space.video_files_state.items():
        # video_file = anno_obj.video_file
        
        print(video_name)

        video_file = os.path.join(space.VideoHome)
    
        make_one_video(anno_obj)

