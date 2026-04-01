import subprocess
import json
import os
import platform
import tomllib  # 读取 pyproject.toml
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QStackedWidget, QLabel, QFrame,
    QLineEdit, QFormLayout, QGroupBox, QFileDialog
)
from PySide6.QtGui import QFont
import sys

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


        self.setWindowTitle("Modern Sidebar")
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
        self.title_layout.setContentsMargins(20, 0, 10, 0)
        self.title_layout.setSpacing(0)

        # 窗口标题
        self.title_label = QLabel("ComfyUI Meme Starter")
        self.title_label.setFont(QFont("微软雅黑", 11, QFont.Bold))
        self.title_label.setStyleSheet("color: #1e293b;")


        # 主题切换按钮 ☀️ 🌙
        self.btn_theme = QPushButton("☀️")
        self.btn_min = QPushButton("—")
        self.btn_max = QPushButton("⚪")
        self.btn_close = QPushButton("✕")

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
        self.page_dashboard = self.create_page("高级选项", "高级的选项")
        self.page_analytics = self.create_system_info_page()
        self.page_dd = self.create_page("下载功能", "下载依赖，智能跳过，安全安装")
        self.page_settings = self.create_settings_page()
        self.page_about = self.create_page("关于", "Modern UI v1.0")

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_dashboard)
        self.stack.addWidget(self.page_analytics)
        self.stack.addWidget(self.page_settings)
        self.stack.addWidget(self.page_about)
        self.stack.addWidget(self.page_dd)
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

        self.dragging = False
        self.drag_pos = QPoint()

        # 启动加载配置
        config = self.load_config()
        if config and "comfyui_root" in config:
            self.comfyui_path_input.setText(config["comfyui_root"])

    # 保存进程对象
    comfy_process = None

    def start_comfyui(self):
        config = self.load_config()
        if not config:
            QMessageBox.warning(self, "提示", "请先配置 ComfyUI 路径！")
            return

        root = config["comfyui_root"]
        python_exe = os.path.join(root, "python_embeded", "python.exe")
        main_py = os.path.join(root, "ComfyUI", "main.py")

        if not os.path.exists(python_exe) or not os.path.exists(main_py):
            QMessageBox.critical(self, "错误", "ComfyUI 路径不完整！")
            return

        # 启动命令
        cmd = [python_exe, "-s", main_py, "--windows-standalone-build"]
        self.comfy_process = subprocess.Popen(cmd, cwd=root)

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

    def refresh_start_info(self):
        config = self.load_config()
        if not config:
            self.set_card_text(self.env_card, "未配置 ComfyUI 路径", "请前往环境配置", "")
            self.set_card_text(self.version_card, "未配置", "", "")
            self.set_card_text(self.libs_card, "未配置", "", "")
            return

        root = config.get("comfyui_root", "")
        if not os.path.exists(root):
            self.set_card_text(self.env_card, "路径不存在", "请检查配置", "")
            return

        # -------------------- 读取 ComfyUI 版本 --------------------
        comfy_version = "未知"
        toml_path = os.path.join(root, "ComfyUI", "pyproject.toml")
        if os.path.exists(toml_path):
            try:
                with open(toml_path, "r", encoding="utf-8") as f:
                    data = tomllib.loads(f.read())
                    comfy_version = data.get("project", {}).get("version", "未知")
            except:
                pass

        # -------------------- 读取 Python 版本 --------------------
        # -------------------- 读取 Python 版本（智能识别，不写死） --------------------
        py_detail = "未知"
        py_short = "未知"

        try:
            exe = os.path.join(root, "python_embeded", "python.exe")
            py_detail = subprocess.check_output([exe, "--version"], text=True).strip()  # Python 3.12.10

            # 自动从版本号提取 cpXXX 格式
            if "Python" in py_detail:
                version_part = py_detail.split()[1]  # 3.12.10
                major_minor = version_part.split(".")[:2]  # ["3","12"]
                py_short = "py简写代号: cp" + "".join(major_minor)

        except:
            # 命令获取失败，尝试从 pth 文件智能匹配（兼容所有版本）
            try:
                embed_dir = os.path.join(root, "python_embeded")
                for fn in os.listdir(embed_dir):
                    if fn.startswith("python3") and fn.endswith("._pth"):
                        # python310._pth → 310
                        ver_num = fn.replace("python", "").replace("._pth", "")
                        py_short = "cp" + ver_num
                        break
            except:
                pass
        # -------------------- 读取 Torch / Transformers --------------------
        torch_ver = "未找到"
        trans_ver = "未找到"
        site = os.path.join(root, "python_embeded", "Lib", "site-packages")

        if os.path.exists(site):
            for name in os.listdir(site):
                if name.startswith("torch-") and ".dist-info" in name:
                    torch_ver = name.replace(".dist-info", "")
                if name.startswith("transformers-") and ".dist-info" in name:
                    trans_ver = name.replace(".dist-info", "")

        # -------------------- 🔥 新增：显卡驱动 / CUDA 信息 --------------------
        driver_version = "未获取"
        cuda_max_support = "未获取"
        nvcc_version = "未检测"
        cuda_system_version = "未检测"

        # 读取 nvidia-smi
        try:
            smi_output = subprocess.check_output(["nvidia-smi"], text=True, encoding="utf-8", errors="ignore")
            for line in smi_output.split("\n"):
                if "Driver Version:" in line:
                    # 提取驱动版本
                    if "Driver Version:" in line:
                        driver_version = line.split("Driver Version:")[1].split()[0].strip()
                    # 提取支持的最高 CUDA
                    if "CUDA Version:" in line:
                        cuda_max_support = line.split("CUDA Version:")[1].strip()[0:line.split("CUDA Version:")[1].strip().find("|")]
                    break
        except:
            pass

        # 读取 nvcc --version
        try:
            nvcc_output = subprocess.check_output(["nvcc", "--version"], text=True, encoding="utf-8", errors="ignore")
            for line in nvcc_output.split("\n"):
                if "Build" in line:
                    nvcc_version = line.strip()
                if "release" in line and "V" in line:
                    cuda_system_version = "cuda_" + line.split("release")[1].split(",")[0].strip()
        except:
            pass

        # -------------------- 更新到卡片 --------------------
        # 🔥 第一张：环境信息 → 显卡驱动 CUDA
        self.set_card_text(self.env_card,
                           f"驱动版本：{driver_version}",
                           f"最高CUDA：{cuda_max_support}",
                           f"系统CUDA：{cuda_system_version.replace('cuda_', '')}")

        # 第二张：版本信息（不变）
        self.set_card_text(self.version_card,
                           f"ComfyUI：{comfy_version}",
                           f"{py_detail}",
                           f"{py_short}")

        # 第三张：核心库（不变）
        self.set_card_text(self.libs_card,
                           f"{torch_ver}",
                           f"{trans_ver}",
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
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
        except:
            gpus = []

        # ---------------- CPU ----------------
        cpu_model = self.get_cpu_model()
        cpu_usage = psutil.cpu_percent()
        cores = psutil.cpu_count(logical=True)

        # ---------------- RAM ----------------
        mem = psutil.virtual_memory()
        ram_total = f"{mem.total // (1024**3)} GB"
        ram_used = f"{mem.used // (1024**3)} GB"
        ram_avail = f"{mem.available // (1024**3)} GB"

        # ---------------- GPU（兼容核显） ----------------
        if gpus:
            gpu = gpus[0]
            gpu_name = gpu.name
            gpu_load = f"{gpu.load*100:.1f}%"
            gpu_total = f"{gpu.memoryTotal:.0f} MB"
            gpu_used = f"{gpu.memoryUsed:.0f} MB"
        else:
            import platform
            gpu_name = "核显 / 集成显卡"
            gpu_load = "0.0%"
            gpu_total = "共享内存"
            gpu_used = "动态分配"

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
        title = QLabel("系统设置")
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

        # 行布局
        row_layout = QHBoxLayout()
        row_layout.addWidget(self.comfyui_path_input)
        row_layout.addWidget(self.select_folder_btn)
        form.addRow(row_layout) # 可以使用文字前缀 form.addRow("Python 根目录：", row_layout)

        # 保存按钮
        self.save_btn = QPushButton("💾 保存设置")
        self.save_btn.setFixedHeight(42)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a7bd5;
                color: white;
                border: none;
                border-radius: 9px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2d6dc2;
            }
        """)

        layout.addWidget(title)
        layout.addWidget(title2)
        layout.addWidget(group)
        layout.addWidget(self.save_btn)
        layout.addStretch()

        # 绑定选择文件夹
        self.select_folder_btn.clicked.connect(self.select_python_folder)
        return page

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
        config = {"comfyui_root": path}
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # 弹出提示
        QMessageBox.information(self, "保存成功", "配置已保存！\n重启软件后生效。")

    # ====================== 主题切换 ======================
    def toggle_theme(self):
        QMessageBox.information(self, "提示", "主题切换未完成，有bug..更新中...敬请期待")
        # self.is_dark_mode = not self.is_dark_mode
        #
        # if self.is_dark_mode:
        #     self.btn_theme.setText("🌙")
        #     self.title_bar.setStyleSheet("QWidget{background:#1a1c1e; border-top-right-radius:12px;}")
        #     self.sidebar.setStyleSheet("QWidget{background:#111827; border-bottom-left-radius:12px;}")
        #     self.content_area.setStyleSheet("QWidget{background:#202124; border-bottom-right-radius:12px;}")
        #     self.title_label.setStyleSheet("color:white;")
        #     self.comfyui_path_input.setStyleSheet("""
        #         QLineEdit{padding:11px 14px; border-radius:9px; border:1px solid #444; background:#333; color:white;}
        #         QLineEdit:focus{border:1px solid #3a7bd5;}
        #     """)
        #     for btn in [self.btn_theme, self.btn_min, self.btn_max]:
        #         btn.setStyleSheet("QPushButton{border:none; background:transparent; color:white; border-radius:4px;} QPushButton:hover{background:#333;}")
        #     for btn in [self.btn_home, self.btn_advanceboard, self.btn_analytics, self.btn_settings, self.btn_about,self.btn_downloadMod]:
        #         btn.setStyleSheet("""
        #             QPushButton{border:none; padding:12px 16px; text-align:left; color:#eee; background:transparent; border-radius:8px; margin:4px 10px;}
        #             QPushButton:checked{background:#3a7bd5; color:white; font-weight:bold;}
        #             QPushButton:hover:!checked{background:#2d3748; color:white;}
        #         """)
        #
        # else:
        #     self.btn_theme.setText("☀️")
        #     self.title_bar.setStyleSheet("QWidget{background:#f8fafc; border-top-right-radius:12px;}")
        #     self.sidebar.setStyleSheet("QWidget{background:#f8fafc; border-bottom-left-radius:12px;}")
        #     self.content_area.setStyleSheet("QWidget{background:white; border-bottom-right-radius:12px;}")
        #     self.title_label.setStyleSheet("color:#1e293b;")
        #     self.comfyui_path_input.setStyleSheet("""
        #         QLineEdit{padding:11px 14px; border-radius:9px; border:1px solid #d1d5db; background:white; color:#222;}
        #         QLineEdit:focus{border:1px solid #3a7bd5;}
        #     """)
        #     for btn in [self.btn_theme, self.btn_min, self.btn_max]:
        #         btn.setStyleSheet("QPushButton{border:none; background:transparent; color:#333; border-radius:4px;} QPushButton:hover{background:#e6e6e6;}")
        #     for btn in [self.btn_home, self.btn_advanceboard, self.btn_analytics, self.btn_settings, self.btn_about,self.btn_downloadMod]:
        #         btn.setStyleSheet("""
        #             QPushButton{border:none; padding:12px 16px; text-align:left; color:#333; background:transparent; border-radius:8px; margin:4px 10px;}
        #             QPushButton:checked{background:#3a7bd5; color:white; font-weight:bold;}
        #             QPushButton:hover:!checked{background:#e2e8f0; color:black;}
        #         """)
        # self.update_system_info()

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