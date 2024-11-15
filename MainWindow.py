import tkinter as tkk
from tkinter.ttk import Style
from logging import Logger
from common.logger import GLogger

from tools.components import TopBar, PlayController
from tools.components.panels import WorkspacePanel, ImageDrawPanel, ShapeBase
from tools.components.seqpanel import SeqenceAttributePanel
from bases.workspace import SharedNamespace

_VERSION = '1.0beta'

"""
    This script is the First Stage of Annotation
    This step is used to create new target that need to be annotation
    The administrator or designer of the dataset is responsible for this stage 
"""

# ====================================================================
#    Common Functions
# ====================================================================
def _default_win():
    tk = tkk.Tk()
    tk.title('EasyAnno - Version %s @Cannol' % _VERSION)
    tk.geometry('%dx%d+%d+%d' % (600, 600, 10, 10))
    # tk.overrideredirect(True)
    style = Style()
    style.configure('my.TButton', background='#345', foreground='black', font=('Arial', 14))
    return tk


# ====================================================================
#    Common Class
# ====================================================================
class MainWindow(object):
    # making logger
    _L: Logger = GLogger.get('MainWindow', 'MainWindow')

    # create default window
    root = _default_win()
    main_panel = tkk.Frame(root)
    left_panel = tkk.Frame(main_panel, bg="black")
    right_panel = WorkspacePanel(main_panel, width=200)
    menu_bar = TopBar(main_panel, height=30)
    right_panel.top_bar = menu_bar
    menu_bar.project_panel = right_panel
    seq_panel = SeqenceAttributePanel(root)
    seq_panel.construct()
    # seq_panel.initialize(length=1000, block_height=20, block_width=20)
    # seq_panel.set_menu())
    menu_bar.seq_panel = seq_panel
    # seq_panel = tkk.Frame(root, bg="green", height=100)

    main_panel.pack(fill=tkk.BOTH, expand=tkk.YES)
    menu_bar.pack(side=tkk.TOP, fill=tkk.X)
    right_panel.pack(side=tkk.LEFT, fill=tkk.Y)
    left_panel.pack(fill=tkk.BOTH, expand=True)
    # right_panel.construct_all()

    workspace_holder = tkk.Frame(left_panel, bg="red")
    workspace = ImageDrawPanel(workspace_holder, bg='black', highlightthickness=0)
    # workspace.bind_classes(SharedNamespace.classnames)
    ShapeBase.BindCanvasRoot(workspace)
    play_controller = PlayController(left_panel, workspace, height=60, bg='Gainsboro')
    seq_panel.bind_controller(play_controller)
    menu_bar.controler = play_controller
    menu_bar.bind_workspace(workspace)
    right_panel.controler = play_controller
    SharedNamespace.global_ctrl = play_controller
    # wp = WorkspacePanel(right_panel, height=20)

    workspace_holder.pack(expand=True)
    play_controller.pack(fill=tkk.X, side=tkk.BOTTOM)
    seq_panel.pack(fill=tkk.X)
    workspace.pack(side=tkk.LEFT)
    # wp.pack(fill=tkk.X)
    
    right_panel.update()
    _L.info('Got right_panel width: {}'.format(right_panel.winfo_width()))
    root.minsize(play_controller.MIN_WIDTH + right_panel.winfo_width(), 600)

    SharedNamespace.frameseq_panel = seq_panel

    @classmethod
    def set_images(cls, images):
        cls.play_controller.set_data(images)

    @classmethod
    def Run(cls):
        """
        this method include following steps:
        1. start and manage sub-processes
        2. do some prepare work before open the root screen
        3. start root screen
        4. clean the environment
        :return:int
        """
        # cls._construct()
        cls.root.mainloop()
        SharedNamespace.Clean()
        # cls._deconstruct()