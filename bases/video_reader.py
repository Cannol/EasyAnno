import sys
import cv2
import os

import struct

from collections import OrderedDict
from PIL import Image

import threading

import tqdm

from logging import Logger
from common.logger import LoggerMeta

class VideoSequence(object, metaclass=LoggerMeta):

    _L: Logger  = None

    def __init__(self, video_file_path, progress_bar=None):
        self._video_file_path = video_file_path

        self._video_height = 0
        self._video_width = 0
        self._frame_count = 0
        self._video_name = ""

        self.video_info = {}
        self._pro_bar = progress_bar
        self._first_pic = None
        self._frames = []
        self._read_info()
        self._is_reading = False
        self._stop_read = False

    def read(self, asyn=False):
        
        if asyn:
            self._is_reading = True
            self._read_asyn()
        else:
            self._is_reading = True
            self._read_all()
            self._is_reading = False

    def _read_asyn(self):
        self._t = threading.Thread(target=self._read_all, daemon=True)
        self._t.start()
    
    def stop_read(self):
        # self._L.info('STOP')
        self._stop_read = True
        self._t.join(timeout=0.1)
        # self._stop_read = False
        # self._is_reading = False

    def _read_info(self):
        cap = cv2.VideoCapture(self._video_file_path)
        self._video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

        self._frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        self._video_name = os.path.basename(self._video_file_path)

        self.video_info = {'source_path': self._video_file_path,
                            "video_name": self._video_name,
                            'fourcc': struct.pack('i', int(cap.get(cv2.CAP_PROP_FOURCC))).decode('ascii'),
                            'fps': int(cap.get(cv2.CAP_PROP_FPS)),
                            'frame_count': self._frame_count,
                            'width': self._video_width,
                            'height': self._video_height,
                            'is_rgb': not bool(cap.get(cv2.CAP_PROP_CONVERT_RGB))
                            }
        
        ret, frame = cap.read()
        self._channel = frame.shape[2]
        if ret == 0:
            raise IOError(f'尝试读取视频第一帧时出问题！{self._video_file_path}')
        
        self._frames = [None] * self._frame_count
        self._frames[0] = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA))
        cap.release()

    def _read_all(self):
        cap = cv2.VideoCapture(self._video_file_path)
        if self._pro_bar is None:
            progress = tqdm.tqdm(range(self._frame_count))
        else:
            progress = range(self._frame_count)

        for i in progress:
            if self._stop_read:
                self._L.info('读取终止：%s' % self._video_file_path)
                return
            if self._pro_bar is not None:
                self._pro_bar.PercentageBottom = i/self._frame_count

            if self._frames[i] is None:
                ret, frame = cap.read()
                if ret == 0:
                    if self._pro_bar is None:
                        progress.write('Error occurred in reading frame: %d' % (i+1))
                    continue
                self._frames[i] = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA))
                
        if len(self._frames) != self._frame_count:
            self._L.warning(f"视频实际读取的帧数({len(self._frames)})与视频原始信息读取的帧数不符({self._frame_count})，视频存在错误帧被跳过，可能会导致未知标注问题！")
        self._L.info('数据读取完毕，读取线程退出。')
        cap.release()
        self._stop_read = False
        self._is_reading = False

    def iter_read(self, cell_length, discard=True):
        cap = cv2.VideoCapture(self._video_file_path)

        if discard:
            length = self._frame_count//cell_length * cell_length
            if length != self._frame_count:
                self._L.info('视频%s不满足%d的倍数条件，末尾被舍弃，长度由%d变为%d' % (self._video_name, cell_length, self._frame_count, length))
        else:
            length = self._frame_count

        progress = tqdm.tqdm(range(length))

        for i in progress:
            ret, frame = cap.read()
            if ret == 0:
                progress.write('Error occurred in reading frame: %d' % (i+1))
                continue
            yield i, frame
                
        cap.release()

    @property
    def Shape(self): return self._video_height, self._video_width, self._channel

    def __len__(self): return self._frame_count

    def __getitem__(self, item):
        # assert isinstance(item, int)
        
        img = self._frames[int(item)]
        if img:
            return img.copy()
        return None