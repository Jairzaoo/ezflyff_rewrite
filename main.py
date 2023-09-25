import configparser
import os
import random
import sys
import traceback
import time
import win32api
import win32gui
from PyQt5.QtCore import QUrl, Qt, pyqtSlot, QThreadPool, QRunnable
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtGui import QIcon

from loguru import logger

import win32con
from win32gui import FindWindow, SendMessage
from key_codes import KEY_MAP
from PIL import ImageGrab

# https://stackoverflow.com/questions/67599432/setting-the-same-icon-as-application-icon-in-task-bar-for-pyqt5-application
# Get taskbar to display the correct icon
import ctypes
myappid = 'mycompany.myproduct.subproduct.version' # arbitrary string
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

# Full path to directory where the script is launched from.
ezflyff_dir = sys.path[0]


class Worker(QRunnable):
    """
    Worker thread
    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.
    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function
    """
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs


    @pyqtSlot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """
        try:
            self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()


class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("ezFlyff")
        self.setWindowIcon(QIcon(f"{ezflyff_dir}\\flyff.ico"))
        self.flyff_url = "https://universe.flyff.com/play"

        self.threadpool = QThreadPool.globalInstance()
        self.toggle_key_listeners = {}


    def create_new_window(self, url, profile_name, profile_settings):
        """Create game window(QWebEngineView) with current profile's settings."""
        logger.info("create_new_window called")
        browser = QWebEngineView()
        browser.setAttribute(Qt.WA_DeleteOnClose)
        browser.setWindowTitle(f"ezFlyff - {profile_name}")

        # Apply user settings from profile_settings.ini
        browser.resize(int(profile_settings["window"]["window_width"]), int(profile_settings["window"]["window_height"]))
        browser.move(int(profile_settings["window"]["window_x_pos"]), int(profile_settings["window"]["window_y_pos"]))

        profile = QWebEngineProfile(profile_name, browser)
        #profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.132 Safari/537.36")
        profile.setCachePath(f"{ezflyff_dir}\\profiles\\{profile_name}\\cache")
        profile.setPersistentStoragePath(f"{ezflyff_dir}\\profiles\\{profile_name}\\storage")
        page = QWebEnginePage(profile, browser)

        browser.setPage(page)
        browser.load(QUrl(url))
        browser.show()
        return browser


    def start_assist_loop(self, profile_name, profile_settings):
        worker = Worker(assist_loop, profile_name, profile_settings, self.toggle_key_listeners)
        self.threadpool.start(worker)

    
    def start_toggle_key_listener(self, profile_name, toggle_key):
        worker = Worker(toggle_key_listener, profile_name, toggle_key, self.toggle_key_listeners)
        self.threadpool.start(worker)


def toggle_key_listener(profile_name, toggle_key, toggle_key_listeners):
    """Toggles key listener."""
    while True:
        if win32api.GetAsyncKeyState(KEY_MAP[toggle_key]):
            if toggle_key_listeners[profile_name] == True:
                logger.info(f"{profile_name} - Assist mode disabled")
                toggle_key_listeners[profile_name] = False
                time.sleep(2)
            else:
                logger.info(f"{profile_name} - Assist mode enabled")
                toggle_key_listeners[profile_name] = True
                time.sleep(2)


def create_settings_dir(profile_name):
    """Creates the profile directory and subdirectories if they don't exist."""
    logger.info("create_settings_dir called")
    dir_path = f"{ezflyff_dir}\\profiles\\{profile_name}"

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        logger.info(f"Created directory {dir_path}")
    else:
        logger.info(f"Directory {dir_path} already exists")


def get_profile_settings(profile_name):
    """Loads profile settings from profile_settings.ini or creates a default if it doesn't exist."""
    logger.info("get_profile_settings called")
    config = configparser.ConfigParser()
    settings_path = f"{ezflyff_dir}\\profiles\\{profile_name}\\settings.ini"
    if not os.path.isfile(settings_path):
        logger.info(f"Creating settings.ini for profile {profile_name}")
        # Add window settings to settings.ini
        config.add_section("window")
        config.set("window", "window_width", "800")
        config.set("window", "window_height", "600")
        config.set("window", "window_x_pos", "0")
        config.set("window", "window_y_pos", "0")
        # Add assist settings to settings.ini
        config.add_section("assist")
        config.set("assist", "toggle_key", "-")
        config.set("assist", "heal_hotkey", "3")
        config.set("assist", "heal_interval", "2")
        config.set("assist", "buff_hotkey", "4")
        config.set("assist", "buff_interval", "300")
        config.set("assist", "mp_hotkey", "7")
        config.set("assist", "mp_interval", "2")
        with open(settings_path, "w") as config_file:
            config.write(config_file)
    config.read(settings_path)
    return config


def press_key(handle, hotkey):
    """Gets key map for hotkey, presses the hotkey, and waits a randomized fraction of a second."""
    hotkey = KEY_MAP[hotkey]
    SendMessage(handle, win32con.WM_KEYDOWN, hotkey, 0)
    time.sleep(0.5 + random.random())
    SendMessage(handle, win32con.WM_KEYUP, hotkey, 0)


def get_game_handle(profile_name):
    """Gets handle to game window."""
    logger.debug("get_game_handle called")
    game_window_name = f"ezFlyff - {profile_name}"
    game_window_class = "Qt5152QWindowIcon"
    return FindWindow(game_window_class, game_window_name)


def assist_loop(profile_name, profile_settings, toggle_key_listeners):
    """Loop that runs on separate thread to heal and buff target.(off until hotkey pressed)"""
    logger.debug("assist_loop called")
    # map hotkeys to key codes
    toggle_key = profile_settings["assist"]["toggle_key"]
    heal_hotkey = profile_settings["assist"]["heal_hotkey"]
    heal_interval = int(profile_settings["assist"]["heal_interval"])
    buff_hotkey = profile_settings["assist"]["buff_hotkey"]
    buff_interval = int(profile_settings["assist"]["buff_interval"])
    mp_hotkey = profile_settings["assist"]["mp_hotkey"]
    mp_interval = int(profile_settings["assist"]["mp_interval"])
    # Get game handle
    game_handle = get_game_handle(profile_name)

    def buff_character():
        """Presses the buff hotkey and waits for the buff interval."""
        logger.info(f"pressing buff hotkey {buff_hotkey} on {profile_name}")
        press_key(game_handle, buff_hotkey)
        logger.info("Sleeping 5 seconds while character buffs")
        time.sleep(5 + random.random())  # To make sure buffs arent interrupted by a heal
        buff_timer = time.perf_counter()  # Reset buff timer
        return buff_timer

    def heal_character():
        x, y = 495, 72 #DONT MOVE THE HP/MP BAR OF SELECTED CHARACTER FOR HEAL 
        xmp, ymp = 130,91 # x <->, y /\ \/

         # Specify the coordinates you want to check
        heal_color_threshold = (0,0,0)
        corvida = (188,24,62)
        left, top, right, bottom = win32gui.GetClientRect(game_handle)
        x_offset = left
        y_offset = top
        screenshot = ImageGrab.grab(bbox=(x_offset, y_offset, right, bottom))
        pixel_color = screenshot.getpixel((x - x_offset, y - y_offset)) 
        mp_color = screenshot.getpixel((xmp - x_offset, ymp - y_offset))  
        #logger.info(f"Rgb color for hp{pixel_color}")
        #logger.info(f"Rgb color for mp{mp_color}")

        if pixel_color == heal_color_threshold:

            """Presses the heal hotkey and sleeps for the heal interval."""
            logger.info(f"Sleeping {heal_interval} seconds...")
            time.sleep(heal_interval + random.random())
            logger.info(f"pressing heal hotkey {heal_hotkey} on {profile_name}.")
            press_key(game_handle, heal_hotkey)

        if mp_color == heal_color_threshold:

            logger.info(f"pressing mp hotkey {mp_hotkey} on {profile_name}.")
            press_key(game_handle, mp_hotkey)
            time.sleep(mp_interval + random.random())

        else:

            logger.info("Vida e Mana estao cheias")
            time.sleep(1)

        
        


    while True:
        # Loop until toggle key is pressed to turn on auto assist
        if toggle_key_listeners[profile_name] == True:
            # Initial buff
            buff_timer = buff_character()
            # Loop until toggle key is pressed again
            while True:
                if toggle_key_listeners[profile_name] == True:
                    # 95% sure heal_character() is blocking keyboard input. Maybe a QTimer could fix it but didn't have a lot of luck...
                    # Tried a QThread but then you need to put the sleep in this thread which I believe is the root of the problem.
                    heal_character()
                    buff_timer_check = time.perf_counter()
                    if buff_timer_check - buff_timer > buff_interval:
                        buff_timer = buff_character()
                else:
                    break



def load_profiles():
    """Loads profiles from profiles directory or creates a 'default' if none exist."""
    profile_list = []
    profiles_path = f"{ezflyff_dir}\\profiles"
    if not os.path.exists(profiles_path):
        os.makedirs(profiles_path)
        logger.info(f"Created directory {profiles_path}")

    profiles = os.listdir(profiles_path)
    if len(profiles) == 0:
        logger.info("No profiles found. Creating default profile.")
        create_settings_dir("default")
        profiles.append("default")
    else:
        for profile in profiles:
            profile_list.append(profile)
    return profiles


if __name__ == "__main__":
    views = []
    profiles = load_profiles()

    app = QApplication(sys.argv)
    app.setApplicationName("ezFlyff")
    app.setWindowIcon(QIcon(f"{ezflyff_dir}\\flyff.ico"))

    window = MainWindow()
    for profile in profiles:
        logger.info(f"Launching {profile}")
        create_settings_dir(profile)
        settings = get_profile_settings(profile)
        view = window.create_new_window(window.flyff_url, profile, settings)
        views.append(view)  # Keep reference to window to prevent it from closing
        window.start_assist_loop(profile, settings)
        window.toggle_key_listeners[profile] = False
        window.start_toggle_key_listener(profile, settings['assist']['toggle_key'])
    sys.exit(app.exec_())
