import sys
import os
import zipfile
import shutil
import subprocess
import importlib.util
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTreeView, QFileSystemModel, QTabWidget, QLabel, QPushButton, QPlainTextEdit, QFrame, QMessageBox, QFileDialog, QInputDialog, QProgressDialog, QProgressBar
)
from PyQt5.QtCore import Qt, QProcess, QTimer, QModelIndex
from PyQt5.QtGui import QFont, QColor
import psutil
from datetime import datetime
import webbrowser
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect
from PyQt5.QtGui import QPixmap, QIcon
import threading
import requests

def autoimport(pkg, pip_name=None):
    pip_name = pip_name or pkg
    try:
        return importlib.import_module(pkg)
    except ImportError:
        print(f'Встановлення {pip_name}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pip_name])
        return importlib.import_module(pkg)

# Гарантовано імпортуємо всі потрібні модулі
requests = autoimport('requests')
PyQt5 = autoimport('PyQt5')
psutil = autoimport('psutil')
telegram = autoimport('telegram', 'python-telegram-bot')

class CustomMessageBox(QDialog):
    ICONS = {
        'info': '🛈',
        'error': '⛔',
        'success': '✅',
        'warning': '⚠️',
    }
    def __init__(self, title, text, mtype='info', parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(340)
        self.setStyleSheet('''
            QDialog { background: #232323; border-radius: 14px; }
            QLabel { color: #dddddd; font-size: 16px; }
            QPushButton { background: #3a3a3a; color: #00ff88; border-radius: 8px; padding: 10px 24px; font-size: 15px; }
            QPushButton:hover { background: #505050; color: #00ff88; }
        ''')
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(18)
        # Іконка
        icon_lbl = QLabel(self.ICONS.get(mtype, '🛈'))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet('font-size: 38px;')
        v.addWidget(icon_lbl)
        # Текст
        text_lbl = QLabel()
        text_lbl.setTextFormat(Qt.RichText)
        text_lbl.setText(text)
        text_lbl.setWordWrap(True)
        text_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(text_lbl)
        # Кнопка
        btn = QPushButton('OK')
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.clicked.connect(self.accept)
        v.addWidget(btn)
        # Анімація появи
        self.setWindowOpacity(0)
        self.anim = QPropertyAnimation(self, b'windowOpacity')
        self.anim.setDuration(220)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()

    @staticmethod
    def show_message(title, text, mtype='info', parent=None):
        dlg = CustomMessageBox(title, text, mtype, parent)
        dlg.exec_()

SCRIPTS_DIR = 'scripts'

if not os.path.exists(SCRIPTS_DIR):
    os.makedirs(SCRIPTS_DIR)

def ensure_package(pkg, pip_name=None):
    pip_name = pip_name or pkg
    if importlib.util.find_spec(pkg) is None:
        print(f'Встановлення {pip_name}...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pip_name])

# Перевірка та встановлення залежностей
for pkg, pip_name in [
    ('PyQt5', 'PyQt5'),
    ('psutil', 'psutil'),
    ('telegram', 'python-telegram-bot'),
]:
    ensure_package(pkg, pip_name)

# Перевірка наявності git
if shutil.which('git') is None:
    from PyQt5.QtWidgets import QApplication
    app = QApplication([])
    CustomMessageBox.show_message(
        'Git не знайдено',
        '⛔ <b>Git не встановлено у системі!</b><br><br>Відкрито сторінку завантаження git:<br><a href="https://git-scm.com/download/win">https://git-scm.com/download/win</a>',
        'error'
    )
    webbrowser.open('https://git-scm.com/download/win')
    sys.exit(1)

class ScriptTab(QWidget):
    def __init__(self, script_path, close_callback):
        super().__init__()
        self.script_path = script_path
        self.process = None
        self.is_running = False
        self.close_callback = close_callback
        self.timer = None
        self.scheduled_time = None
        self.telegram_token = None
        self.telegram_chat_id = None
        self.ps_process = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.title = QLabel(f'🧠 {os.path.relpath(self.script_path, SCRIPTS_DIR)}')
        self.title.setFont(QFont('Consolas', 15, QFont.Bold))
        self.title.setStyleSheet('color: #00ff88; margin-bottom: 8px;')
        layout.addWidget(self.title)
        self.status_label = QLabel('🟢 Статус: Готово')
        self.status_label.setFont(QFont('Consolas', 12))
        self.status_label.setStyleSheet('color: #dddddd;')
        layout.addWidget(self.status_label)
        # Аргументи запуску
        args_layout = QHBoxLayout()
        args_label = QLabel('Аргументи:')
        args_label.setFont(QFont('Consolas', 10))
        args_label.setStyleSheet('color: #dddddd;')
        self.args_field = QPlainTextEdit()
        self.args_field.setPlaceholderText('Введіть аргументи через пробіл...')
        self.args_field.setMaximumHeight(30)
        self.args_field.setFont(QFont('Consolas', 10))
        self.args_field.setStyleSheet('background: #232323; color: #dddddd; border-radius: 6px; padding: 4px;')
        args_layout.addWidget(args_label)
        args_layout.addWidget(self.args_field, 1)
        layout.addLayout(args_layout)
        # Кнопки
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton('▶ Запустити')
        self.btn_stop = QPushButton('⏹ Зупинити')
        self.btn_restart = QPushButton('🔁 Перезапустити')
        self.btn_save_log = QPushButton('💾 Зберегти лог')
        for btn in [self.btn_start, self.btn_stop, self.btn_restart, self.btn_save_log]:
            btn.setMinimumWidth(110)
            btn.setMinimumHeight(36)
            btn.setFont(QFont('Consolas', 11))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self.button_stylesheet())
        self.btn_start.clicked.connect(self.start_script)
        self.btn_stop.clicked.connect(self.stop_script)
        self.btn_restart.clicked.connect(self.restart_script)
        self.btn_save_log.clicked.connect(self.save_log)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_restart)
        btn_layout.addWidget(self.btn_save_log)
        layout.addLayout(btn_layout)
        # Роздільник
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet('color: #333333; background: #333333; height: 2px;')
        layout.addWidget(line)
        # Логи
        self.log_field = QPlainTextEdit()
        self.log_field.setReadOnly(True)
        self.log_field.setFont(QFont('Consolas', 11))
        self.log_field.setStyleSheet('background: #151515; color: #00ff88; border-radius: 8px; padding: 8px;')
        self.log_field.setMinimumHeight(120)
        layout.addWidget(self.log_field, stretch=1)
        # Моніторинг CPU/RAM
        self.res_label = QLabel('CPU: 0% | RAM: 0 MB')
        self.res_label.setFont(QFont('Consolas', 10))
        self.res_label.setStyleSheet('color: #00ff88; margin-top: 4px;')
        layout.addWidget(self.res_label)
        self.res_timer = QTimer()
        self.res_timer.timeout.connect(self.update_resource_usage)
        # Розклад запуску
        sched_layout = QHBoxLayout()
        self.sched_btn = QPushButton('⏰ Запланувати запуск')
        self.sched_btn.setFont(QFont('Consolas', 10))
        self.sched_btn.setStyleSheet(self.button_stylesheet())
        self.sched_btn.clicked.connect(self.schedule_run)
        self.sched_time_label = QLabel('')
        self.sched_time_label.setFont(QFont('Consolas', 10))
        self.sched_time_label.setStyleSheet('color: #dddddd;')
        sched_layout.addWidget(self.sched_btn)
        sched_layout.addWidget(self.sched_time_label)
        layout.addLayout(sched_layout)
        # Telegram
        tg_layout = QHBoxLayout()
        self.tg_btn = QPushButton('🔗 Telegram')
        self.tg_btn.setFont(QFont('Consolas', 10))
        self.tg_btn.setStyleSheet(self.button_stylesheet())
        self.tg_btn.clicked.connect(self.setup_telegram)
        self.tg_status = QLabel('')
        self.tg_status.setFont(QFont('Consolas', 10))
        self.tg_status.setStyleSheet('color: #dddddd;')
        tg_layout.addWidget(self.tg_btn)
        tg_layout.addWidget(self.tg_status)
        layout.addLayout(tg_layout)

    def button_stylesheet(self):
        return '''
        QPushButton {
            background: #3a3a3a;
            color: #dddddd;
            border: none;
            border-radius: 8px;
            padding: 8px 18px;
        }
        QPushButton:hover {
            background: #505050;
            color: #00ff88;
        }
        QPushButton:pressed {
            background: #222222;
        }
        '''

    def start_script(self):
        if self.is_running:
            CustomMessageBox.show_message('Увага', 'Скрипт вже виконується!', 'warning', self)
            return
        if not os.path.exists(self.script_path):
            CustomMessageBox.show_message('Помилка', 'Скрипт не знайдено!', 'error', self)
            return
        args = self.args_field.toPlainText().strip().split()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.on_process_finished)
        self.process.started.connect(lambda: self.status_label.setText('🟡 Статус: Виконується'))
        self.process.start(sys.executable, [self.script_path] + args)
        if not self.process.waitForStarted(1000):
            self.status_label.setText('🔴 Статус: Не вдалося запустити')
            self.log_field.appendPlainText('❗ Не вдалося запустити скрипт.')
            return
        self.is_running = True
        self.status_label.setText('🟡 Статус: Виконується')
        self.log_field.appendPlainText(f'▶ Запуск: {os.path.basename(self.script_path)} {" ".join(args)}\n')
        # Моніторинг процесу
        self.ps_process = None
        QTimer.singleShot(500, self.find_psutil_process)
        self.res_timer.start(1000)

    def find_psutil_process(self):
        # Знайти процес через psutil
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if p.name().lower().startswith('python') and self.script_path in ' '.join(p.cmdline()):
                    self.ps_process = p
                    return
            except Exception:
                continue

    def update_resource_usage(self):
        if self.ps_process and self.ps_process.is_running():
            try:
                cpu = self.ps_process.cpu_percent() / psutil.cpu_count()
                mem = self.ps_process.memory_info().rss / 1024 / 1024
                self.res_label.setText(f'CPU: {cpu:.1f}% | RAM: {mem:.1f} MB')
            except Exception:
                self.res_label.setText('CPU: ? | RAM: ?')
        else:
            self.res_label.setText('CPU: 0% | RAM: 0 MB')

    def stop_script(self):
        if self.process and self.is_running:
            self.process.kill()
            self.process = None
            self.is_running = False
            self.status_label.setText('🔴 Статус: Зупинено')
            self.log_field.appendPlainText('⛔ Скрипт було зупинено вручну\n')
            self.res_timer.stop()
        else:
            CustomMessageBox.show_message('Інформація', 'Немає активного скрипта для зупинки.', 'info', self)

    def restart_script(self):
        if self.is_running:
            self.stop_script()
            QTimer.singleShot(400, self.start_script)
        else:
            self.start_script()

    def save_log(self):
        text = self.log_field.toPlainText()
        if not text.strip():
            CustomMessageBox.show_message('Інформація', 'Лог порожній.', 'info', self)
            return
        fname, _ = QFileDialog.getSaveFileName(self, 'Зберегти лог', f'log_{os.path.basename(self.script_path)}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt', 'Text files (*.txt)')
        if fname:
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(text)
            CustomMessageBox.show_message('Успіх', 'Лог збережено!', 'success', self)

    def schedule_run(self):
        from PyQt5.QtWidgets import QTimeEdit, QDialogButtonBox, QDialog
        class TimeDialog(QDialog):
            def __init__(self):
                super().__init__()
                self.setWindowTitle('Запланувати запуск')
                self.setMinimumWidth(220)
                v = QVBoxLayout(self)
                self.time_edit = QTimeEdit()
                self.time_edit.setDisplayFormat('HH:mm')
                v.addWidget(QLabel('Оберіть час запуску:'))
                v.addWidget(self.time_edit)
                btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                btns.accepted.connect(self.accept)
                btns.rejected.connect(self.reject)
                v.addWidget(btns)
        dlg = TimeDialog()
        if dlg.exec_() == QDialog.Accepted:
            t = dlg.time_edit.time()
            now = datetime.now()
            run_dt = now.replace(hour=t.hour(), minute=t.minute(), second=0, microsecond=0)
            if run_dt < now:
                run_dt = run_dt.replace(day=now.day+1)
            self.scheduled_time = run_dt
            self.sched_time_label.setText(f'Запуск о {run_dt.strftime("%H:%M")}')
            if self.timer:
                self.timer.stop()
            self.timer = QTimer()
            self.timer.timeout.connect(self.check_schedule)
            self.timer.start(1000)

    def check_schedule(self):
        if self.scheduled_time and datetime.now() >= self.scheduled_time:
            self.start_script()
            self.scheduled_time = None
            self.sched_time_label.setText('')
            if self.timer:
                self.timer.stop()

    def setup_telegram(self):
        from PyQt5.QtWidgets import QInputDialog
        token, ok1 = QInputDialog.getText(self, 'Telegram', 'Введіть токен бота:')
        if not ok1 or not token.strip():
            return
        chat_id, ok2 = QInputDialog.getText(self, 'Telegram', 'Введіть chat_id:')
        if not ok2 or not chat_id.strip():
            return
        self.telegram_token = token.strip()
        self.telegram_chat_id = chat_id.strip()
        self.tg_status.setText('Telegram підключено!')

    def send_telegram(self, text):
        if not self.telegram_token or not self.telegram_chat_id:
            return
        try:
            from telegram import Bot
            bot = Bot(token=self.telegram_token)
            bot.send_message(chat_id=self.telegram_chat_id, text=text)
        except Exception as e:
            self.tg_status.setText('❗ Telegram: помилка')

    def handle_stdout(self):
        if self.process:
            data = self.process.readAllStandardOutput().data().decode('utf-8')
            self.append_log(data)

    def handle_stderr(self):
        if self.process:
            data = self.process.readAllStandardError().data().decode('utf-8')
            self.append_log('❗ ' + data, is_error=True)

    def append_log(self, text, is_error=False):
        if is_error:
            self.log_field.setTextColor(QColor('#ff4444'))
            self.log_field.appendPlainText(text)
            self.log_field.setTextColor(QColor('#00ff88'))
        else:
            self.log_field.appendPlainText(text)
        self.log_field.verticalScrollBar().setValue(self.log_field.verticalScrollBar().maximum())

    def on_process_finished(self, exitCode, exitStatus):
        self.is_running = False
        self.res_timer.stop()
        if exitCode == 0:
            self.status_label.setText('✅ Статус: Завершено')
            self.log_field.appendPlainText('\n✅ Скрипт завершився успішно.')
            self.send_telegram(f'✅ Скрипт {os.path.basename(self.script_path)} завершився успішно.')
        else:
            self.status_label.setText('🔴 Статус: Завершено з помилкою')
            self.log_field.appendPlainText(f'\n❗ Скрипт завершився з помилкою (код {exitCode}).')
            self.send_telegram(f'❗ Скрипт {os.path.basename(self.script_path)} завершився з помилкою (код {exitCode}).')
        self.process = None
        self.ps_process = None
        self.res_label.setText('CPU: 0% | RAM: 0 MB')

    def closeEvent(self, event):
        if self.is_running:
            self.stop_script()
        self.close_callback(self)
        event.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('🧠 Керування Python-скриптами')
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(self.dark_stylesheet())
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.setMovable(True)
        self.tabs.setStyleSheet('QTabBar::tab { background: #232323; color: #dddddd; border-radius: 8px; padding: 8px 18px; margin: 2px; font-size: 14px; } QTabBar::tab:selected { background: #333355; color: #00ff88; } QTabWidget::pane { border: none; }')
        central = QWidget()
        layout = QHBoxLayout(central)
        # Зліва — дерево скриптів
        left_panel = QVBoxLayout()
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(SCRIPTS_DIR)
        self.fs_model.setNameFilters(['*.py'])
        self.fs_model.setNameFilterDisables(False)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(SCRIPTS_DIR))
        self.tree.setColumnHidden(1, True)
        self.tree.setColumnHidden(2, True)
        self.tree.setColumnHidden(3, True)
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet('QTreeView { background: #232323; color: #dddddd; border: none; font-size: 15px; } QTreeView::item:selected { background: #333355; }')
        self.tree.doubleClicked.connect(self.on_tree_double_click)
        left_panel.addWidget(self.tree, stretch=1)
        # Кнопки імпорту
        import_layout = QHBoxLayout()
        btn_zip = QPushButton('📦 Завантажити архів')
        btn_git = QPushButton('🌐 Імпорт з Git')
        for btn in [btn_zip, btn_git]:
            btn.setMinimumHeight(32)
            btn.setFont(QFont('Consolas', 10))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self.button_stylesheet())
        btn_zip.clicked.connect(self.import_zip)
        btn_git.clicked.connect(self.import_git)
        import_layout.addWidget(btn_zip)
        import_layout.addWidget(btn_git)
        left_panel.addLayout(import_layout)
        layout.addLayout(left_panel, 2)
        # Справа — вкладки
        layout.addWidget(self.tabs, 5)
        self.setCentralWidget(central)

    def dark_stylesheet(self):
        return '''
        QMainWindow, QWidget { background: #1e1e1e; color: #dddddd; }
        QScrollBar:vertical { background: #232323; width: 12px; margin: 0px; border-radius: 6px; }
        QScrollBar::handle:vertical { background: #333333; min-height: 20px; border-radius: 6px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        '''

    def button_stylesheet(self):
        return '''
        QPushButton {
            background: #3a3a3a;
            color: #dddddd;
            border: none;
            border-radius: 8px;
            padding: 8px 18px;
        }
        QPushButton:hover {
            background: #505050;
            color: #00ff88;
        }
        QPushButton:pressed {
            background: #222222;
        }
        '''

    def on_tree_double_click(self, index: QModelIndex):
        if not self.fs_model.isDir(index):
            script_path = self.fs_model.filePath(index)
            self.open_script_tab(script_path)

    def open_script_tab(self, script_path):
        # Якщо вже є вкладка для цього скрипта — активувати її
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, ScriptTab) and tab.script_path == script_path:
                self.tabs.setCurrentIndex(i)
                return
        tab = ScriptTab(script_path, self.close_tab_callback)
        self.tabs.addTab(tab, os.path.basename(script_path))
        self.tabs.setCurrentWidget(tab)

    def close_tab(self, index):
        tab = self.tabs.widget(index)
        if isinstance(tab, ScriptTab):
            if tab.is_running:
                tab.stop_script()
        self.tabs.removeTab(index)

    def close_tab_callback(self, tab):
        # Викликається при закритті ScriptTab
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == tab:
                self.tabs.removeTab(i)
                break

    def import_zip(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Оберіть ZIP-архів', '', 'ZIP files (*.zip)')
        if not file_path:
            return
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(SCRIPTS_DIR)
            CustomMessageBox.show_message('Успіх', 'Архів успішно розпаковано!', 'success', self)
            self.fs_model.refresh()
        except Exception as e:
            CustomMessageBox.show_message('Помилка', f'Не вдалося розпакувати архів: {e}', 'error', self)

    def import_git(self):
        url, ok = QInputDialog.getText(self, 'Імпорт з Git', 'Введіть git-лінк:')
        if not ok or not url.strip():
            return
        folder = QFileDialog.getExistingDirectory(self, 'Оберіть папку для клонування', SCRIPTS_DIR)
        if not folder:
            return
        try:
            subprocess.check_call(['git', 'clone', url, folder], shell=True)
            CustomMessageBox.show_message('Успіх', 'Репозиторій успішно клоновано!', 'success', self)
            self.fs_model.refresh()
        except Exception as e:
            CustomMessageBox.show_message('Помилка', f'Не вдалося клонувати репозиторій: {e}', 'error', self)

class SetupProgressDialog(QDialog):
    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Підготовка середовища')
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet('''
            QDialog { background: #232323; border-radius: 14px; }
            QLabel { color: #dddddd; font-size: 16px; }
            QProgressBar { background: #151515; color: #00ff88; border-radius: 8px; height: 24px; font-size: 15px; }
        ''')
        v = QVBoxLayout(self)
        self.label = QLabel('Підготовка...')
        self.label.setAlignment(Qt.AlignCenter)
        v.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(len(steps))
        v.addWidget(self.progress)
        self.setLayout(v)
        self.steps = steps
        self.current = 0
        self.success = True
        self.error_msg = ''
        self.thread = threading.Thread(target=self.run_steps)
        self.thread.start()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_thread)
        self.timer.start(200)

    def run_steps(self):
        try:
            for i, (desc, func) in enumerate(self.steps):
                self.label.setText(desc)
                func()
                self.current = i + 1
        except Exception as e:
            self.success = False
            self.error_msg = str(e)

    def check_thread(self):
        self.progress.setValue(self.current)
        if not self.thread.is_alive():
            self.timer.stop()
            self.accept()

def download_git_installer():
    url = 'https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe'
    fname = 'git-installer.exe'
    if os.path.exists(fname):
        return fname
    r = requests.get(url, stream=True)
    total = int(r.headers.get('content-length', 0))
    with open(fname, 'wb') as f:
        downloaded = 0
        for chunk in r.iter_content(1024*128):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
    return fname

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Підготовка середовища
    def pip_install(pkg):
        if importlib.util.find_spec(pkg) is None:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])
    steps = [
        ('Встановлення PyQt5...', lambda: pip_install('PyQt5')),
        ('Встановлення psutil...', lambda: pip_install('psutil')),
        ('Встановлення python-telegram-bot...', lambda: pip_install('python-telegram-bot')),
    ]
    need_git = shutil.which('git') is None
    if need_git:
        steps.append(('Завантаження Git...', download_git_installer))
    dlg = SetupProgressDialog(steps)
    dlg.exec_()
    if not dlg.success:
        CustomMessageBox.show_message('Помилка', f'Не вдалося підготувати середовище:\n{dlg.error_msg}', 'error')
        sys.exit(1)
    if need_git:
        fname = 'git-installer.exe'
        CustomMessageBox.show_message(
            'Встановлення Git',
            f'<b>Git не знайдено у вашій системі.</b><br><br>'
            f'Інсталятор <b>{fname}</b> вже завантажено і зараз буде відкрито.<br><br>'
            f'<b>Що робити далі?</b><br>'
            f'1. Дочекайтесь завершення встановлення Git (натискайте Next/Далі у майстрі).<br>'
            f'2. Після завершення <b>закрийте це вікно</b>.<br>'
            f'3. <b>Запустіть програму ще раз!</b><br><br>'
            f'Детальніше про Git: <a href="https://git-scm.com/doc">https://git-scm.com/doc</a>',
            'info'
        )
        os.startfile(fname)
        sys.exit(0)
    # Запуск основного вікна
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 