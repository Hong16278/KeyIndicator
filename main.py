import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import keyboard
import threading
import time
import ctypes
import json
import os
import sys
import winreg
from PIL import Image, ImageDraw
import pystray

class KeyIndicatorOSD:
    def __init__(self, root, config_manager):
        # 使用 Toplevel 而不是新的 Tk 实例，因为主程序已经有一个 root 了
        self.osd_window = tk.Toplevel(root)
        self.config_manager = config_manager
        
        # 窗口配置
        self.osd_window.overrideredirect(True)  # 移除标题栏
        self.osd_window.wm_attributes("-topmost", True)  # 始终置顶
        self.osd_window.wm_attributes("-toolwindow", True)
        
        # 设置透明背景色（用于实现圆角）
        # Windows 上使用 -transparentcolor 来使特定颜色完全透明
        self.transparent_key = "#000001"  # 几乎纯黑，作为透明色键
        self.osd_window.wm_attributes("-transparentcolor", self.transparent_key)
        self.osd_window.configure(bg=self.transparent_key)
        
        # 窗口尺寸
        self.window_width = 200
        self.window_height = 60
        
        # 加载外观配置
        self.apply_appearance()
        
        # 加载位置
        self.load_position()
        
        # 使用 Canvas 绘制圆角背景
        self.canvas = tk.Canvas(
            self.osd_window,
            bg=self.transparent_key,
            highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)
        
        # 在 Canvas 上创建文字标签（居中）
        # 注意：Canvas 上的 create_text 不支持自动换行和复杂排版，
        # 但对于简单的单行文本足够了。或者我们可以把 Label 放在 Canvas 上方？
        # 为了圆角背景，我们需要 Canvas 在最底层。
        # 这里我们使用 Canvas 的 create_text 来绘制文字，或者 create_window 放入 Label。
        # create_window 放入 Label 可能导致 Label 的背景色遮挡圆角，除非 Label 也透明。
        # Tkinter Label 无法真正透明。所以最好直接在 Canvas 上绘制文字。
        
        self.text_id = self.canvas.create_text(
            self.window_width // 2,
            self.window_height // 2,
            text="",
            font=self.get_font(),
            fill=self.text_color
        )
        
        # 绑定鼠标事件用于拖拽 (绑定到 Canvas)
        self.osd_window.bind("<Button-1>", self.start_move)
        self.osd_window.bind("<B1-Motion>", self.do_move)
        self.osd_window.bind("<ButtonRelease-1>", self.stop_move)
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)
        self.canvas.bind("<ButtonRelease-1>", self.stop_move)

        self._drag_data = {"x": 0, "y": 0}
        self.is_dragging = False

        # 状态追踪
        self.fade_job = None
        self.is_cn_mode = False
        self.last_shift_time = 0
        
        # 初始隐藏
        self.hide_window()
        
        # 启动监听
        self.update_listeners()

    def apply_appearance(self):
        config = self.config_manager.get_config()
        self.bg_color = config.get("bg_color", "#1e1e1e")
        self.text_color = config.get("text_color", "#ffffff")
        self.font_size = config.get("font_size", 16)
        self.opacity = config.get("opacity", 0.8)
        self.border_color = config.get("border_color", "#444444")
        self.corner_radius = config.get("corner_radius", 10)  # 圆角半径
        
        # 确保类型正确 (防止从 json 加载后变成其他类型)
        self.font_size = int(self.font_size)
        self.opacity = float(self.opacity)
        self.corner_radius = int(self.corner_radius)
        
        # 动态计算窗口大小
        self.window_height = int(self.font_size * 3)
        self.window_width = int(self.font_size * 12)
        
        # 确保最小尺寸
        self.window_height = max(40, self.window_height)
        self.window_width = max(150, self.window_width)
        
        # 整体透明度
        self.osd_window.wm_attributes("-alpha", self.opacity)
        
        # 如果 Canvas 已创建，重绘背景
        if hasattr(self, 'canvas'):
            self.draw_background()
            
            # 更新文字样式
            self.canvas.itemconfig(self.text_id, font=self.get_font(), fill=self.text_color)
            # 更新文字位置
            self.canvas.coords(self.text_id, self.window_width // 2, self.window_height // 2)
            
        # 重新应用位置和大小
        self.load_position()

    def draw_background(self):
        self.canvas.delete("bg")
        
        # 绘制圆角矩形
        # 转换为 hex 颜色，以便 Canvas 识别
        # 注意：Canvas 不支持带 alpha 的颜色填充，透明度由窗口整体控制
        
        # 绘制边框（外层）
        x1, y1 = 0, 0
        x2, y2 = self.window_width, self.window_height
        
        # 限制圆角半径不超过高度或宽度的一半，防止绘图错乱
        r = min(self.corner_radius, self.window_height // 2, self.window_width // 2)
        
        # 绘制背景（使用 polygon 模拟圆角矩形，或者 create_aa_circle 等）
        # Tkinter 标准 Canvas 没有直接的 round_rect，需要自己画
        self.create_rounded_rect(x1, y1, x2, y2, r, outline=self.border_color, width=2, fill=self.bg_color, tag="bg")
        
        # 确保文字在最上层
        self.canvas.tag_raise(self.text_id)

    def create_rounded_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        points = [x1+radius, y1,
                  x1+radius, y1,
                  x2-radius, y1,
                  x2-radius, y1,
                  x2, y1,
                  x2, y1+radius,
                  x2, y1+radius,
                  x2, y2-radius,
                  x2, y2-radius,
                  x2, y2,
                  x2-radius, y2,
                  x2-radius, y2,
                  x1+radius, y2,
                  x1+radius, y2,
                  x1, y2,
                  x1, y2-radius,
                  x1, y2-radius,
                  x1, y1+radius,
                  x1, y1+radius,
                  x1, y1]

        return self.canvas.create_polygon(points, **kwargs, smooth=True)

    def get_font(self):
        return ("Microsoft YaHei", self.font_size, "bold")

    def load_position(self):
        screen_width = self.osd_window.winfo_screenwidth()
        screen_height = self.osd_window.winfo_screenheight()
        default_x = (screen_width - self.window_width) // 2
        # 改为默认显示在上方 (10% 位置)
        default_y = int(screen_height * 0.1)
        
        config = self.config_manager.get_config()
        x = config.get("x", default_x)
        y = config.get("y", default_y)
        
        # 简单的边界检查，防止窗口在屏幕外
        if x is None or y is None:
            x, y = default_x, default_y
            
        self.osd_window.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

    def save_position(self):
        try:
            x = self.osd_window.winfo_x()
            y = self.osd_window.winfo_y()
            self.config_manager.update_position(x, y)
        except Exception as e:
            print(f"保存配置错误: {e}")

    def start_move(self, event):
        self.is_dragging = True
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        # 拖拽时取消淡出
        if self.fade_job:
            self.osd_window.after_cancel(self.fade_job)
            self.fade_job = None

    def do_move(self, event):
        deltax = event.x - self._drag_data["x"]
        deltay = event.y - self._drag_data["y"]
        x = self.osd_window.winfo_x() + deltax
        y = self.osd_window.winfo_y() + deltay
        self.osd_window.geometry(f"+{x}+{y}")

    def stop_move(self, event):
        self.is_dragging = False
        self.save_position()
        # 恢复淡出
        self.fade_job = self.osd_window.after(1500, self.hide_window)

    def hide_window(self):
        if not self.is_dragging:
            self.osd_window.withdraw()
        
    def show_message(self, text, duration=1500):
        # self.label.config(text=text)
        self.canvas.itemconfig(self.text_id, text=text)
        self.osd_window.deiconify()
        
        # 取消之前的淡出任务
        if self.fade_job:
            self.osd_window.after_cancel(self.fade_job)
            
        # 安排新的淡出
        self.fade_job = self.osd_window.after(duration, self.hide_window)

    def get_caps_lock_state(self):
        # VK_CAPITAL = 0x14
        hllDll = ctypes.WinDLL("User32.dll")
        VK_CAPITAL = 0x14
        return hllDll.GetKeyState(VK_CAPITAL) & 1

    def handle_key_event(self, key_name):
        # 特殊按键处理
        if key_name == 'caps lock':
            # 稍微延迟以等待系统状态更新
            time.sleep(0.05)
            state = self.get_caps_lock_state()
            status = "ON" if state else "OFF"
            self.schedule_update(f"Caps Lock: {status}")
        elif key_name == 'shift':
            # 简单的 Shift 切换模拟
            current_time = time.time()
            if current_time - self.last_shift_time < 0.2:
                return
            self.last_shift_time = current_time
            
            self.is_cn_mode = not self.is_cn_mode
            status = "中" if self.is_cn_mode else "英"
            self.schedule_update(f"输入法: {status}")
        else:
            # 普通按键直接显示名称
            self.schedule_update(f"按键: {key_name.upper()}")

    def schedule_update(self, text):
        # 线程安全的 GUI 更新
        self.osd_window.after(0, lambda: self.show_message(text))

    def update_listeners(self):
        # 清除所有旧的钩子
        try:
            keyboard.unhook_all()
        except:
            pass
            
        # 获取需要监听的按键列表
        monitored_keys = self.config_manager.get_monitored_keys()
        
        for key in monitored_keys:
            try:
                # 使用闭包捕获 key 变量
                # 注意：keyboard.on_release_key 在单独线程运行
                if key == 'shift':
                    keyboard.on_press_key(key, lambda e, k=key: self.handle_key_event(k))
                else:
                    keyboard.on_release_key(key, lambda e, k=key: self.handle_key_event(k))
            except ValueError:
                print(f"无法监听按键: {key}")

class ConfigManager:
    def __init__(self, config_file="config.json"):
        # 确定配置文件路径
        if getattr(sys, 'frozen', False):
            # 如果是打包后的 exe，配置文件放在 exe 同级目录
            application_path = os.path.dirname(sys.executable)
        else:
            # 如果是脚本运行，配置文件放在脚本同级目录
            application_path = os.path.dirname(os.path.abspath(__file__))
            
        self.config_file = os.path.join(application_path, config_file)
        self.load_error = None
        self.config = self._load_config()

    def _load_config(self):
        default_config = {
            "x": None,
            "y": None,
            "monitored_keys": ["caps lock", "shift"],
            "close_action": "ask",
            "bg_color": "#000000",
            "text_color": "#84ffa3",
            "border_color": "#77ffff",
            "font_size": 17,
            "opacity": 0.8,
            "corner_radius": 100
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    # 确保加载所有保存的字段，不仅仅是默认值中存在的
                    for key, value in saved_config.items():
                        default_config[key] = value
                    return default_config
        except Exception as e:
            self.load_error = str(e)
            print(f"加载配置失败: {e}")
            
        return default_config

    def update_appearance(self, bg_color, text_color, border_color, font_size, opacity, corner_radius):
        self.config["bg_color"] = bg_color
        self.config["text_color"] = text_color
        self.config["border_color"] = border_color
        self.config["font_size"] = font_size
        self.config["opacity"] = opacity
        self.config["corner_radius"] = corner_radius
        self.save_config()

    def set_close_action(self, action):
        self.config["close_action"] = action
        self.save_config()

    def get_close_action(self):
        return self.config.get("close_action", "ask")

    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def get_config(self):
        return self.config

    def get_monitored_keys(self):
        return self.config["monitored_keys"]

    def set_startup(self, enable):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "KeyIndicator"
        try:
            # 获取正确的启动命令
            if getattr(sys, 'frozen', False):
                # 打包后的 exe
                run_path = f'"{sys.executable}"'
            else:
                # 脚本运行模式：使用 pythonw.exe 避免黑框
                python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                script_path = os.path.abspath(sys.argv[0])
                run_path = f'"{python_exe}" "{script_path}"'
            
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                if enable:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, run_path)
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
        except Exception as e:
            print(f"设置开机启动失败: {e}")

    def is_startup_enabled(self):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "KeyIndicator"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, app_name)
                # 检查注册表中的路径是否包含当前程序
                # 如果是 exe 模式，必须完全匹配
                if getattr(sys, 'frozen', False):
                    return os.path.normcase(value.strip('"')) == os.path.normcase(sys.executable)
                else:
                    # 脚本模式只要存在即可 (简化处理)
                    return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def fix_startup_path(self):
        # 仅在 exe 模式下自动修复路径
        if getattr(sys, 'frozen', False):
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "KeyIndicator"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                    try:
                        value, _ = winreg.QueryValueEx(key, app_name)
                        current_exe = sys.executable
                        # 如果路径不匹配，强制更新
                        if os.path.normcase(value.strip('"')) != os.path.normcase(current_exe):
                            print("检测到开机启动路径不正确，正在自动修复...")
                            run_path = f'"{current_exe}"'
                            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, run_path)
                    except FileNotFoundError:
                        # 没有设置开机启动，无需修复
                        pass
            except Exception as e:
                print(f"修复开机启动路径失败: {e}")

    def add_key(self, key):
        if key not in self.config["monitored_keys"]:
            self.config["monitored_keys"].append(key)
            self.save_config()
            return True
        return False

    def remove_key(self, key):
        if key in self.config["monitored_keys"]:
            self.config["monitored_keys"].remove(key)
            self.save_config()
            return True
        return False

    def update_position(self, x, y):
        self.config["x"] = x
        self.config["y"] = y
        self.save_config()

    def reset_defaults(self):
        self.config = {
            "x": None,
            "y": None,
            "monitored_keys": ["caps lock", "shift"],
            "close_action": "ask",
            "bg_color": "#000000",
            "text_color": "#84ffa3",
            "border_color": "#77ffff",
            "font_size": 17,
            "opacity": 0.8,
            "corner_radius": 100
        }
        self.save_config()

class MainWindow:
    def __init__(self):
        self.check_admin()
        self.root = tk.Tk()
        self.root.title("按键提示器设置")
        # 增加初始高度，并设置最小尺寸
        self.root.geometry("450x550")
        self.root.minsize(350, 450)
        
        self.config_manager = ConfigManager()
        # 检查配置加载错误
        if self.config_manager.load_error:
            messagebox.showerror("配置加载错误", f"无法加载配置文件，将使用默认设置。\n错误信息: {self.config_manager.load_error}\n路径: {self.config_manager.config_file}")
            
        # 尝试自动修复开机启动路径（仅在 exe 模式下）
        self.config_manager.fix_startup_path()
        
        self.osd = None
        self.tray_icon = None
        
        self.setup_ui()
        
        # 延迟初始化 OSD，确保主窗口先加载
        self.root.after(100, self.init_osd)
        
        # 拦截关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_tray_icon(self):
        image = Image.new('RGB', (64, 64), color=(30, 30, 30))
        d = ImageDraw.Draw(image)
        d.text((10, 20), "Key", fill=(255, 255, 255))
        
        menu = (
            pystray.MenuItem("显示设置", self.show_window),
            pystray.MenuItem("退出", self.quit_app)
        )
        
        self.tray_icon = pystray.Icon("KeyIndicator", image, "按键提示器", menu)
        # 在单独线程运行 tray，避免阻塞 tkinter
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)

    def quit_app(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)
        # 确保进程退出
        os._exit(0)

    def on_close(self):
        action = self.config_manager.get_close_action()
        
        if action == "minimize":
            self.minimize_to_tray()
            return
        elif action == "exit":
            self.quit_app()
            return
            
        # 询问用户
        self.show_close_dialog()

    def minimize_to_tray(self):
        self.root.withdraw()
        if not self.tray_icon:
            self.create_tray_icon()
        # 托盘提示
        if self.tray_icon:
            self.tray_icon.notify("程序已最小化到托盘，双击图标或右键菜单可恢复", "按键提示器")

    def show_close_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("关闭程序")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中显示
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 150) // 2
        dialog.geometry(f"+{x}+{y}")
        
        tk.Label(dialog, text="您想要执行什么操作？", pady=20).pack()
        
        var_dont_ask = tk.BooleanVar()
        
        def do_minimize():
            if var_dont_ask.get():
                self.config_manager.set_close_action("minimize")
            self.minimize_to_tray()
            dialog.destroy()
            
        def do_exit():
            if var_dont_ask.get():
                self.config_manager.set_close_action("exit")
            self.quit_app()
            
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Button(btn_frame, text="最小化到托盘", command=do_minimize).pack(side='left', expand=True)
        tk.Button(btn_frame, text="退出程序", command=do_exit).pack(side='right', expand=True)
        
        tk.Checkbutton(dialog, text="不再询问 (记住选择)", variable=var_dont_ask).pack(side='bottom', pady=10)

    def check_admin(self):
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except:
            is_admin = False
            
        if not is_admin:
            # 如果不是打包的 exe，提醒用户
            if not getattr(sys, 'frozen', False):
                print("警告: 程序未以管理员身份运行，按键监听可能无法正常工作。")
                # 在 GUI 初始化前，我们只能打印。GUI 初始化后可以弹窗，但这里尽量早点提示。

    def init_osd(self):
        self.osd = KeyIndicatorOSD(self.root, self.config_manager)

    def setup_ui(self):
        # 创建选项卡控件
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both', padx=5, pady=5)
        
        # 1. 监控设置页
        self.keys_frame = tk.Frame(self.notebook)
        self.notebook.add(self.keys_frame, text="按键监控")
        self.setup_keys_ui(self.keys_frame)
        
        # 2. 外观设置页
        self.appearance_frame = tk.Frame(self.notebook)
        self.notebook.add(self.appearance_frame, text="外观设置")
        self.setup_appearance_ui(self.appearance_frame)

    def setup_keys_ui(self, parent):
        # 顶部容器：包含标签和录制按钮
        top_frame = tk.Frame(parent)
        top_frame.pack(side='top', fill='x', padx=10, pady=10)

        # 说明标签
        tk.Label(top_frame, text="监控按键列表:").pack(anchor='w')
        
        # 录制按钮
        self.record_btn = tk.Button(top_frame, text="点击此处并按下按键以添加", command=self.start_recording_key, height=2)
        self.record_btn.pack(fill='x', pady=(5, 0))
        
        # 底部容器：包含操作按钮
        bottom_frame = tk.Frame(parent)
        bottom_frame.pack(side='bottom', fill='x', padx=10, pady=10)
        
        remove_btn = tk.Button(bottom_frame, text="删除选中", command=self.remove_key)
        remove_btn.pack(side='left', padx=(0, 5))
        
        refresh_btn = tk.Button(bottom_frame, text="刷新监听", command=self.refresh_listeners)
        refresh_btn.pack(side='left', padx=(0, 5))
        
        reset_btn = tk.Button(bottom_frame, text="恢复默认", command=self.restore_defaults)
        reset_btn.pack(side='left', padx=(0, 20))
        
        # 开机自启复选框
        self.startup_var = tk.BooleanVar(value=self.config_manager.is_startup_enabled())
        startup_cb = tk.Checkbutton(bottom_frame, text="开机自启", variable=self.startup_var, command=self.toggle_startup)
        startup_cb.pack(side='right')
        
        # 中间容器：列表区域
        list_frame = tk.Frame(parent)
        list_frame.pack(side='top', expand=True, fill='both', padx=10, pady=(0, 0))
        
        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self.keys_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        
        scrollbar.config(command=self.keys_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.keys_listbox.pack(side='left', expand=True, fill='both')
        
        # 填充列表
        self.refresh_list()

    def setup_appearance_ui(self, parent):
        config = self.config_manager.get_config()
        
        # 字体大小
        tk.Label(parent, text="字体大小:").pack(anchor='w', padx=20, pady=(10, 5))
        self.font_size_scale = tk.Scale(parent, from_=10, to=48, orient='horizontal')
        self.font_size_scale.set(config.get("font_size", 16))
        self.font_size_scale.pack(fill='x', padx=20)
        
        # 透明度
        tk.Label(parent, text="不透明度 (0.1 - 1.0):").pack(anchor='w', padx=20, pady=(10, 5))
        self.opacity_scale = tk.Scale(parent, from_=0.1, to=1.0, resolution=0.1, orient='horizontal')
        self.opacity_scale.set(config.get("opacity", 0.8))
        self.opacity_scale.pack(fill='x', padx=20)
        
        # 圆角半径
        tk.Label(parent, text="圆角大小 (0 - 100):").pack(anchor='w', padx=20, pady=(10, 5))
        self.radius_scale = tk.Scale(parent, from_=0, to=100, orient='horizontal')
        self.radius_scale.set(config.get("corner_radius", 10))
        self.radius_scale.pack(fill='x', padx=20)
        
        # 颜色选择
        colors_frame = tk.Frame(parent)
        colors_frame.pack(fill='x', padx=20, pady=10)
        
        self.bg_color_var = config.get("bg_color", "#1e1e1e")
        self.text_color_var = config.get("text_color", "#ffffff")
        self.border_color_var = config.get("border_color", "#444444")
        
        # 背景色按钮
        tk.Button(colors_frame, text="背景颜色", command=self.choose_bg_color).pack(side='left', expand=True, fill='x', padx=(0, 5))
        # 文本色按钮
        tk.Button(colors_frame, text="文字颜色", command=self.choose_text_color).pack(side='left', expand=True, fill='x', padx=(0, 5))
        # 边框色按钮
        tk.Button(colors_frame, text="边框颜色", command=self.choose_border_color).pack(side='left', expand=True, fill='x')
        
        # 按钮容器
        btn_frame = tk.Frame(parent)
        btn_frame.pack(fill='x', padx=20, pady=20)
        
        # 恢复默认按钮
        tk.Button(btn_frame, text="恢复默认", command=self.restore_defaults).pack(side='left', padx=(0, 10))
        
        # 应用按钮
        tk.Button(btn_frame, text="应用更改并预览", command=self.apply_appearance_changes, height=2).pack(side='left', expand=True, fill='x')

        # 显示配置文件路径 (用于调试)
        path_frame = tk.Frame(parent)
        path_frame.pack(side='bottom', fill='x', padx=10, pady=5)
        path_label = tk.Label(path_frame, text=f"配置文件路径: {self.config_manager.config_file}", fg="gray", font=("Arial", 8), wraplength=400)
        path_label.pack(anchor='w')

    def choose_bg_color(self):
        color = colorchooser.askcolor(title="选择背景颜色", color=self.bg_color_var)[1]
        if color:
            self.bg_color_var = color
            
    def choose_text_color(self):
        color = colorchooser.askcolor(title="选择文字颜色", color=self.text_color_var)[1]
        if color:
            self.text_color_var = color

    def choose_border_color(self):
        color = colorchooser.askcolor(title="选择边框颜色", color=self.border_color_var)[1]
        if color:
            self.border_color_var = color

    def apply_appearance_changes(self):
        font_size = self.font_size_scale.get()
        opacity = self.opacity_scale.get()
        corner_radius = self.radius_scale.get()
        
        self.config_manager.update_appearance(
            self.bg_color_var,
            self.text_color_var,
            self.border_color_var,
            font_size,
            opacity,
            corner_radius
        )
        
        if self.osd:
            self.osd.apply_appearance()
            self.osd.show_message("预览样式 ABC")

    def start_recording_key(self):
        self.record_btn.config(text="请按下一个按键...", state='disabled', bg="#ffcccc")
        # 在新线程中等待按键，避免阻塞 UI
        threading.Thread(target=self._wait_for_key, daemon=True).start()

    def _wait_for_key(self):
        # 读取下一个键盘事件
        event = keyboard.read_event()
        # 只需要按下的事件
        while event.event_type != keyboard.KEY_DOWN:
            event = keyboard.read_event()
        
        # 回到主线程更新 UI
        self.root.after(0, lambda: self.finish_recording_key(event.name))

    def finish_recording_key(self, key_name):
        self.record_btn.config(text="点击此处并按下按键以添加", state='normal', bg="SystemButtonFace")
        
        if key_name:
            if self.config_manager.add_key(key_name):
                self.refresh_list()
                self.refresh_listeners()
                # 可以在这里显示一个简短的提示，或者直接通过列表更新反馈
            else:
                messagebox.showinfo("提示", f"按键 '{key_name}' 已在列表中")

    def refresh_list(self):
        self.keys_listbox.delete(0, tk.END)
        for key in self.config_manager.get_monitored_keys():
            self.keys_listbox.insert(tk.END, key)

    def remove_key(self):
        selection = self.keys_listbox.curselection()
        if not selection:
            return
            
        key = self.keys_listbox.get(selection[0])
        if self.config_manager.remove_key(key):
            self.refresh_list()
            self.refresh_listeners()

    def refresh_listeners(self):
        if self.osd:
            self.osd.update_listeners()
            self.osd.show_message("监听配置已更新")

    def toggle_startup(self):
        self.config_manager.set_startup(self.startup_var.get())

    def restore_defaults(self):
        if messagebox.askyesno("确认", "确定要恢复默认设置吗？\n这将重置按键列表和窗口位置。"):
            self.config_manager.reset_defaults()
            self.refresh_list()
            self.refresh_listeners()
            if self.osd:
                self.osd.load_position()
                self.osd.show_message("已恢复默认设置")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = MainWindow()
    app.run()
