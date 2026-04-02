import subprocess
import json
import os,re
import platform
import tomllib
import datetime
import requests
from getWhlUpdate import get_github_releases, filter_whl_assets
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QStackedWidget, QLabel, QCheckBox,
    QLineEdit, QFormLayout, QGroupBox, QFileDialog, QDialog, QComboBox, QTextEdit,
    QGridLayout, QFrame, QRadioButton, QButtonGroup
)
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtCore import QThread, Signal
import sys


class ReleaseWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, repo, platform_key="win", cuda_ver=None, python_ver=None, proxy=None):
        super().__init__()
        self.repo = repo
        self.platform_key = platform_key
        self.cuda_ver = cuda_ver
        self.python_ver = python_ver
        self.proxy = proxy

    def run(self):
        try:
            releases = get_github_releases(self.repo, proxy=self.proxy)
            if not releases:
                self.error.emit("未能获取到 GitHub Release 列表")
                return
            
            whl_info = filter_whl_assets(releases, self.platform_key, self.cuda_ver, self.python_ver)
            self.finished.emit(whl_info)
        except Exception as e:
            self.error.emit(str(e))

class ProcessWorker(QThread):
    log = Signal(str)
    finished = Signal(bool)  # 返回是否成功

    def __init__(self, cmd, cwd=None, desc="", env=None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.desc = desc
        self.env = env
        self.running = True

    def run(self):
        try:
            if self.desc:
                self.log.emit(f"🚀 {self.desc}...")

            # 实时输出
            p = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore",
                cwd=self.cwd,
                env=self.env,
                shell=True if isinstance(self.cmd, str) else False
            )

            # 逐行输出日志到GUI
            while self.running and p.poll() is None:
                line = p.stdout.readline()
                if line:
                    # 替换成（去掉颜色代码）
                    clean_line = re.sub(r'\x1b\[\d+;\d+m|\x1b\[0m', '', line.strip())
                    if clean_line:
                        self.log.emit(clean_line)

            return_code = p.poll()
            success = return_code == 0
            
            if success:
                self.log.emit(f"✅ {self.desc} 已完成")
            else:
                self.log.emit(f"❌ {self.desc} 失败，退出码: {return_code}")
                
            self.finished.emit(success)

        except Exception as e:
            self.log.emit(f"❌ 异常：{str(e)}")
            self.finished.emit(False)

class ProcessLogDialog(QDialog):
    def __init__(self, parent=None, title="操作日志"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(680, 450)
        self.setStyleSheet("background:#ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # 标题
        self.label = QLabel("⏬ 正在执行操作... 请勿关闭")
        self.label.setFont(QFont("微软雅黑", 10, QFont.Bold))
        layout.addWidget(self.label)

        # 日志文本框（显示CMD输出）
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background:#1e1e1e;
                color:#dcdcdc;
                border-radius:8px;
                padding:8px;
                font-family:Consolas;
                font-size:10pt;
            }
        """)
        layout.addWidget(self.log_text)

        # 关闭按钮（默认隐藏，完成后显示）
        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 6px;
            }
            QPushButton:hover { background-color: #e5e7eb; }
        """)
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.hide()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        # 进程对象
        self.worker = None

    def append_log(self, text):
        self.log_text.append(text)
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def show_close_btn(self):
        self.btn_close.show()

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "停止确认", "操作尚未完成，确定要停止吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.running = False
                e.accept()
            else:
                e.ignore()
        else:
            e.accept()

# 自定义侧边栏按钮
class SideBarButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFont(QFont("微软雅黑", 10))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 12px 16px;
                text-align: left;
                color: #333333;
                background-color: transparent;
                border-radius: 8px;
                margin: 4px 10px;
            }
            QPushButton:checked {
                background-color: #3a7bd5;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover:!checked {
                background-color: #e2e8f0;
                color: black;
            }
        """)

# 主窗口
class ModernSidebarWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.config_dir = "ComfyUI_Meme_Starter"
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.log_dir = os.path.join("cache_meme_data", "logs")
        self.log_file = os.path.join(self.log_dir, "meme_log.json")


        self.setWindowTitle("ComfyuiMemeStarter")
        self.setWindowIcon(QIcon("icon.ico")) # 设置任务栏图标
        self.setMinimumSize(1000, 650)
        self.is_dark_mode = False  # 主题模式

        # 无边框
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 主容器
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ========== 顶部标题栏（包含窗口按钮 + 主题切换） ==========
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(40)
        self.title_bar.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                border-top-right-radius: 12px;
            }
        """)
        self.title_layout = QHBoxLayout(self.title_bar)
        self.title_layout.setContentsMargins(15, 0, 10, 0)
        self.title_layout.setSpacing(10)

        # 软件图标
        self.icon_label = QLabel()
        self.icon_pixmap = QPixmap("icon.ico").scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(self.icon_pixmap)
        self.title_layout.addWidget(self.icon_label)

        # 窗口标题
        self.title_label = QLabel("ComfyUI Meme Starter")
        self.title_label.setFont(QFont("微软雅黑", 11, QFont.Bold))
        self.title_label.setStyleSheet("color: #1e293b;")


        # 主题切换按钮 ☀️ 🌙
        self.btn_theme = QPushButton("☀️")
        self.btn_min = QPushButton("—")
        self.btn_max = QPushButton("⚪")
        self.btn_close = QPushButton("❎")

        # 统一窗口按钮样式
        for btn in [self.btn_theme, self.btn_min, self.btn_max, self.btn_close]:
            btn.setFixedSize(35, 35)
            btn.setFont(QFont("微软雅黑", 11, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    background-color: transparent;
                    color: #333;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #e6e6e6;
                }
            """)

        # 关闭按钮特殊样式
        self.btn_close.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                color: #333;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #ff4d4f;
                color: white;
            }
        """)

        self.title_layout.addWidget(self.title_label)

        self.title_layout.addStretch()
        self.title_layout.addWidget(self.btn_theme)
        self.title_layout.addWidget(self.btn_min)
        self.title_layout.addWidget(self.btn_max)
        self.title_layout.addWidget(self.btn_close)

        # ========== 主体内容 ==========
        self.body_widget = QWidget()
        self.body_layout = QHBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)

        # 侧边栏（浅色主题）
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                border-bottom-left-radius: 12px;
            }
        """)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 20, 0, 20)
        self.sidebar_layout.setSpacing(5)

        self.btn_home = SideBarButton("  启动页面")
        
        self.btn_analytics = SideBarButton("  系统信息")
        self.btn_settings = SideBarButton("  环境配置")
        self.btn_about = SideBarButton("  关于")
        self.btn_advanceboard = SideBarButton("  高级选项")
        self.btn_downloadMod = SideBarButton("  下载功能")
        self.btn_offline_install = SideBarButton("  离线安装")
        self.btn_proxy = SideBarButton("  网络代理")
        self.btn_home.setChecked(True)

        # ========== 侧边栏顶部作者文字 ==========
        # 侧边栏顶部居中文字
        self.creator_label = QLabel("by Ai Maoster")
        self.creator_label.setFont(QFont("微软雅黑", 8))
        self.creator_label.setAlignment(Qt.AlignCenter)  # 👈 关键：居中
        self.creator_label.setStyleSheet("color: #1e293b;")
        self.sidebar_layout.addWidget(self.creator_label)

        self.sidebar_layout.addWidget(self.btn_home)
        self.sidebar_layout.addWidget(self.btn_analytics)
        self.sidebar_layout.addWidget(self.btn_settings)
        self.sidebar_layout.addWidget(self.btn_advanceboard)
        self.sidebar_layout.addWidget(self.btn_downloadMod)
        self.sidebar_layout.addWidget(self.btn_offline_install)
        self.sidebar_layout.addWidget(self.btn_proxy)

        self.sidebar_layout.addStretch()

        self.sidebar_layout.addWidget(self.btn_about)

        # 内容区域
        self.content_area = QWidget()
        self.content_area.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-bottom-right-radius: 12px;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(30, 20, 30, 30)

        self.stack = QStackedWidget()
        self.page_home = self.create_start_page()  # 使用新的启动页
        self.page_dashboard = self.create_advanced_page()  # 高级选项页面
        self.page_analytics = self.create_system_info_page()
        self.page_dd = self.create_download_page()  # 下载功能页面
        self.page_settings = self.create_settings_page()
        self.page_about = self.create_page("关于", "Modern UI v1.0")
        self.page_offline = self.create_offline_install_page() # 离线安装页面
        self.page_proxy = self.create_proxy_page() # 网络代理页面

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_dashboard)
        self.stack.addWidget(self.page_analytics)
        self.stack.addWidget(self.page_settings)
        self.stack.addWidget(self.page_about)
        self.stack.addWidget(self.page_dd)
        self.stack.addWidget(self.page_offline) # Index 6
        self.stack.addWidget(self.page_proxy) # Index 7
        self.content_layout.addWidget(self.stack)

        self.body_layout.addWidget(self.sidebar)
        self.body_layout.addWidget(self.content_area)
        self.main_layout.addWidget(self.title_bar)
        self.main_layout.addWidget(self.body_widget)

        # 绑定
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(self.toggle_max)
        self.btn_close.clicked.connect(self.close)
        self.save_btn.clicked.connect(self.save_config)

        self.btn_home.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_advanceboard.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_analytics.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.btn_settings.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        self.btn_about.clicked.connect(lambda: self.stack.setCurrentIndex(4))
        self.btn_downloadMod.clicked.connect(lambda: self.stack.setCurrentIndex(5))
        self.btn_offline_install.clicked.connect(lambda: self.stack.setCurrentIndex(6))
        self.btn_proxy.clicked.connect(lambda: self.stack.setCurrentIndex(7))

        self.dragging = False
        self.drag_pos = QPoint()

        # 启动加载配置
        config = self.load_config()
        if config:
            if "comfyui_root" in config:
                self.comfyui_path_input.setText(config["comfyui_root"])
            
            # 加载高级选项
            if "uv_enabled" in config:
                self.uv_switch.setChecked(config["uv_enabled"])
            if "online_enabled" in config:
                self.online_switch.setChecked(config["online_enabled"])
            if "online_ip" in config:
                self.online_ip_input.setText(config["online_ip"])
            if "online_port" in config:
                self.online_port_input.setText(config["online_port"])
            
            # 加载硬件模式
            hw_mode = config.get("hw_mode", 4)  # 默认 4 (不添加)
            btn = self.hw_btn_group.button(hw_mode)
            if btn: btn.setChecked(True)
            
            self.cb_smart_mem.setChecked(config.get("smart_mem_disabled", False))
            self.cb_fp16.setChecked(config.get("fp16_enabled", False))
            
            # 加载代理设置
            if "proxy_url" in config:
                self.proxy_input.setText(config["proxy_url"])
            
            # 加载 pip 镜像源
            pip_source = config.get("pip_source_index", 4)
            btn_pip = self.pip_btn_group.button(pip_source)
            if btn_pip: btn_pip.setChecked(True)
        
        # 预先加载环境信息
        self.get_env_info()

    def install_whl(self, whl_path, dlg=None):
        """安装 whl 包，支持实时日志输出"""
        env = self.get_env_info()
        if not env:
            if dlg: dlg.append_log("❌ 错误：请先设置 ComfyUI 路径")
            else: QMessageBox.warning(self, "错误", "请先设置 ComfyUI 路径")
            return

        py_exe = env["py_exe"]
        use_uv = self.uv_switch.isChecked()

        if use_uv:
            cmd = [py_exe, "-m", "uv", "pip", "install", whl_path, "--system"]
            desc = "UV 安装"
        else:
            cmd = [py_exe, "-m", "pip", "install", whl_path]
            desc = "Pip 安装"

        # 记录安装日志
        self.write_app_log("INSTALL_WHL", {
            "path": whl_path,
            "method": desc,
            "command": " ".join(cmd),
            "proxy": self.proxy_input.text().strip() or "None"
        })

        if dlg:
            dlg.label.setText(f"📦 正在通过 {desc}...")
            worker = ProcessWorker(cmd, desc=desc, env=self.get_proxy_env())
            dlg.worker = worker
            worker.log.connect(dlg.append_log)
            
            # 这里需要处理 finished 信号以允许后续操作
            # 但因为是在对话框内，我们通常等待它完成
            worker.start()
            return worker
        else:
            # 如果没有对话框，则创建一个
            new_dlg = ProcessLogDialog(self, title="安装依赖")
            worker = ProcessWorker(cmd, desc=desc, env=self.get_proxy_env())
            new_dlg.worker = worker
            worker.log.connect(new_dlg.append_log)
            worker.finished.connect(lambda ok: new_dlg.show_close_btn())
            worker.start()
            new_dlg.exec()
            return None

    def start_download(self, idx):
        if idx == 1:
            cat = "using_mod"
            mod_combo = self.cb_mod1
            ver_combo = self.cb_ver1
        else:
            cat = "lighting_mod"
            mod_combo = self.cb_mod2
            ver_combo = self.cb_ver2

        mod_name = mod_combo.currentText().strip()
        display_name = ver_combo.currentText()

        if not mod_name or "选择需下载" in mod_name:
            QMessageBox.warning(self, "提示", "请选择模块")
            return
            
        if not display_name or "正在获取" in display_name or "未找到" in display_name or "获取失败" in display_name:
            QMessageBox.warning(self, "提示", "请选择有效的版本")
            return

        mod_info = self.dl_data[cat][mod_name]
        
        # 1. 判断是 GitHub 模式还是本地 JSON 模式
        url = ""
        filename = ""
        
        if "githubName" in mod_info:
            # GitHub 模式：从下拉框的 userData 获取
            asset_data = ver_combo.currentData()
            if not asset_data:
                QMessageBox.warning(self, "错误", "无法获取下载数据，请尝试重新获取更新。")
                return
            url = asset_data["download_url"]
            filename = asset_data["filename"]
        else:
            # 本地模式
            ver_key = display_name
            url = mod_info[ver_key]
            
            # 兼容旧逻辑的 URL 替换
            env_data = self.get_env_info()
            if not env_data:
                QMessageBox.warning(self, "环境不支持", "请先配置 ComfyUI 路径")
                return
            
            cp = env_data["cp"]
            cuda = env_data["cuda"]
            torchv = env_data["torch"]
            mod_type = mod_info.get("mod")
            tips = mod_info.get("tips")

            if mod_type == "replace":
                url = url.replace("[cp_version]", cp).replace("[cuda_version]", cuda).strip()
            elif mod_type == "index" and isinstance(url, list):
                matched = [u for u in url if cuda in u and (torchv >= "2.9.0" if "torch2.9" in u else True)]
                if not matched:
                    QMessageBox.warning(self, "不支持", tips)
                    return
                url = matched[-1]
            
            filename = url.split("/")[-1]

        # 启动下载逻辑
        cache_path = self.get_cache_path()
        whl_full_path = os.path.abspath(os.path.join(cache_path, filename))

        if os.path.exists(whl_full_path):
            reply = QMessageBox.question(
                self, "文件已存在",
                f"缓存已存在：\n{filename}\n\n是否跳过下载，直接安装？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.install_whl(whl_full_path)
                return

        aria2 = "ComfyUI_Meme_Starter/tools/aria2c.exe"
        if not os.path.exists(aria2):
            QMessageBox.critical(self, "错误", "aria2c.exe 不存在，请检查工具目录！")
            return

        dlg = ProcessLogDialog(self, title="下载并安装")
        dlg.label.setText("⏬ 正在下载模块...")

        cmd = [
            aria2,
            "--max-download-limit=0",
            "--continue=true",
            f"--out={whl_full_path}",
            url
        ]
        
        # 使用代理（如果配置了）
        proxy_env = self.get_proxy_env()

        worker = ProcessWorker(cmd, desc=f"下载 {filename}", env=proxy_env)
        dlg.worker = worker
        worker.log.connect(dlg.append_log)

        # 记录下载日志
        self.write_app_log("DOWNLOAD_START", {
            "filename": filename,
            "url": url,
            "command": " ".join(cmd),
            "proxy": self.proxy_input.text().strip() or "None"
        })

        def on_download_finished(success):
            if success:
                dlg.label.setText("✅ 下载完成，准备安装...")
                install_worker = self.install_whl(whl_full_path, dlg)
                if install_worker:
                    install_worker.finished.connect(lambda ok: dlg.show_close_btn())
            else:
                dlg.label.setText("❌ 下载失败")
                dlg.show_close_btn()

        worker.finished.connect(on_download_finished)
        worker.start()
        dlg.exec()

    def get_cache_path(self):
        # 获取输入框路径
        path = self.cache_path_input.text().strip()

        # 如果为空，使用默认相对路径
        if not path:
            path = "cache_meme_data/whl_pack"

        # 强制转成 相对路径 / 基础名称，避免重复叠加
        if os.path.isabs(path):
            path = os.path.basename(path)

        # 确保目录存在
        os.makedirs(path, exist_ok=True)
        return path

    def select_install_whl(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 whl 文件", "", "Python Wheel (*.whl)")
        if file_path:
            self.install_whl(file_path)

    def on_drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def on_drop_file(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.endswith(".whl"):
                self.install_whl(file_path)
            else:
                QMessageBox.warning(self, "格式错误", "仅支持 .whl 文件安装")

    def create_proxy_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("🌐 网络代理")
        title.setFont(QFont("微软雅黑", 18, QFont.Bold))
        title.setStyleSheet("color: #1e293b;")

        desc = QLabel("配置系统代理，用于加速 HuggingFace、Github、Pip 等插件和环境的下载。")
        desc.setFont(QFont("微软雅黑", 11))
        desc.setStyleSheet("color: #64748b;")

        # 分组
        group = QGroupBox("代理设置")
        group.setStyleSheet("QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 30, 16, 16)
        group_layout.setSpacing(15)

        # 输入框
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("例如: http://127.0.0.1:7890")
        self.proxy_input.setStyleSheet(self.input_style())
        group_layout.addWidget(QLabel("代理地址 (HTTP/HTTPS/ALL_PROXY):"))
        group_layout.addWidget(self.proxy_input)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_auto_proxy = QPushButton("🔍 自动获取")
        self.btn_auto_proxy.setFixedHeight(38)
        self.btn_auto_proxy.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 0 15px;
            }
            QPushButton:hover { background-color: #e5e7eb; }
        """)
        self.btn_auto_proxy.clicked.connect(self.auto_detect_proxy)

        self.btn_clear_proxy = QPushButton("🧹 清除代理")
        self.btn_clear_proxy.setFixedHeight(38)
        self.btn_clear_proxy.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 0 15px;
            }
            QPushButton:hover { background-color: #e5e7eb; }
        """)
        self.btn_clear_proxy.clicked.connect(self.clear_proxy)

        self.btn_save_proxy = QPushButton("✅ 即时生效代理")
        self.btn_save_proxy.setFixedHeight(38)
        self.btn_save_proxy.setStyleSheet("""
            QPushButton {
                background-color: #3a7bd5;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 0 20px;
            }
            QPushButton:hover { background-color: #2d6dc2; }
        """)
        self.btn_save_proxy.clicked.connect(self.save_config)

        btn_layout.addWidget(self.btn_auto_proxy)
        btn_layout.addWidget(self.btn_clear_proxy)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save_proxy)
        group_layout.addLayout(btn_layout)

        # 提示
        tip_label = QLabel("💡 提示：代理设置即时生效，无需重启启动器。已运行的 ComfyUI 需重启后生效。")
        tip_label.setStyleSheet("color:#64748b; font-size:11px;")
        group_layout.addWidget(tip_label)

        # ====================== Python 镜像源设置 ======================
        pip_group = QGroupBox("Python 镜像源设置 (pip 换源)")
        pip_group.setStyleSheet("QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}")
        pip_layout = QVBoxLayout(pip_group)
        pip_layout.setContentsMargins(16, 30, 16, 16)
        pip_layout.setSpacing(12)

        pip_tip = QLabel("提示：切换国内镜像源可以大幅提升插件依赖的安装速度。")
        pip_tip.setStyleSheet("color:#64748b; font-size:11px;")
        pip_layout.addWidget(pip_tip)

        pip_grid = QGridLayout()
        self.pip_btn_group = QButtonGroup(self)

        self.rb_aliyun = QRadioButton("阿里云 (最快最稳)")
        self.rb_tsinghua = QRadioButton("清华大学 (常用)")
        self.rb_official = QRadioButton("官方源 (pypi.org)")
        self.rb_unset = QRadioButton("恢复默认 (清除配置)")
        self.rb_no_change = QRadioButton("保持当前设置")
        self.rb_no_change.setChecked(True)

        self.pip_btn_group.addButton(self.rb_aliyun, 0)
        self.pip_btn_group.addButton(self.rb_tsinghua, 1)
        self.pip_btn_group.addButton(self.rb_official, 2)
        self.pip_btn_group.addButton(self.rb_unset, 3)
        self.pip_btn_group.addButton(self.rb_no_change, 4)

        pip_grid.addWidget(self.rb_aliyun, 0, 0)
        pip_grid.addWidget(self.rb_tsinghua, 0, 1)
        pip_grid.addWidget(self.rb_official, 1, 0)
        pip_grid.addWidget(self.rb_unset, 1, 1)
        pip_grid.addWidget(self.rb_no_change, 2, 0)
        pip_layout.addLayout(pip_grid)

        self.btn_apply_pip = QPushButton("🚀 立即应用镜像源")
        self.btn_apply_pip.setFixedHeight(38)
        self.btn_apply_pip.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #16a34a; }
        """)
        self.btn_apply_pip.clicked.connect(self.apply_pip_source)
        pip_layout.addWidget(self.btn_apply_pip)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(group)
        layout.addWidget(pip_group)
        layout.addStretch()

        return page

    def apply_pip_source(self):
        env = self.get_env_info()
        if not env:
            QMessageBox.warning(self, "环境错误", "请先配置 ComfyUI 路径！")
            return

        py_exe = env["py_exe"]
        checked_id = self.pip_btn_group.checkedId()
        
        cmd = []
        desc = ""
        
        if checked_id == 0: # 阿里云
            cmd = [py_exe, "-m", "pip", "config", "set", "global.index-url", "https://mirrors.aliyun.com/pypi/simple/"]
            desc = "切换为阿里云镜像源"
        elif checked_id == 1: # 清华
            cmd = [py_exe, "-m", "pip", "config", "set", "global.index-url", "https://pypi.tuna.tsinghua.edu.cn/simple/"]
            desc = "切换为清华大学镜像源"
        elif checked_id == 2: # 官方
            cmd = [py_exe, "-m", "pip", "config", "set", "global.index-url", "https://pypi.org/simple"]
            desc = "恢复为官方源"
        elif checked_id == 3: # 清除
            cmd = [py_exe, "-m", "pip", "config", "unset", "global.index-url"]
            desc = "清除 pip 源配置"
        else:
            return

        # 执行命令
        dlg = ProcessLogDialog(self, title="应用镜像源")
        worker = ProcessWorker(cmd, desc=desc, env=self.get_proxy_env())
        dlg.worker = worker
        worker.log.connect(dlg.append_log)
        worker.finished.connect(lambda ok: dlg.show_close_btn())
        worker.start()
        dlg.exec()

    def auto_detect_proxy(self):
        try:
            # 尝试在 Windows 环境下获取环境变量中的代理
            # 使用 shell=True 因为 set 是 cmd 内置命令
            out = subprocess.check_output('set | findstr /i "proxy"', shell=True, text=True, encoding='gbk', errors='ignore')
            for line in out.split('\n'):
                if 'ALL_PROXY=' in line or 'HTTP_PROXY=' in line or 'HTTPS_PROXY=' in line:
                    proxy = line.split('=', 1)[1].strip()
                    if proxy:
                        self.proxy_input.setText(proxy)
                        return
            QMessageBox.information(self, "获取代理", "未检测到系统环境变量代理，请手动输入。")
        except:
            # 备选方案：尝试从注册表或常规路径获取（这里简化为提示手动输入）
            QMessageBox.information(self, "获取代理", "自动获取失败，请手动输入代理地址。")

    def clear_proxy(self):
        self.proxy_input.clear()

    def create_offline_install_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("📦 离线安装")
        title.setFont(QFont("微软雅黑", 18, QFont.Bold))
        title.setStyleSheet("color: #1e293b;")

        desc = QLabel("用于离线安装已经提前下载好的 whl 包，支持拖拽文件到窗口。")
        desc.setFont(QFont("微软雅黑", 11))
        desc.setStyleSheet("color: #64748b;")

        # ====================== 离线安装区域 ======================
        offline_group = QGroupBox("安装已有的 whl 包")
        offline_group.setStyleSheet("""
            QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}
        """)
        offline_layout = QVBoxLayout(offline_group)
        offline_layout.setContentsMargins(16, 30, 16, 16)
        offline_layout.setSpacing(12)

        offline_tip = QLabel("提示：请确保选择的文件是与当前 Python 环境匹配的 .whl 安装包")
        offline_tip.setStyleSheet("color:#64748b; font-size:11px;")
        offline_layout.addWidget(offline_tip)

        # 拖拽文件接收区域
        self.drop_label = QLabel("📥 请将 whl 文件拖拽至此进行安装")
        self.drop_label.setAcceptDrops(True)
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setMinimumHeight(150) # 独立页面，高度可以给足
        self.drop_label.setFrameShape(QFrame.StyledPanel)
        self.drop_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #d1d5db;
                border-radius: 8px;
                background-color: #f9fafb;
                color: #6b7280;
                font-family: 微软雅黑;
                font-size: 14px;
            }
            QLabel:hover {
                border-color: #3b82f6;
                background-color: #eff6ff;
            }
        """)
        
        # 覆写拖拽事件
        self.drop_label.dragEnterEvent = self.on_drag_enter
        self.drop_label.dropEvent = self.on_drop_file
        offline_layout.addWidget(self.drop_label)

        # 选择 WHL 文件按钮
        self.btn_select_whl = QPushButton("📂 选择本地 whl 文件进行安装")
        self.btn_select_whl.setFixedHeight(45)
        self.btn_select_whl.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        self.btn_select_whl.clicked.connect(self.select_install_whl)
        offline_layout.addWidget(self.btn_select_whl)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(offline_group)
        layout.addStretch()

        return page

    def create_download_page(self):

        # 让 ComboBox 自动拉伸填充，不被压缩
        combo_stretch_style = """
            QComboBox{
                min-width:220px;  /* 保证下拉框不会太短 */
            }
        """

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("📥 下载功能")
        title.setFont(QFont("微软雅黑", 18, QFont.Bold))
        title.setStyleSheet("color: #1e293b;")

        desc = QLabel("常用依赖包的预制轮子下载，比如工具依赖，加速依赖等，指定安装，更高效、快速、安全。")
        desc.setFont(QFont("微软雅黑", 11))
        desc.setStyleSheet("color: #64748b;")

        # 分组1
        group1 = QGroupBox("常用模块下载")
        group1.setStyleSheet("""
            QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}
        """)
        form1 = QFormLayout(group1)
        form1.setContentsMargins(16, 30, 16, 16)


        self.cb_mod1 = QComboBox()
        self.cb_ver1 = QComboBox()
        self.btn_update1 = QPushButton("获取更新")
        self.btn_download1 = QPushButton("下载")

        self.cb_mod1.setStyleSheet(self.combo_style())
        self.cb_ver1.setStyleSheet(self.combo_style() + combo_stretch_style)
        self.cb_ver1.setEnabled(False)

        # 按钮样式
        self.btn_update1.setStyleSheet("""
            QPushButton{background:#10b981; color:white; border-radius:8px; padding:8px 12px; font-size:12px;}
            QPushButton:hover{background:#059669;}
        """)
        self.btn_download1.setStyleSheet("""
            QPushButton{background:#3b82f6; color:white; border-radius:8px; padding:8px 16px;}
            QPushButton:hover{background:#2563eb;}
        """)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("模块："))
        row1.addWidget(self.cb_mod1)
        row1.addWidget(self.btn_update1)
        row1.addWidget(QLabel("版本："))
        row1.addWidget(self.cb_ver1)
        row1.addWidget(self.btn_download1)
        form1.addRow(row1)

        # 分组2
        group2 = QGroupBox("加速模块下载")
        group2.setStyleSheet("""
            QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}
        """)
        form2 = QFormLayout(group2)
        form2.setContentsMargins(16, 30, 16, 16)

        self.cb_mod2 = QComboBox()
        self.cb_ver2 = QComboBox()
        self.btn_update2 = QPushButton("获取更新")
        self.btn_download2 = QPushButton("下载")

        self.cb_mod2.setStyleSheet(self.combo_style())
        self.cb_ver2.setStyleSheet(self.combo_style())
        self.cb_ver2.setEnabled(False)

        self.btn_update2.setStyleSheet("""
            QPushButton{background:#10b981; color:white; border-radius:8px; padding:8px 12px; font-size:12px;}
            QPushButton:hover{background:#059669;}
        """)
        self.btn_download2.setStyleSheet("""
            QPushButton{background:#3b82f6; color:white; border-radius:8px; padding:8px 16px;}
            QPushButton:hover{background:#2563eb;}
        """)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("模块："))
        row2.addWidget(self.cb_mod2)
        row2.addWidget(self.btn_update2)
        row2.addWidget(QLabel("版本："))
        row2.addWidget(self.cb_ver2)
        row2.addWidget(self.btn_download2)
        form2.addRow(row2)

        layout.addWidget(title)
        layout.addWidget(desc)

        layout.addWidget(group1)
        layout.addWidget(group2)

        # ====================== 下载缓存路径 ======================
        cache_group = QGroupBox("下载缓存路径")
        cache_group.setStyleSheet("""
            QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}
        """)
        cache_layout = QHBoxLayout(cache_group)
        cache_layout.setContentsMargins(16, 30, 16, 16)
        cache_layout.setSpacing(10)

        # 缓存路径输入框
        self.cache_path_input = QLineEdit()
        self.cache_path_input.setPlaceholderText("默认缓存到 ./cache_meme_data/whl_pack")
        self.cache_path_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 14px;
                border-radius: 8px;
                border: 1px solid #d1d5db;
                background-color: white;
                font-size: 13px;
            }
        """)

        # 选择文件夹按钮
        self.btn_select_cache = QPushButton("选择文件夹")
        self.btn_select_cache.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border-radius: 8px;
                padding: 10px 16px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)

        cache_layout.addWidget(self.cache_path_input)
        cache_layout.addWidget(self.btn_select_cache)
        layout.addWidget(cache_group)
        # ========================================================

        layout.addStretch()

        # 加载JSON
        self.load_download_list()

        # 下拉联动
        # 用activated（用户手动选择才触发，更稳定）
        self.cb_mod1.activated.connect(lambda: self.on_mod_select(1))
        self.cb_mod2.activated.connect(lambda: self.on_mod_select(2))

        # 下载
        self.btn_download1.clicked.connect(lambda: self.start_download(1))
        self.btn_download2.clicked.connect(lambda: self.start_download(2))

        # 获取更新
        self.btn_update1.clicked.connect(lambda: self.on_get_update(1))
        self.btn_update2.clicked.connect(lambda: self.on_get_update(2))

        self.btn_select_cache.clicked.connect(self.select_cache_folder)

        # 默认选中提示文字
        self.cb_mod1.setCurrentIndex(0)
        self.cb_mod2.setCurrentIndex(0)



        return page

    def select_cache_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择下载缓存路径")
        if folder:
            self.cache_path_input.setText(folder)

    def combo_style(self):
        return """
            QComboBox{
                padding:8px 12px; border-radius:8px;
                border:1px solid #d1d5db; background:white;
            }
            QComboBox::drop-down{border:none;}
        """

    def load_download_list(self):
        json_path = "ComfyUI_Meme_Starter/downloadList.json"
        if not os.path.exists(json_path):
            QMessageBox.warning(self, "缺失文件", f"未找到：{json_path}")
            self.dl_data = {}
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                self.dl_data = json.load(f)
            self.github_release_data = {} # 存储获取到的 GitHub Release 信息
        except Exception as e:
            QMessageBox.critical(self, "JSON错误", str(e))
            self.dl_data = {}
            return

        # 调试打印（看是否读到数据）
        print("=== 下载配置加载成功 ===")
        print("using_mod:", list(self.dl_data.get("using_mod", {}).keys()))
        print("lighting_mod:", list(self.dl_data.get("lighting_mod", {}).keys()))

        # 先添加默认提示文字
        self.cb_mod1.addItem("选择需下载的模块")
        self.cb_mod2.addItem("选择需下载的模块")

        # 再加载真实模块列表
        self.cb_mod1.addItems(self.dl_data.get("using_mod", {}).keys())
        self.cb_mod2.addItems(self.dl_data.get("lighting_mod", {}).keys())

    def on_mod_select(self, idx):
        """选择模块时，清空版本列表。如果是普通模块，加载JSON版本；如果是GitHub模块，等待用户点击获取更新。"""
        if idx == 1:
            cat_key = "using_mod"
            mod_combo = self.cb_mod1
            ver_combo = self.cb_ver1
        else:
            cat_key = "lighting_mod"
            mod_combo = self.cb_mod2
            ver_combo = self.cb_ver2

        ver_combo.clear()
        ver_combo.setEnabled(False)
        
        mod_name = mod_combo.currentText().strip()
        if mod_name == "选择需下载的模块" or not mod_name:
            return

        mod_info = self.dl_data.get(cat_key, {}).get(mod_name, {})
        
        # 如果是传统的 JSON 版本列表模式
        if "githubName" not in mod_info:
            versions = [key for key in mod_info if key not in ("mod", "tips")]
            if versions:
                ver_combo.addItems(versions)
                ver_combo.setEnabled(True)

    def on_get_update(self, idx):
        """点击获取更新，从 GitHub 拉取最新的 whl 列表"""
        if idx == 1:
            cat_key = "using_mod"
            mod_combo = self.cb_mod1
            ver_combo = self.cb_ver1
        else:
            cat_key = "lighting_mod"
            mod_combo = self.cb_mod2
            ver_combo = self.cb_ver2

        mod_name = mod_combo.currentText().strip()
        if mod_name == "选择需下载的模块" or not mod_name:
            QMessageBox.warning(self, "提示", "请先选择一个模块")
            return

        mod_info = self.dl_data.get(cat_key, {}).get(mod_name, {})
        repo = mod_info.get("githubName")
        
        if not repo:
            QMessageBox.information(self, "提示", "该模块不通过 GitHub 获取更新，已直接加载本地版本。")
            return

        # 获取环境信息
        env = self.get_env_info()
        if not env:
            QMessageBox.warning(self, "错误", "未能获取到环境信息，请先设置 ComfyUI 路径")
            return
            
        cuda_ver = env["cuda_short"] # 如 128
        python_ver = env["cp"] # 如 cp312
        proxy = self.proxy_input.text().strip() or None

        # 启动获取更新线程
        ver_combo.clear()
        ver_combo.addItem("🔄 正在获取 GitHub 更新...")
        ver_combo.setEnabled(False)

        worker = ReleaseWorker(repo, platform_key="win", cuda_ver=f"cu{cuda_ver}", python_ver=python_ver, proxy=proxy)
        
        def on_success(whl_list):
            ver_combo.clear()
            if not whl_list:
                ver_combo.addItem("❌ 未找到匹配当前环境的 whl")
                return
            
            # 存储结果，用于下载
            self.github_release_data[mod_name] = whl_list
            
            # 显示文件名到下拉框
            for item in whl_list:
                display_text = f"{item['filename']} ({item['size_mb']} MB)"
                ver_combo.addItem(display_text, item) # 存储数据对象
            
            ver_combo.setEnabled(True)
            QMessageBox.information(self, "成功", f"成功获取到 {len(whl_list)} 个可用版本")

        def on_error(msg):
            ver_combo.clear()
            ver_combo.addItem("❌ 获取失败")
            QMessageBox.critical(self, "获取更新失败", msg)

        worker.finished.connect(on_success)
        worker.error.connect(on_error)
        worker.start()
        # 保持引用防止被垃圾回收
        self._current_release_worker = worker

    def get_env_info(self, force_refresh=False):
        """统一获取并缓存环境信息：Python, CUDA, Torch, Driver"""
        if hasattr(self, "_env_info_cache") and not force_refresh:
            return self._env_info_cache

        config = self.load_config()
        if not config:
            return None

        root = config["comfyui_root"]
        # 使用统一校验逻辑
        ok, _ = self.is_valid_comfy_root(root)
        if not ok:
            return None

        py_exe = os.path.join(root, "python_embeded", "python.exe")

        # 1. Python 版本 (cpXX)
        py_detail = "未知"
        cp = "cp312"
        try:
            py_detail = subprocess.check_output([py_exe, "--version"], text=True).strip()
            v = py_detail.split()[1]
            mj, mn = v.split(".")[:2]
            cp = f"cp{mj}{mn}"
        except:
            pass

        # 2. CUDA & Driver 版本
        cuda_display = "未知"
        cuda_short = "未知"
        driver_ver = "未获取"
        cuda_max = "未获取"
        try:
            smi = subprocess.check_output(["nvidia-smi"], text=True, encoding="utf-8", errors="ignore")
            for line in smi.split("\n"):
                if "Driver Version:" in line:
                    parts = line.split("Driver Version:")
                    if len(parts) > 1:
                        driver_ver = parts[1].split()[0].strip()
                    parts = line.split("CUDA Version:")
                    if len(parts) > 1:
                        cuda_max = parts[1].strip().split("|")[0].strip()
                    break
        except:
            pass

        try:
            # 优先从 nvcc 获取
            out = subprocess.check_output(["nvcc", "--version"], text=True, encoding="utf-8", errors="ignore")
            for line in out.split("\n"):
                if "release" in line:
                    # 12.8
                    cuda_display = line.split("release")[1].strip().split(",")[0].strip()
                    # 128
                    cuda_short = cuda_display.replace(".", "")
                    break
        except:
            # 备选：从 torch 获取
            try:
                code = "import torch; print(torch.version.cuda)"
                out = subprocess.check_output([py_exe, "-c", code], text=True, errors="ignore").strip()
                if out and "." in out:
                    cuda_display = out
                    cuda_short = out.replace(".", "")
            except:
                pass
        
        # 如果还是没获取到，但 nvidia-smi 里的最高支持获取到了，可以做个参考
        if cuda_display == "未知" and cuda_max != "未获取":
            cuda_display = f"{cuda_max} (支持)"

        cuda_full = f"cu{cuda_short}" if cuda_short != "未知" else "未知"

        # 3. Torch & Transformers 版本
        torch_ver = "未找到"
        trans_ver = "未找到"
        site = os.path.join(root, "python_embeded", "Lib", "site-packages")
        if os.path.exists(site):
            for n in os.listdir(site):
                if n.startswith("torch-") and ".dist-info" in n:
                    torch_ver = n.replace(".dist-info", "")
                if n.startswith("transformers-") and ".dist-info" in n:
                    trans_ver = n.replace(".dist-info", "")

        # 4. ComfyUI 版本
        comfy_ver = "未知"
        toml_path = os.path.join(root, "ComfyUI", "pyproject.toml")
        if os.path.exists(toml_path):
            try:
                with open(toml_path, "r", encoding="utf-8") as f:
                    data = tomllib.loads(f.read())
                    comfy_ver = data.get("project", {}).get("version", "未知")
            except:
                pass

        self._env_info_cache = {
            "cp": cp,
            "cuda": cuda_full,
            "cuda_short": cuda_short,
            "cuda_display": cuda_display,
            "cuda_max": cuda_max,
            "driver": driver_ver,
            "torch": torch_ver,
            "transformers": trans_ver,
            "py_exe": py_exe,
            "py_detail": py_detail,
            "root": root,
            "comfy_ver": comfy_ver
        }
        return self._env_info_cache

    def check_environment(self, mod_info):
        env = self.get_env_info()
        if not env:
            return False, "请先配置 ComfyUI 路径"
        
        print(f"✅ 环境检测：Python={env['cp']}, CUDA={env['cuda']}, Torch={env['torch']}")
        return True, (env['cp'], env['cuda'], env['torch'])

    # 保存进程对象
    comfy_process = None

    def is_valid_comfy_root(self, root):
        """通用路径校验逻辑"""
        if not root:
            return False, "请先配置 ComfyUI 根目录！"
        
        python_exe = os.path.join(root, "python_embeded", "python.exe")
        main_py = os.path.join(root, "ComfyUI", "main.py")

        if not os.path.exists(python_exe) or not os.path.exists(main_py):
            return False, "ComfyUI 目录不正确，\n没有检测到相关环境 (python_embeded 或 ComfyUI/main.py)，\n\n请重新设置！"
        
        return True, ""

    def get_proxy_env(self):
        """获取代理环境变量"""
        proxy = self.proxy_input.text().strip()
        if not proxy:
            return None
        
        env = os.environ.copy()
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["ALL_PROXY"] = proxy
        # Git 专用代理配置（可选，通常环境变量已足够）
        return env

    def start_comfyui(self):
        config = self.load_config()
        if not config:
            QMessageBox.warning(self, "提示", "请先配置 ComfyUI 路径！")
            return

        root = config["comfyui_root"]
        ok, msg = self.is_valid_comfy_root(root)
        if not ok:
            QMessageBox.critical(self, "错误", msg)
            return

        python_exe = os.path.join(root, "python_embeded", "python.exe")
        main_py = os.path.join(root, "ComfyUI", "main.py")

        # 基础启动命令
        cmd = [python_exe, "-s", main_py, "--windows-standalone-build"]

        # 添加高级选项参数
        if self.online_switch.isChecked():
            ip = self.online_ip_input.text().strip() or "0.0.0.0"
            port = self.online_port_input.text().strip() or "8000"
            cmd.extend(["--listen", ip, "--port", port])

        # 硬件模式 (互斥)
        if self.rb_cpu.isChecked():
            cmd.append("--cpu")
        elif self.rb_normal.isChecked():
            cmd.append("--normalvram")
        elif self.rb_low.isChecked():
            cmd.append("--lowvram")
        elif self.rb_high.isChecked():
            cmd.append("--highvram")
        
        # 追加硬件模式
        if self.cb_smart_mem.isChecked():
            cmd.append("--disable-smart-memory")
            
        # 加速优化模式
        if self.cb_fp16.isChecked():
            cmd.extend(["--fast", "fp16_accumulation"])

        # 启动进程
        env = self.get_proxy_env()
        
        # 记录启动日志
        self.write_app_log("START_COMFYUI", {
            "command": " ".join(cmd),
            "cwd": root,
            "proxy": self.proxy_input.text().strip() or "None",
            "env_vars": {k: v for k, v in env.items() if "PROXY" in k} if env else "None"
        })
        
        self.comfy_process = subprocess.Popen(cmd, cwd=root, env=env)

        self.start_btn.setText("▶ 运行中...")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #9333ea;
                color: white;
                border-radius: 12px;
            }
        """)

        self.update_button_states()

    def stop_comfyui(self):
        if self.comfy_process:
            self.comfy_process.terminate()
            self.comfy_process = None

        self.start_btn.setText("▶ 启动 ComfyUI")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                color: white;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #16a34a;
            }
        """)
        self.update_button_states()

    def create_page(self, title, desc):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        t = QLabel(title)
        t.setFont(QFont("微软雅黑", 24, QFont.Bold))
        t.setStyleSheet("color:#1e293b")
        d = QLabel(desc)
        d.setFont(QFont("微软雅黑", 12))
        d.setStyleSheet("color:#64748b; margin-top:10px")
        lay.addWidget(t)
        lay.addWidget(d)
        return w

    def create_advanced_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("⚙️ 高级选项")
        title.setFont(QFont("微软雅黑", 18, QFont.Bold))
        title.setStyleSheet("color: #1e293b;")

        # 红色警告 Tips
        warning_tip = QLabel("⚠️ 红色提示：如果你不知道以下显存和量化参数的含义，请不要修改它们，保持默认即可。")
        warning_tip.setWordWrap(True)
        warning_tip.setStyleSheet("""
            QLabel {
                color: #ef4444;
                background-color: #fee2e2;
                border: 1px solid #fecaca;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
                font-size: 13px;
            }
        """)

        # ====================== 硬件模式设置 (单选) ======================
        hw_group = QGroupBox("硬件模式 (显存与运行环境)")
        hw_group.setStyleSheet("QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}")
        hw_layout = QVBoxLayout(hw_group)
        hw_layout.setContentsMargins(16, 30, 16, 16)
        hw_layout.setSpacing(10)

        hw_grid = QGridLayout()
        self.hw_btn_group = QButtonGroup(self)

        self.rb_cpu = QRadioButton("仅 CPU 启动 (--cpu)")
        self.rb_normal = QRadioButton("默认显存 (--normalvram)")
        self.rb_low = QRadioButton("低显存模式 (--lowvram)")
        self.rb_high = QRadioButton("高显存模式 (--highvram)")
        self.rb_none = QRadioButton("不添加显存参数 (系统自动)")
        self.rb_none.setChecked(True)

        self.hw_btn_group.addButton(self.rb_cpu, 0)
        self.hw_btn_group.addButton(self.rb_normal, 1)
        self.hw_btn_group.addButton(self.rb_low, 2)
        self.hw_btn_group.addButton(self.rb_high, 3)
        self.hw_btn_group.addButton(self.rb_none, 4)

        hw_grid.addWidget(self.rb_cpu, 0, 0)
        hw_grid.addWidget(self.rb_normal, 0, 1)
        hw_grid.addWidget(self.rb_low, 1, 0)
        hw_grid.addWidget(self.rb_high, 1, 1)
        hw_grid.addWidget(self.rb_none, 2, 0)
        hw_layout.addLayout(hw_grid)

        # 追加硬件模式
        self.cb_smart_mem = QCheckBox("禁用智能显存管理 (--disable-smart-memory)")
        hw_layout.addWidget(self.cb_smart_mem)

        # ====================== 加速优化模式 ======================
        opt_group = QGroupBox("加速优化模式 (可能降低质量)")
        opt_group.setStyleSheet("QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}")
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setContentsMargins(16, 30, 16, 16)

        self.cb_fp16 = QCheckBox("启用 fp16 加速 (--fast fp16_accumulation)")
        opt_layout.addWidget(self.cb_fp16)

        # ====================== 安装设置 ======================
        install_group = QGroupBox("安装增强")
        install_group.setStyleSheet("QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}")
        install_layout = QVBoxLayout(install_group)
        install_layout.setContentsMargins(16, 30, 16, 16)
        
        uv_row = QHBoxLayout()
        self.uv_label = QLabel("启用 UV 安装模式：")
        self.uv_switch = QCheckBox(" ")
        self.uv_switch.setChecked(True)
        uv_row.addWidget(self.uv_label)
        uv_row.addWidget(self.uv_switch)
        uv_row.addStretch()
        install_layout.addLayout(uv_row)

        uv_tip = QLabel("提示：使用 UV 安装依赖，速度比 pip 快 5~10 倍")
        uv_tip.setStyleSheet("color:#64748b; font-size:11px;")
        install_layout.addWidget(uv_tip)

        # ====================== 联机模式设置 ======================
        online_group = QGroupBox("联机模式 (启动参数扩展)")
        online_group.setStyleSheet("QGroupBox{font-size:14px; font-weight:bold; margin-top:8px;}")
        online_layout = QVBoxLayout(online_group)
        online_layout.setContentsMargins(16, 30, 16, 16)
        online_layout.setSpacing(12)

        # 联机勾选
        self.online_switch = QCheckBox("启用联机模式 (--listen)")
        self.online_switch.setFont(QFont("微软雅黑", 10, QFont.Bold))
        online_layout.addWidget(self.online_switch)

        online_tip = QLabel("提示：广播到局域网或者广域网，在相同网络下供给其他设备或者多人使用")
        online_tip.setStyleSheet("color:#64748b; font-size:11px;")
        online_layout.addWidget(online_tip)

        # IP 和 端口输入
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        
        self.online_ip_input = QLineEdit()
        self.online_ip_input.setPlaceholderText("默认: 0.0.0.0")
        self.online_ip_input.setText("0.0.0.0")
        self.online_ip_input.setStyleSheet(self.input_style())
        
        self.online_port_input = QLineEdit()
        self.online_port_input.setPlaceholderText("默认: 8000")
        self.online_port_input.setText("8000")
        self.online_port_input.setStyleSheet(self.input_style())

        form.addRow("绑定 IP 地址：", self.online_ip_input)
        form.addRow("绑定端口号：", self.online_port_input)
        online_layout.addLayout(form)

        layout.addWidget(title)
        layout.addWidget(warning_tip)
        layout.addWidget(hw_group)
        layout.addWidget(opt_group)
        layout.addWidget(install_group)
        layout.addWidget(online_group)

        # 保存按钮
        self.btn_save_advanced = QPushButton("💾 保存高级设置")
        self.btn_save_advanced.setFixedHeight(45)
        self.btn_save_advanced.setStyleSheet("""
            QPushButton {
                background-color: #3a7bd5;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2d6dc2;
            }
        """)
        self.btn_save_advanced.clicked.connect(self.save_config)
        layout.addWidget(self.btn_save_advanced)

        layout.addStretch()

        return page

    def input_style(self):
        return """
            QLineEdit {
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid #d1d5db;
                background-color: white;
            }
        """

    def refresh_start_info(self, force=False):
        env = self.get_env_info(force_refresh=force)
        if not env:
            self.set_card_text(self.env_card, "未配置 ComfyUI 路径", "请前往环境配置", "")
            self.set_card_text(self.version_card, "未配置", "", "")
            self.set_card_text(self.libs_card, "未配置", "", "")
            return

        # 1. 环境信息
        self.set_card_text(self.env_card,
                           f"显卡驱动版本：{env['driver']}",
                           f"最高支持CUDA：{env['cuda_max']}",
                           f"系统已装CUDA：{env['cuda_display']}")

        # 2. 版本信息
        self.set_card_text(self.version_card,
                           f"ComfyUI：{env['comfy_ver']}",
                           f"{env['py_detail']}",
                           f"py简写代号: {env['cp']}")

        # 3. 核心库
        self.set_card_text(self.libs_card,
                           f"{env['torch']}",
                           f"{env['transformers']}",
                           "核心库正常")
    
    def create_start_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        # ========= 左侧：信息卡片区域 =========
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setAlignment(Qt.AlignTop)
        left_layout.setSpacing(16)

        title = QLabel("🚀 ComfyUI 启动中心")
        title.setFont(QFont("微软雅黑", 18, QFont.Bold))
        left_layout.addWidget(title)

        # 卡片行
        card_row = QHBoxLayout()
        card_row.setSpacing(14)

        self.env_card = self.create_info_card("📦 环境信息", "加载中...", "", "")
        self.version_card = self.create_info_card("📌 版本信息", "加载中...", "", "")
        self.libs_card = self.create_info_card("🔧 核心库", "加载中...", "", "")

        card_row.addWidget(self.env_card)
        card_row.addWidget(self.version_card)
        card_row.addWidget(self.libs_card)

        left_layout.addLayout(card_row)
        left_layout.addStretch()

        # ========= 右侧：按钮区域 =========
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setAlignment(Qt.AlignTop)
        right_layout.setContentsMargins(0, 52, 0, 0)
        right_layout.setSpacing(20)

        self.start_btn = QPushButton("▶ 启动 ComfyUI")
        self.stop_btn = QPushButton("⏹ 停止 ComfyUI")

        for btn in [self.start_btn, self.stop_btn]:
            btn.setFixedSize(220, 60)
            btn.setFont(QFont("微软雅黑", 14, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)

        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                color: white;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #16a34a;
            }
        """)

        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)

        right_layout.addWidget(self.start_btn)
        right_layout.addWidget(self.stop_btn)
        right_layout.addStretch()

        layout.addWidget(left_widget, 3)
        layout.addWidget(right_widget, 1)

        # 绑定
        self.start_btn.clicked.connect(self.start_comfyui)
        self.stop_btn.clicked.connect(self.stop_comfyui)

        # 启动时刷新信息
        self.refresh_start_info()
        self.update_button_states()  # 加在这里
        return page

    def update_button_states(self):
        if self.comfy_process and self.comfy_process.poll() is None:
            # 运行中
            self.start_btn.setText("▶ 运行中...")
            self.start_btn.setStyleSheet("""
                QPushButton { background-color: #9333ea; color: white; border-radius:12px; }
            """)
            self.start_btn.setEnabled(False)

            self.stop_btn.setText("⏹ 停止 ComfyUI")
            self.stop_btn.setStyleSheet("""
                QPushButton { background-color: #ef4444; color: white; border-radius:12px; }
                QPushButton:hover { background-color: #dc2626; }
            """)
            self.stop_btn.setEnabled(True)
        else:
            # 未运行
            self.start_btn.setText("▶ 启动 ComfyUI")
            self.start_btn.setStyleSheet("""
                QPushButton { background-color: #22c55e; color: white; border-radius:12px; }
                QPushButton:hover { background-color: #16a34a; }
            """)
            self.start_btn.setEnabled(True)

            self.stop_btn.setText("⏹ 未运行...")
            self.stop_btn.setStyleSheet("""
                QPushButton { background-color:#3b82f6; color:white; border-radius:12px; }
                QPushButton:disabled { background-color:#2563eb; color:white; }
            """)
            self.stop_btn.setEnabled(False)
    
    # ====================== 系统信息页面（现代化卡片 + 自动刷新） ======================
    def create_system_info_page(self):
        import psutil
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("🖥️ 系统硬件信息")
        title.setFont(QFont("微软雅黑", 18, QFont.Bold))
        title.setStyleSheet("color: #1e293b;" if not self.is_dark_mode else "color: white;")

        # 卡片容器
        self.card_container = QHBoxLayout()
        self.card_container.setSpacing(14)
        self.card_container.setContentsMargins(0, 8, 0, 0)

        # 创建卡片
        self.cpu_card = self.create_info_card("🧠 CPU 处理器", "", "", "")
        self.ram_card = self.create_info_card("💾 物理内存", "", "", "")
        self.gpu_card = self.create_info_card("🎨 GPU 显卡", "", "", "")

        self.card_container.addWidget(self.cpu_card)
        self.card_container.addWidget(self.ram_card)
        self.card_container.addWidget(self.gpu_card)

        layout.addWidget(title)
        layout.addLayout(self.card_container)
        layout.addStretch()

        # 每秒刷新
        from PySide6.QtCore import QTimer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.update_system_info)
        self.refresh_timer.start(1000)

        self.update_system_info()  # 立即刷新一次
        return page

    # 辅助：创建现代化信息卡片（整体缩小20%）
    def create_info_card(self, title, line1, line2, line3):
        card = QWidget()
        card.setMinimumWidth(220)
        card.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 11px;
                padding: 16px;
                border: 1px solid #e2e8f0;
            }
        """ if not self.is_dark_mode else """
            QWidget {
                background-color: #2d3748;
                border-radius: 11px;
                padding: 16px;
                border: 1px solid #4a5568;
            }
        """)

        lay = QVBoxLayout(card)
        lay.setSpacing(6)
        lay.setContentsMargins(18, 18, 18, 18)

        t = QLabel(title)
        t.setFont(QFont("微软雅黑", 12, QFont.Bold))
        t.setStyleSheet("color: #1e293b;" if not self.is_dark_mode else "color: white;")

        l1 = QLabel(line1)
        l2 = QLabel(line2)
        l3 = QLabel(line3)

        for lbl in [l1, l2, l3]:
            lbl.setFont(QFont("微软雅黑", 9))
            lbl.setStyleSheet("color: #475569;" if not self.is_dark_mode else "color: #cbd5e1;")

        lay.addWidget(t)
        lay.addWidget(l1)
        lay.addWidget(l2)
        lay.addWidget(l3)

        self.cpu_label = t
        self.ram_label = l1
        self.gpu_label = l2
        return card

    # 每秒更新信息
    def update_system_info(self):
        import psutil
        gpu_name = "核显 / 集成显卡"
        gpu_load = "0.0%"
        gpu_total = "共享内存"
        gpu_used = "动态分配"

        # 1. 尝试使用 GPUtil (需安装 pip install gputil)
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_name = gpu.name
                gpu_load = f"{gpu.load*100:.1f}%"
                gpu_total = f"{gpu.memoryTotal:.0f} MB"
                gpu_used = f"{gpu.memoryUsed:.0f} MB"
            else:
                raise Exception("GPUtil failed")
        except:
            # 2. 如果 GPUtil 失败，尝试直接调用 nvidia-smi (更通用)
            try:
                # 查询：名称, 占用率, 显存总量, 显存已用
                cmd = ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.total,memory.used", "--format=csv,noheader,nounits"]
                out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="ignore").strip()
                if out:
                    # 例如: NVIDIA GeForce RTX 4090, 10, 24564, 1200
                    parts = [p.strip() for p in out.split(",")]
                    if len(parts) >= 4:
                        gpu_name = parts[0]
                        gpu_load = f"{parts[1]}%"
                        gpu_total = f"{parts[2]} MB"
                        gpu_used = f"{parts[3]} MB"
            except:
                pass

        # ---------------- CPU ----------------
        cpu_model = self.get_cpu_model()
        cpu_usage = psutil.cpu_percent()
        cores = psutil.cpu_count(logical=True)

        # ---------------- RAM ----------------
        mem = psutil.virtual_memory()
        ram_total = f"{mem.total // (1024**3)} GB"
        ram_used = f"{mem.used // (1024**3)} GB"
        ram_avail = f"{mem.available // (1024**3)} GB"

        # 更新到UI
        self.set_card_text(self.cpu_card, f"CPU 占用：{cpu_usage}%", f"型号：{cpu_model}", f"核心：{cores}")
        self.set_card_text(self.ram_card, f"内存：{ram_used} / {ram_total}", f"占用：{mem.percent}%", f"可用：{ram_avail}")
        self.set_card_text(self.gpu_card, f"显卡：{gpu_name}", f"负载：{gpu_load}", f"显存：{gpu_used} / {gpu_total}")

    def set_card_text(self, card, title, l1, l2):
        items = card.findChildren(QLabel)
        if len(items) >= 4:
            items[1].setText(title)
            items[2].setText(l1)
            items[3].setText(l2)

    # 辅助：获取CPU型号（跨平台 增强版，绝不空白）
    def get_cpu_model(self):
        import platform
        try:
            # Windows 优先方案
            if platform.system() == "Windows":
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                    cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0]
                    return cpu_name.strip()
                except:
                    pass

                try:
                    return subprocess.check_output(
                        ["wmic", "cpu", "get", "name"], text=True, encoding="gbk"
                    ).strip().split("\n")[1].strip()
                except:
                    pass

            # Linux
            if platform.system() == "Linux":
                try:
                    with open("/proc/cpuinfo") as f:
                        for line in f:
                            if "model name" in line:
                                return line.split(":", 1)[1].strip()
                except:
                    pass

            # macOS
            if platform.system() == "Darwin":
                try:
                    return subprocess.check_output(
                        ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
                    ).strip()
                except:
                    pass

        except:
            pass

        # 最终兜底方案，绝对不会空白
        cpu_name = platform.processor()
        if not cpu_name or cpu_name == "":
            cpu_name = f"{platform.machine()} 处理器"
        return cpu_name

    # ====================== 优化后的设置页面 ======================
    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(18)  # 全局宽松间距

        # 标题
        title = QLabel("环境配置")
        title.setFont(QFont("微软雅黑", 20, QFont.Bold))
        title.setStyleSheet("color: #1e293b; margin-bottom: 10px")

        title2 = QLabel("基本的路径设置：比如项目本体，python路径，模型路径，git路径...")
        title2.setFont(QFont("微软雅黑", 14))
        title2.setStyleSheet("color: #00FF00; margin-bottom: 10px")

       # 分组
        group = QGroupBox("ComfyUI 环境配置")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                margin-top: 10px;
            }
        """)
        form = QFormLayout(group)
        form.setVerticalSpacing(10)       # 上下行间距
        form.setHorizontalSpacing(30)     # 标签 ↔ 输入框 横向间距
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setContentsMargins(20, 35, 20, 20)

        # 输入框 + 选择文件夹按钮
        self.comfyui_path_input = QLineEdit()
        self.comfyui_path_input.setPlaceholderText("请选择 ComfyUI 根文件夹路径")
        self.comfyui_path_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 16px;
                border-radius: 9px;
                border: 1px solid #d1d5db;
                background-color: white;
                font-size: 13px;
                color: #222;
            }
            QLineEdit:focus {
                border: 1px solid #3a7bd5;
                outline: none;
            }
        """)

        self.select_folder_btn = QPushButton("选择文件夹")
        self.select_folder_btn.setFixedHeight(38)
        self.select_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #e5e7eb;
            }
        """)

        # 保存按钮
        self.save_btn = QPushButton("💾 保存设置")
        self.save_btn.setFixedHeight(38)
        self.save_btn.setFixedWidth(100)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a7bd5;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2d6dc2;
            }
        """)

        # 行布局
        row_layout = QHBoxLayout()
        row_layout.setSpacing(10)
        row_layout.addWidget(self.comfyui_path_input)
        row_layout.addWidget(self.select_folder_btn)
        row_layout.addWidget(self.save_btn) # 把保存按钮移到同一行
        form.addRow(row_layout)

        # ========== 快捷打开文件夹区域 ==========
        quick_group = QGroupBox("快捷打开常用目录")
        quick_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                margin-top: 20px;
            }
        """)
        quick_layout = QVBoxLayout(quick_group)
        quick_layout.setContentsMargins(20, 30, 20, 20)
        quick_layout.setSpacing(15)

        # 按钮网格布局 (2行3列)
        grid = QGridLayout()
        grid.setSpacing(12)

        self.btn_open_py = self.create_quick_btn("🐍 打开 Python 根目录", "python_embeded")
        self.btn_open_models = self.create_quick_btn("📁 打开模型根目录", "ComfyUI/models")
        self.btn_open_nodes = self.create_quick_btn("🧩 打开插件根目录", "ComfyUI/custom_nodes")
        self.btn_open_workflows = self.create_quick_btn("📉 打开工作流目录", "ComfyUI/user/default/workflows")
        self.btn_open_input = self.create_quick_btn("📥 打开输入根目录", "ComfyUI/input")
        self.btn_open_output = self.create_quick_btn("📤 打开输出根目录", "ComfyUI/output")

        grid.addWidget(self.btn_open_py, 0, 0)
        grid.addWidget(self.btn_open_models, 0, 1)
        grid.addWidget(self.btn_open_nodes, 0, 2)
        grid.addWidget(self.btn_open_workflows, 1, 0)
        grid.addWidget(self.btn_open_input, 1, 1)
        grid.addWidget(self.btn_open_output, 1, 2)

        quick_layout.addLayout(grid)

        layout.addWidget(title)
        layout.addWidget(title2)
        layout.addWidget(group)
        layout.addWidget(quick_group) # 添加快捷按钮组
        layout.addStretch()

        # 绑定
        self.select_folder_btn.clicked.connect(self.select_python_folder)
        return page

    def create_quick_btn(self, text, sub_path):
        btn = QPushButton(text)
        btn.setFixedHeight(45)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 0 15px;
                text-align: left;
                font-size: 13px;
                color: #334155;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #cbd5e1;
            }
        """)
        # 使用 lambda 传参
        btn.clicked.connect(lambda: self.open_comfy_dir(sub_path))
        return btn

    def open_comfy_dir(self, sub_path):
        root = self.comfyui_path_input.text().strip()
        
        # 使用通用校验逻辑
        ok, msg = self.is_valid_comfy_root(root)
        if not ok:
            QMessageBox.critical(self, "错误", msg)
            return
        
        target_path = os.path.abspath(os.path.join(root, sub_path))
        if not os.path.exists(target_path):
            # 只有在根目录合法的情况下才尝试创建子目录
            try:
                os.makedirs(target_path, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建文件夹：\n{target_path}\n原因：{str(e)}")
                return

        # 调用系统资源管理器打开
        try:
            if platform.system() == "Windows":
                os.startfile(target_path)
            elif platform.system() == "Darwin": # macOS
                subprocess.run(["open", target_path])
            else: # Linux
                subprocess.run(["xdg-open", target_path])
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件夹：{str(e)}")

    # 选择文件夹
    def select_python_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 Python 根文件夹")
        if folder:
            self.comfyui_path_input.setText(folder)

    def load_config(self):
        if not os.path.exists(self.config_path):
            return None  # 第一次启动
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None

    # 保存配置
    def save_config(self):
        path = self.comfyui_path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "路径不能为空！")
            return

        # 自动创建配置文件夹
        if not os.path.exists(self.config_dir):
            os.mkdir(self.config_dir)

        # 写入配置
        config = {
            "comfyui_root": path,
            "uv_enabled": self.uv_switch.isChecked(),
            "online_enabled": self.online_switch.isChecked(),
            "online_ip": self.online_ip_input.text().strip(),
            "online_port": self.online_port_input.text().strip(),
            "hw_mode": self.hw_btn_group.checkedId(),
            "smart_mem_disabled": self.cb_smart_mem.isChecked(),
            "fp16_enabled": self.cb_fp16.isChecked(),
            "proxy_url": self.proxy_input.text().strip(),
            "pip_source_index": self.pip_btn_group.checkedId()
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # 弹出提示
        QMessageBox.information(self, "保存成功", "配置已保存！")
        
        # 刷新环境信息
        self.refresh_start_info(force=True)

    def write_app_log(self, event_type, details):
        """记录日志到 logs/meme_log.json"""
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            
            log_entry = {
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event": event_type,
                "details": details
            }

            logs = []
            if os.path.exists(self.log_file):
                try:
                    with open(self.log_file, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                        if not isinstance(logs, list):
                            logs = []
                except:
                    logs = []

            logs.append(log_entry)
            
            # 限制日志大小，保留最近 500 条
            if len(logs) > 500:
                logs = logs[-500:]

            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"写入日志失败: {str(e)}")

    # ====================== 主题切换 ======================
    def toggle_theme(self):
        # QMessageBox.information(self, "提示", "主题切换未完成，有bug..更新中...敬请期待")
        self.is_dark_mode = not self.is_dark_mode

        if self.is_dark_mode:
            self.creator_label.setStyleSheet("color: white;")
            self.btn_theme.setText("🌙")
            self.title_bar.setStyleSheet("QWidget{background:#1a1c1e; border-top-right-radius:12px;}")
            self.sidebar.setStyleSheet("QWidget{background:#111827; border-bottom-left-radius:12px;}")
            self.content_area.setStyleSheet("QWidget{background:#202124; border-bottom-right-radius:12px;}")
            self.title_label.setStyleSheet("color:white;")
            self.comfyui_path_input.setStyleSheet("""
                QLineEdit{padding:11px 14px; border-radius:9px; border:1px solid #444; background:#333; color:white;}
                QLineEdit:focus{border:1px solid #3a7bd5;}
            """)
            for btn in [self.btn_theme, self.btn_min, self.btn_max]:
                btn.setStyleSheet("QPushButton{border:none; background:transparent; color:white; border-radius:4px;} QPushButton:hover{background:#333;}")
            for btn in [self.btn_home, self.btn_advanceboard, self.btn_analytics, self.btn_settings, self.btn_about, self.btn_downloadMod, self.btn_offline_install, self.btn_proxy]:
                btn.setStyleSheet("""
                    QPushButton{border:none; padding:12px 16px; text-align:left; color:#eee; background:transparent; border-radius:8px; margin:4px 10px;}
                    QPushButton:checked{background:#3a7bd5; color:white; font-weight:bold;}
                    QPushButton:hover:!checked{background:#2d3748; color:white;}
                """)
            
            # 更新快捷按钮样式 (深色)
            for btn in [self.btn_open_py, self.btn_open_models, self.btn_open_nodes, self.btn_open_workflows, self.btn_open_input, self.btn_open_output]:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #333;
                        border: 1px solid #444;
                        border-radius: 8px;
                        padding: 0 15px;
                        text-align: left;
                        font-size: 13px;
                        color: #cbd5e1;
                    }
                    QPushButton:hover {
                        background-color: #444;
                        border-color: #555;
                    }
                """)

        else:
            self.creator_label.setStyleSheet("color: #1e293b;")
            self.btn_theme.setText("☀️")
            self.title_bar.setStyleSheet("QWidget{background:#f8fafc; border-top-right-radius:12px;}")
            self.sidebar.setStyleSheet("QWidget{background:#f8fafc; border-bottom-left-radius:12px;}")
            self.content_area.setStyleSheet("QWidget{background:white; border-bottom-right-radius:12px;}")
            self.title_label.setStyleSheet("color:#1e293b;")
            self.comfyui_path_input.setStyleSheet("""
                QLineEdit{padding:11px 14px; border-radius:9px; border:1px solid #d1d5db; background:white; color:#222;}
                QLineEdit:focus{border:1px solid #3a7bd5;}
            """)
            for btn in [self.btn_theme, self.btn_min, self.btn_max]:
                btn.setStyleSheet("QPushButton{border:none; background:transparent; color:#333; border-radius:4px;} QPushButton:hover{background:#e6e6e6;}")
            for btn in [self.btn_home, self.btn_advanceboard, self.btn_analytics, self.btn_settings, self.btn_about, self.btn_downloadMod, self.btn_offline_install, self.btn_proxy]:
                btn.setStyleSheet("""
                    QPushButton{border:none; padding:12px 16px; text-align:left; color:#333; background:transparent; border-radius:8px; margin:4px 10px;}
                    QPushButton:checked{background:#3a7bd5; color:white; font-weight:bold;}
                    QPushButton:hover:!checked{background:#e2e8f0; color:black;}
                """)

            # 更新快捷按钮样式 (浅色)
            for btn in [self.btn_open_py, self.btn_open_models, self.btn_open_nodes, self.btn_open_workflows, self.btn_open_input, self.btn_open_output]:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f8fafc;
                        border: 1px solid #e2e8f0;
                        border-radius: 8px;
                        padding: 0 15px;
                        text-align: left;
                        font-size: 13px;
                        color: #334155;
                    }
                    QPushButton:hover {
                        background-color: #f1f5f9;
                        border-color: #cbd5e1;
                    }
                """)
        self.update_system_info()

    def toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # if self.title_bar.rect().contains(event.pos()):  # 这一行报错
            if self.title_bar.rect().contains(event.position().toPoint()):  # 已修复
                self.dragging = True
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.dragging = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ModernSidebarWindow()
    win.show()
    sys.exit(app.exec())