import os
import json
import re

import pandas as pd
import numpy as np

# from PyQt6.QtGui import QAction
from PyQt6 import QtWidgets as qt
from PyQt6 import QtGui
from PyQt6.QtCore import QSize, Qt, QMargins, QTimer
from bs4 import BeautifulSoup

# Global Constants
APP_VERSION = "0.1.7"
URL_RE = re.compile(r"(ftp|http|https)://(\w+:?\w*@)?(\S+)(:\d+)?(/|/([\w#!:.?+=&%@!-/]))?")
CONTENT_MARGINS_NARROW = QMargins(2, 0, 2, 0)  # Left, Top, Right, Bottom
CONTENT_MARGINS_NORMAL = QMargins(2, 2, 2, 2)
LOREM_IPSUM = """
SOME TEXT
"""


def qt_widget_set_size(button: qt.QWidget, width: int = None, height: int = None):
    if width:
        button.setMinimumWidth(width)
        button.setMaximumWidth(width)

    if height:
        button.setMinimumHeight(width)
        button.setMaximumHeight(width)


class FormRadioButtons:
    """
        Form Radio Button Line Factory Class.
        Use new() method and pass in a list of button names.
        Return the groupbox and a list of created buttons.
    """
    def new(*button_names: str) -> (qt.QGroupBox, list[qt.QRadioButton]):
        rdo_gbox = qt.QGroupBox()
        rdo_hbox = qt.QHBoxLayout()

        lst_btn = []
        for button_name in button_names:
            btn = qt.QRadioButton(button_name)
            lst_btn.append(btn)
            rdo_hbox.addWidget(btn)

        lst_btn[0].setChecked(True)
        rdo_gbox.setLayout(rdo_hbox)

        rdo_hbox.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        rdo_hbox.setContentsMargins(CONTENT_MARGINS_NARROW)
        rdo_gbox.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Minimum)
        return rdo_gbox, *lst_btn


class PythonBox(qt.QPlainTextEdit):
    '''
        Custom QPlainTextEdit with [Tab] key behavior override for ease of python coding.
    '''
    def __init__(self):
        super().__init__()
        self.setTabStopDistance(20)
        self.setLineWrapMode(self.LineWrapMode.NoWrap)

    def keyPressEvent(self, e: QtGui.QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Tab:
            self.insertPlainText('\t')
        else:
            super().keyPressEvent(e)


class EntityBox(qt.QWidget):
    """
    EntityBox is a self-containing widget for scraping one URL.
    """

    # These tags are unlikely to contain useful information, or contain an array of nested information.
    # Therefore, they are excluded during the tag parsing stage.
    TAG_EXCLUDE = ['script', 'meta', 'head', 'noscript', 'svg', 'html', 'aside', 'main']

    def __init__(self, parent):

        # parent
        super().__init__()
        self.parent = parent

        # data
        self.status_code = -1
        self.resp_raw = None
        self.resp_soup = None
        self.resp_html_full = None
        self.resp_html = None
        self.is_with_css = True
        self.func_transform = None
        self.is_with_transform = False

        # widgets
        self.display = ScrollDisplay()
        self.input_url = qt.QLineEdit()
        self.input_filter = qt.QLineEdit()
        self.input_transform = PythonBox()

        self.rdo_gbox_with, self.rdo_with_css, self.rdo_with_text = FormRadioButtons.new("CSS", "Text")
        self.rdo_gbox_disp, self.rdo_html, self.rdo_clean, self.rdo_raw = FormRadioButtons.new("HTML", "Clean", "Raw")

        self.btn_fetch = qt.QPushButton("Fetch")
        self.btn_transform = qt.QPushButton("Transform")

        self.btn_transform.setCheckable(True)
        self.input_filter.setEnabled(False)

        # layout
        layout_l1 = qt.QGridLayout()
        layout_l2_left = qt.QVBoxLayout()
        layout_l3_form = qt.QFormLayout()
        layout_l3_btn = qt.QHBoxLayout()
        layout_l3_form.setFieldGrowthPolicy(qt.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Form
        layout_l3_form.addRow("URL", self.input_url)
        layout_l3_form.addRow("Filter", self.input_filter)
        layout_l3_form.addRow("With", self.rdo_gbox_with)
        layout_l3_form.addRow("Display", self.rdo_gbox_disp)
        layout_l3_form.addRow("Transform", self.input_transform)

        # Form Button
        layout_l3_btn.addWidget(self.btn_fetch)
        layout_l3_btn.addWidget(self.btn_transform)

        layout_l2_left.addLayout(layout_l3_form)
        layout_l2_left.addLayout(layout_l3_btn)
        layout_l1.addLayout(layout_l2_left, 0, 0)
        layout_l1.addWidget(self.display, 0, 1)
        layout_l1.setColumnStretch(0, 1)
        layout_l1.setColumnStretch(1, 5)

        # Spacing
        layout_l1.setContentsMargins(CONTENT_MARGINS_NARROW)
        layout_l3_form.setContentsMargins(CONTENT_MARGINS_NARROW)

        # Size
        self.setMinimumSize(800, 180)
        self.setMaximumSize(800, 360)

        # Collect remaining parts
        self.form = layout_l3_form
        self.setLayout(layout_l1)
        self.input_url.setText("https://")
        self.form.setRowVisible(4, False)

        # Set reactions
        self.btn_fetch.clicked.connect(self.requests_get)
        self.btn_transform.clicked.connect(self.enable_transform)
        self.input_filter.textChanged.connect(self.send_to_display)
        self.rdo_html.clicked.connect(self.output_html)
        self.rdo_clean.clicked.connect(self.output_clean)
        self.rdo_raw.clicked.connect(self.output_raw)
        self.rdo_with_css.clicked.connect(self.with_css)
        self.rdo_with_text.clicked.connect(self.with_text)

    def requests_get(self, _=None):
        """
            Given URL in self.input_url.text(), blocking fetch and display content.
        """

        if not bool(URL_RE.match(self.input_url.text())):
            self.set_status("The provided URL is invalid. It must starts with [ http(s):// ].")
            return

        try:
            from aio import async_fetch
            # resp = requests.get(self.input_url.text())
            resp = async_fetch(self.input_url.text()).result()
        except BaseException as e:
            self.set_status(repr(e))
            return

        if resp.status_code == 200:
            self.enable_transform(False)
            self.status_code = resp.status_code

            # Parse response
            self.resp_raw = resp.text
            self.resp_soup = BeautifulSoup(self.resp_raw, 'lxml')
            self.resp_html_full = self.resp_soup.prettify()

            # Post process
            self.btn_fetch.setText("Re-fetch")
            self.input_filter.setEnabled(True)
            self.send_to_display()
            self.set_status("URL Fetch succeeded.")

        else:
            self.set_status(repr(resp))

    def requests_extract(self, _=None):
        """
            Extract data only after self.requests_get() is called.
            Responsive to display options.

            Note that CSS option used RegEx, therefore any filter with non-alphanumeric character must be escaped.

            e.g. ``List(n)`` must be entered as ``List\(n\)``.
        """
        if self.status_code != 200:
            return

        if not len(self.input_filter.text()):
            self.resp_html = self.resp_html_full
            return

        try:
            if self.is_with_css:
                repo_html = []
                for tag in list(self.resp_soup.find_all(class_=re.compile(self.input_filter.text()))):
                    if tag.name not in EntityBox.TAG_EXCLUDE:
                        if str(tag) not in repo_html:
                            repo_html.append(str(tag))
                resp_html_sub = '<br>\n'.join(repo_html)

            else:
                repo_html = []
                for tag in list(self.resp_soup.find_all()):
                    if (tag.name not in EntityBox.TAG_EXCLUDE) and (self.input_filter.text() in tag.text):
                        if str(tag) not in repo_html:
                            repo_html.append(str(tag))
                resp_html_sub = '<br>\n'.join(repo_html)

        except BaseException as e:
            resp_html_sub = repr(e)

        self.resp_html = resp_html_sub

    def send_to_display(self):
        if self.status_code != 200:
            return

        self.requests_extract()
        self.display.set_text(self.resp_html)

    def output_html(self, _=None):
        self.display.output_option = 0
        self.send_to_display()

    def output_clean(self, _=None):
        self.display.output_option = 1
        self.send_to_display()

    def output_raw(self, _=None):
        self.display.output_option = 2
        self.send_to_display()

    def with_css(self, _=None):
        self.is_with_css = True
        self.send_to_display()

    def with_text(self, _=None):
        self.is_with_css = False
        self.send_to_display()

    def set_status(self, msg):
        self.parent.set_status(msg)

    def enable_transform(self, enable):
        if enable:
            self.is_with_transform = True
            self.form.setRowVisible(4, True)
            self.input_transform.textChanged.connect(self.get_from_input_and_set_transform)

            self.get_from_input_and_set_transform()
            self.set_status('Transform enabled.')

        else:
            self.is_with_transform = False
            self.form.setRowVisible(4, False)
            if self.input_transform.receivers(self.input_transform.textChanged) > 0:
                self.input_transform.textChanged.disconnect()

            self.unset_display_transform()
            self.set_status('Transform disabled.')

    def unset_display_transform(self):
        self.func_transform = None
        self.display.set_transform(None)

    def set_display_transform(self):
        self.set_status('Transform set and ready.')
        self.display.set_transform(self.func_transform)

    def get_from_input_and_set_transform(self):
        """
        Advanced function !!

        Transforms the output on the display to a new form with a Python function.

        Suggest to be paired with HTML display mode given WYSIWYG, otherwise for non-HTML data,
        some tags maybe added to the raw data given the soup conversion.

        Example
        ----------------------------------
        url=https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=fnd&lang=en

        .. code-block:: python
        def f(x):
            tmp = pd.DataFrame(json.loads(x)['weatherForecast']).set_index('forecastDate')
            cols = ['forecastMaxtemp', 'forecastMintemp', 'forecastMaxrh', 'forecastMinrh']

            for col in cols:
                tmp[col] = tmp[col].apply(lambda x: float(x['value']))

            return tmp[cols].to_markdown()

        """

        # TODO: Add transformation as charts, also add ability to dynamically import
        err_msg = 'Transformation must be a Python function starting with ' \
                  'def f(x): and returns a value, input is malformed'
        # x: str = self.display.label.document().toPlainText()
        fn: str = self.input_transform.document().toPlainText()

        try:
            fn = fn.strip()
            if not fn.startswith('def') or 'return' not in fn:
                self.set_status(err_msg)

            # Extract parameters from function, mangle function name and call from local
            # fn_sig_ori = fn[fn.index(" ")+1:fn.index("(")]
            fn_sig_new = f'_F{id(self)}'
            fn_args = fn[fn.index("(")+1:fn.index(")")]
            fn_body = fn[fn.index('\n')+1:]
            fn_reconstructed = f"def {fn_sig_new}({fn_args}):\n{fn_body}"
            exec(fn_reconstructed)

            self.func_transform = locals()[fn_sig_new]
            self.set_display_transform()
            self.send_to_display()

        except Exception as e:
            self.set_status(err_msg)
            self.func_transform = lambda x: x

    def to_config(self) -> dict:
        cfg = dict(
            url=self.input_url.text(),
            filter=self.input_filter.text(),
            is_with_css=self.is_with_css,
            output_option=self.display.output_option,
            is_with_transform=self.is_with_transform,
            transform=self.input_transform.document().toPlainText() if self.func_transform is not None else ""
        )
        return cfg

    def from_config(self, cfg: dict):
        self.input_url.setText(cfg.get('url', ''))
        self.input_filter.setText(cfg.get('filter', ''))
        self.is_with_css = cfg.get('is_with_css', True)
        self.display.output_option = cfg.get('output_option', 0)
        self.is_with_transform = cfg.get('is_with_transform', False)
        self.input_transform.setPlainText(cfg.get('transform', ''))

        if self.is_with_css:
            self.rdo_with_css.setChecked(True)
        else:
            self.rdo_with_text.setChecked(True)

        if self.display.output_option == 0:
            self.rdo_html.setChecked(True)
        elif self.display.output_option == 1:
            self.rdo_clean.setChecked(True)
        elif self.display.output_option == 2:
            self.rdo_raw.setChecked(True)

        self.requests_get()
        if self.is_with_transform:
            self.btn_transform.setChecked(True)
            self.enable_transform(True)


class ScrollDisplay(qt.QScrollArea):
    """
        Scrollable Website Content Display.
    """
    # constructor
    def __init__(self):
        super().__init__()
        self.output_option = 0
        self.func_transform = None

        # making widget resizable
        self.setWidgetResizable(True)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)

        # creating text field
        self.label = qt.QTextEdit(self)
        self.label.setLineWrapMode(self.label.LineWrapMode.NoWrap)
        self.label.setReadOnly(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.label.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)

        self.setWidget(self.label)

    def set_transform(self, func=None):
        self.func_transform = func

    def set_text(self, html):
        # Option = HTML
        if self.output_option == 0:
            self.label.setText(html)

        # Option = Clean
        elif self.output_option == 1:
            plain_soup = BeautifulSoup(html, 'lxml')
            body = re.sub('[\n| ]+', '\n', plain_soup.text)
            self.label.setPlainText(body)

        # Option = Raw
        elif self.output_option == 2:
            self.label.setPlainText(html)

        # With Transform
        if self.func_transform is not None:
            try:
                text = self.func_transform(self.label.document().toPlainText())
                self.label.setPlainText(text)
            except BaseException as e:
                self.label.setPlainText(repr(e))


class MainWindow(qt.QMainWindow):
    '''
        Custom QMainWindow holding all widgets.
    '''
    def __init__(self):
        super().__init__()

        # window parameters
        self.setWindowTitle(f"BeautifulSoup GUI v{APP_VERSION}")
        self.setMinimumSize(QSize(840, 360))
        self.setMaximumSize(QSize(840, 1080))

        self.status_bar = qt.QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.refresh_timer = QTimer(self)
        self.list_entity_box: list[EntityBox] = list()

        # self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # self.customContextMenuRequested.connect(lambda: print("calling context menu"))

        # widgets init
        self.btn_add_display = qt.QPushButton("Add Display")
        self.btn_rmv_display = qt.QPushButton("Remove Display")
        self.btn_fetch_all = qt.QPushButton("Fetch All")
        self.btn_save_config = qt.QPushButton("Save Config")
        self.btn_load_config = qt.QPushButton("Load Config")
        self.chk_auto_refresh = qt.QCheckBox("Auto Refresh")
        qt_widget_set_size(self.btn_add_display, width=120)
        qt_widget_set_size(self.btn_rmv_display, width=120)
        qt_widget_set_size(self.btn_fetch_all, width=120)
        qt_widget_set_size(self.btn_save_config, width=120)
        qt_widget_set_size(self.btn_load_config, width=120)
        qt_widget_set_size(self.chk_auto_refresh, width=110)

        # 1/ Layouts
        widget_main = qt.QWidget()
        layout_main = qt.QVBoxLayout()

        self.layout_main_fixed_btn = qt.QHBoxLayout()
        self.layout_main_fixed_btn.setSpacing(4)
        self.layout_main_fixed_btn_left = qt.QHBoxLayout()
        self.layout_main_fixed_btn_right = qt.QHBoxLayout()

        self.layout_main_fixed_btn_left.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout_main_fixed_btn_right.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Layout | Spacer | Layout such that btn_left is left aligned, btn_right is right aligned
        self.layout_main_fixed_btn.addLayout(self.layout_main_fixed_btn_left)
        self.layout_main_fixed_btn.addItem(qt.QSpacerItem(0, 0, qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Minimum))
        self.layout_main_fixed_btn.addLayout(self.layout_main_fixed_btn_right)

        # 2/ Left Button
        self.layout_main_fixed_btn_left.addWidget(self.btn_add_display, alignment=Qt.AlignmentFlag.AlignLeft)
        self.layout_main_fixed_btn_left.addWidget(self.btn_rmv_display, alignment=Qt.AlignmentFlag.AlignLeft)
        self.layout_main_fixed_btn_left.addWidget(self.btn_fetch_all,   alignment=Qt.AlignmentFlag.AlignLeft)

        # 3/ Right Buttons
        self.layout_main_fixed_btn_right.addWidget(self.chk_auto_refresh, alignment=Qt.AlignmentFlag.AlignLeft)
        self.layout_main_fixed_btn_right.addWidget(self.btn_save_config, alignment=Qt.AlignmentFlag.AlignLeft)
        self.layout_main_fixed_btn_right.addWidget(self.btn_load_config, alignment=Qt.AlignmentFlag.AlignLeft)

        # Compose Layout
        self.layout_main_display = qt.QScrollArea()
        self.layout_main_display_widget = qt.QWidget()
        self.layout_main_display_widget_layout = qt.QVBoxLayout()

        self.layout_main_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.layout_main_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.layout_main_display.setWidgetResizable(True)

        self.layout_main_display.setWidget(self.layout_main_display_widget)
        self.layout_main_display_widget.setLayout(self.layout_main_display_widget_layout)

        layout_main.addLayout(self.layout_main_fixed_btn)
        layout_main.addWidget(self.layout_main_display)
        widget_main.setLayout(layout_main)
        self.layout_main_fixed_btn.setAlignment(Qt.AlignmentFlag.AlignLeft)

        widget_main.setContentsMargins(CONTENT_MARGINS_NORMAL)
        layout_main.setContentsMargins(CONTENT_MARGINS_NORMAL)
        layout_main.setSpacing(0)

        # connect
        self.btn_add_display.clicked.connect(self.add_display)
        self.btn_rmv_display.clicked.connect(self.rmv_display)
        self.btn_fetch_all.clicked.connect(self.fetch_all)
        self.btn_save_config.clicked.connect(self.save_config)
        self.btn_load_config.clicked.connect(self.load_config)
        self.chk_auto_refresh.clicked.connect(self.set_refresh)
        self.setCentralWidget(widget_main)

        # late init
        self.add_display()
        self.resize(QSize(840, 360))
        self.set_status("Initialization completed.")

    def add_display(self) -> EntityBox:
        """
        Add an EntityBox.
        """
        eb = EntityBox(self)
        self.list_entity_box.append(eb)
        self.layout_main_display_widget_layout.addWidget(eb)
        self.set_status('Added new widget')
        return eb

    def rmv_display(self):
        """
        Remove the bottom most EntityBox.
        """
        if len(self.list_entity_box):
            eb: EntityBox = self.list_entity_box.pop()
            self.layout_main_display_widget_layout.removeWidget(eb)
            self.set_status('Removed bottom most widget')

        else:
            self.set_status('Cannot remove widget')

    def rmv_all_display(self):
        """
        Remove all EntityBox.
        """
        num_of_eb = len(self.list_entity_box)
        for i in range(num_of_eb):
            self.rmv_display()
        self.set_status('Removed all widgets')

    def fetch_all(self):
        """
        For all existing EntityBox, fetch and display content.
        """
        for eb in self.list_entity_box:
            eb.requests_get()

    def save_config(self):
        """
        For all existing EntityBox, fetch and save their config.
        """
        global_cfg = {}
        for idx, eb in enumerate(self.list_entity_box):
            global_cfg[idx] = eb.to_config()

        with open("./config.json", 'w+') as f:
            json.dump(global_cfg, f)

        self.set_status(f"Config saved to {os.getcwd()}/config.json")

    def set_refresh(self, check_state):
        import time

        def fetch_all_with_time():
            self.fetch_all()
            self.set_status(f"Auto refreshed at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")

        if check_state:
            self.refresh_timer.timeout.connect(fetch_all_with_time)
            self.refresh_timer.start(int(1000 * 60 * 5))

        else:
            self.refresh_timer.stop()
            self.set_status(f"Auto refresh stopped.")

    def load_config(self):
        """
            Clear all existing EB, load entirely new list of EntityBox from config.
        """
        # TODO: Add a dialog to select arbitrary config
        # TODO: Can add a preload config option
        self.rmv_all_display()

        try:
            with open("./config.json", 'r') as f:
                try:
                    cfg = json.load(f)

                except Exception as e:
                    # Could include JSONDecodeError or other IOError
                    self.set_status("config.json may be corrupted. Try recreating proper file with Save Config.")

                # Create display from config one at a time
                for key in cfg:
                    cfg_ = cfg[key]
                    self.add_display().from_config(cfg_)

        except FileNotFoundError:
            self.set_status("config.json not found in current working directory. Check if file exists.")

        self.set_status("Load config succeeded.")

    def set_status(self, e):
        self.status_bar.showMessage(e)

    def contextMenuEvent(self, e):
        pass
        # context = qt.QMenu(self)
        # context.addAction(QAction("test 1", self))
        # context.hovered.connect(lambda x: print("hovered over", x.text()))
        # context.triggered.connect(lambda x: print("pressed", x.str_html()))
        # context.exec(e.globalPos())

    # def mousePressEvent(self, e):
    #     if e.button() ...
    #     pass

    # def mouseReleaseEvent(self, e):
    #     pass

    # def mouseDoubleClickEvent(self, e):
    #     pass


def main():
    app = qt.QApplication([])

    window = MainWindow()
    window.show()

    app.exec()


if __name__ == '__main__':
    main()