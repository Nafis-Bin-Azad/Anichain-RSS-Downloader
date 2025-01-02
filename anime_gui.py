import sys
if sys.version_info[0] == 3 and sys.version_info[1] < 8:
    raise ImportError("This application requires Python 3.8 or higher")

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QTabWidget, QScrollArea, 
                           QPushButton, QLineEdit, QGridLayout, QFrame,
                           QStackedWidget, QListWidget, QFileDialog, QMessageBox,
                           QTextEdit, QDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QImage, QPalette, QColor, QFont
import os
from datetime import datetime
from anime_backend import AnimeManager

class ImageLoader(QThread):
    image_loaded = pyqtSignal(str, QPixmap)
    
    def __init__(self, title, manager):
        super().__init__()
        self.title = title
        self.manager = manager
        
    def run(self):
        image_path = self.manager.fetch_anime_image(self.title)
        if image_path:
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(300, 420, Qt.AspectRatioMode.KeepAspectRatio, 
                                        Qt.TransformationMode.SmoothTransformation)
            self.image_loaded.emit(self.title, scaled_pixmap)

class AnimeCard(QFrame):
    clicked = pyqtSignal(str)
    
    def __init__(self, title, manager, parent=None):
        super().__init__(parent)
        self.title = title
        self.manager = manager
        self.setup_ui()
        
    def setup_ui(self):
        self.setObjectName("animeCard")
        self.setStyleSheet("""
            #animeCard {
                background-color: white;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
            }
            #animeCard:hover {
                border: 1px solid #007AFF;
            }
            QLabel {
                color: #333333;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(300, 420)
        layout.addWidget(self.image_label)
        
        # Title
        clean_title = self.title.replace("[SubsPlease]", "").strip().split(" - ")[0]
        title_label = QLabel(clean_title)
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        # Episode info
        episode_info = self.title.split(" - ")[-1].split("[")[0].strip()
        episode_label = QLabel(episode_info)
        episode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        episode_label.setStyleSheet("color: #666666;")
        layout.addWidget(episode_label)
        
        # Status indicator
        status_text = "✓ Tracked" if self.title in self.manager.tracked_anime else "Click to Track"
        self.status_label = QLabel(status_text)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(
            "color: green;" if self.title in self.manager.tracked_anime else "color: blue;"
        )
        layout.addWidget(self.status_label)
        
        # Load image
        self.loader = ImageLoader(clean_title, self.manager)
        self.loader.image_loaded.connect(self.set_image)
        self.loader.start()
        
    def set_image(self, title, pixmap):
        if title == self.title.replace("[SubsPlease]", "").strip().split(" - ")[0]:
            self.image_label.setPixmap(pixmap)
            
    def mousePressEvent(self, event):
        self.clicked.emit(self.title)

class QBittorrentDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("qBittorrent Connection")
        self.setModal(True)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Add message
        message = QLabel("Please configure qBittorrent connection to continue:")
        message.setStyleSheet("font-weight: bold; color: #007AFF;")
        layout.addWidget(message)
        
        # Host
        layout.addWidget(QLabel("Host:"))
        self.host_entry = QLineEdit(self.manager.settings["qb_host"])
        layout.addWidget(self.host_entry)
        
        # Username
        layout.addWidget(QLabel("Username:"))
        self.username_entry = QLineEdit(self.manager.settings["qb_username"])
        layout.addWidget(self.username_entry)
        
        # Password
        layout.addWidget(QLabel("Password:"))
        self.password_entry = QLineEdit(self.manager.settings["qb_password"])
        self.password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_entry)
        
        # Connect button
        connect_button = QPushButton("Connect")
        connect_button.clicked.connect(self.try_connect)
        connect_button.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #0066CC;
            }
        """)
        layout.addWidget(connect_button)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red;")
        layout.addWidget(self.status_label)
        
    def try_connect(self):
        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("color: blue;")
        QApplication.processEvents()
        
        # Update settings
        new_settings = self.manager.settings.copy()
        new_settings.update({
            "qb_host": self.host_entry.text(),
            "qb_username": self.username_entry.text(),
            "qb_password": self.password_entry.text()
        })
        self.manager.save_settings(new_settings)
        
        # Try connection
        if self.manager.setup_qbittorrent():
            self.status_label.setText("Connected successfully!")
            self.status_label.setStyleSheet("color: green;")
            QTimer.singleShot(1000, self.accept)
        else:
            self.status_label.setText("Connection failed. Please check your settings.")
            self.status_label.setStyleSheet("color: red;")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.manager = AnimeManager()
        self.setWindowTitle("Anime RSS Downloader")
        self.setMinimumSize(1200, 800)
        
        # Setup basic UI first so we have status labels
        self.setup_ui()
        
        # Ensure qBittorrent connection before proceeding
        if not self.ensure_qbittorrent_connection():
            sys.exit(1)
            
        self.setup_timers()
        
    def ensure_qbittorrent_connection(self):
        if not self.manager.setup_qbittorrent():
            dialog = QBittorrentDialog(self.manager, self)
            result = dialog.exec()
            return result == QDialog.DialogCode.Accepted
        return True
        
    def check_qbittorrent_connection(self):
        if not self.manager.qb_client or not self.manager.setup_qbittorrent():
            self.qb_status_label.setText("qBittorrent: Disconnected ✗")
            self.qb_status_label.setStyleSheet("color: red; font-weight: bold;")
            
            # Show reconnection dialog
            if self.ensure_qbittorrent_connection():
                self.qb_status_label.setText("qBittorrent: Connected ✓")
                self.qb_status_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                QMessageBox.critical(self, "Connection Error", 
                    "Failed to connect to qBittorrent. The application will now close.")
                self.close()
        
    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Create tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Add tabs
        self.setup_anime_tab()
        self.setup_schedule_tab()
        self.setup_tracked_tab()
        self.setup_downloads_tab()
        self.setup_settings_tab()
        
    def setup_anime_tab(self):
        anime_tab = QWidget()
        layout = QVBoxLayout(anime_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Scroll area for anime grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f5f5f7;
            }
            QScrollBar:vertical {
                border: none;
                background: #f5f5f7;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #c1c1c1;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a8a8a8;
            }
        """)
        
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(20)
        scroll.setWidget(self.grid_widget)
        
        layout.addWidget(scroll)
        self.tabs.addTab(anime_tab, "Anime")
        
        # Load initial feed
        self.load_feed()
        
    def setup_schedule_tab(self):
        schedule_tab = QWidget()
        layout = QVBoxLayout(schedule_tab)
        
        # Header frame
        header_frame = QWidget()
        header_layout = QHBoxLayout(header_frame)
        
        self.current_time_label = QLabel("Current Time: ")
        self.current_time_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.current_time_label)
        
        # Initialize qBittorrent status
        self.qb_status_label = QLabel()
        if self.manager.qb_client:
            self.qb_status_label.setText("qBittorrent: Connected ✓")
            self.qb_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.qb_status_label.setText("qBittorrent: Disconnected ✗")
            self.qb_status_label.setStyleSheet("color: red; font-weight: bold;")
        header_layout.addWidget(self.qb_status_label, alignment=Qt.AlignmentFlag.AlignRight)
        
        layout.addWidget(header_frame)
        
        self.next_anime_label = QLabel("Next Episode: ")
        self.next_anime_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.next_anime_label)
        
        self.schedule_text = QTextEdit()
        self.schedule_text.setReadOnly(True)
        self.schedule_text.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.schedule_text)
        
        self.tabs.addTab(schedule_tab, "Schedule")
        self.load_schedule()
        
    def setup_tracked_tab(self):
        tracked_tab = QWidget()
        layout = QVBoxLayout(tracked_tab)
        
        self.tracked_list = QListWidget()
        self.tracked_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:hover {
                background-color: #f5f5f7;
            }
        """)
        layout.addWidget(self.tracked_list)
        
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_tracked)
        remove_button.setStyleSheet("""
            QPushButton {
                background-color: #ff3b30;
                color: white;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #ff453a;
            }
        """)
        layout.addWidget(remove_button, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.tabs.addTab(tracked_tab, "Tracked")
        self.update_tracked_list()
        
    def setup_downloads_tab(self):
        downloads_tab = QWidget()
        layout = QVBoxLayout(downloads_tab)
        
        self.folder_label = QLabel(f"Download Folder: {self.manager.settings['download_folder']}")
        self.folder_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.folder_label)
        
        self.downloads_list = QListWidget()
        self.downloads_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:hover {
                background-color: #f5f5f7;
            }
        """)
        layout.addWidget(self.downloads_list)
        
        self.tabs.addTab(downloads_tab, "Downloads")
        self.update_downloads_list()
        
    def setup_settings_tab(self):
        settings_tab = QWidget()
        layout = QVBoxLayout(settings_tab)
        layout.setSpacing(15)
        
        # Download folder
        folder_frame = QWidget()
        folder_layout = QHBoxLayout(folder_frame)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        
        self.folder_entry = QLineEdit(self.manager.settings["download_folder"])
        folder_layout.addWidget(self.folder_entry)
        
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(browse_button)
        
        layout.addWidget(QLabel("Download Folder:"))
        layout.addWidget(folder_frame)
        
        # RSS URL
        layout.addWidget(QLabel("RSS URL:"))
        self.rss_entry = QLineEdit(self.manager.settings["rss_url"])
        layout.addWidget(self.rss_entry)
        
        # qBittorrent settings
        layout.addWidget(QLabel("qBittorrent Settings"))
        
        self.qb_host_entry = QLineEdit(self.manager.settings["qb_host"])
        layout.addWidget(QLabel("Host:"))
        layout.addWidget(self.qb_host_entry)
        
        self.qb_username_entry = QLineEdit(self.manager.settings["qb_username"])
        layout.addWidget(QLabel("Username:"))
        layout.addWidget(self.qb_username_entry)
        
        self.qb_password_entry = QLineEdit(self.manager.settings["qb_password"])
        self.qb_password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(QLabel("Password:"))
        layout.addWidget(self.qb_password_entry)
        
        # Save button
        save_button = QPushButton("Save Settings")
        save_button.clicked.connect(self.save_settings)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #0066CC;
            }
        """)
        layout.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignRight)
        
        layout.addStretch()
        self.tabs.addTab(settings_tab, "Settings")
        
    def setup_timers(self):
        # Add qBittorrent connection check every minute
        self.qb_timer = QTimer()
        self.qb_timer.timeout.connect(self.check_qbittorrent_connection)
        self.qb_timer.start(60000)  # Check every minute
        
        # Existing timers
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        
        self.schedule_timer = QTimer()
        self.schedule_timer.timeout.connect(self.load_schedule)
        self.schedule_timer.start(300000)
        
        self.downloads_timer = QTimer()
        self.downloads_timer.timeout.connect(self.update_downloads_list)
        self.downloads_timer.start(60000)
        
        self.feed_timer = QTimer()
        self.feed_timer.timeout.connect(self.load_feed)
        self.feed_timer.start(300000)
        
    def load_feed(self):
        feed = self.manager.fetch_rss_feed()
        if feed:
            self.display_anime_tiles(feed.entries)
            
    def display_anime_tiles(self, entries):
        # Clear existing items
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)
            
        # Add new items
        for i, entry in enumerate(entries):
            card = AnimeCard(entry.get("title", "No Title"), self.manager)
            card.clicked.connect(self.on_anime_clicked)
            self.grid_layout.addWidget(card, i // 4, i % 4)
            
    def on_anime_clicked(self, title):
        # Find the torrent link for this anime
        feed = self.manager.fetch_rss_feed()
        if not feed:
            QMessageBox.warning(self, "Error", "Could not fetch RSS feed")
            return
            
        for entry in feed.entries:
            if entry.get("title") == title:
                # Found matching entry, try to download
                if not self.manager.qb_client:
                    if not self.ensure_qbittorrent_connection():
                        QMessageBox.critical(self, "Error", "Not connected to qBittorrent")
                        return
                
                if self.manager.add_torrent(entry.get("link")):
                    if title not in self.manager.tracked_anime:
                        self.manager.tracked_anime.append(title)
                        self.manager.save_tracked_anime(self.manager.tracked_anime)
                        self.update_tracked_list()
                    QMessageBox.information(self, "Success", 
                        f"Started downloading: {title}\nAdded to tracked anime.")
                else:
                    QMessageBox.warning(self, "Error", 
                        f"Failed to start download for: {title}")
                return
                
        QMessageBox.warning(self, "Error", f"Could not find torrent link for: {title}")
        
    def update_clock(self):
        current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        self.current_time_label.setText(f"Current Time: {current_time}")
        
    def load_schedule(self):
        schedule_data = self.manager.fetch_schedule()
        if not schedule_data:
            self.schedule_text.setText("Failed to load schedule. Will retry in 5 minutes.")
            return
            
        current_time = datetime.utcnow()
        next_anime = None
        schedule_text = ""
        
        for day, shows in schedule_data["schedule"].items():
            schedule_text += f"\n{day}:\n"
            for show in shows:
                time_str = show['time']
                title = show['title']
                
                anime_time = datetime.strptime(time_str, "%H:%M")
                anime_time = anime_time.replace(
                    year=current_time.year,
                    month=current_time.month,
                    day=current_time.day
                )
                
                if anime_time > current_time and (next_anime is None or anime_time < next_anime[1]):
                    next_anime = (title, anime_time)
                    schedule_text += f"  → {time_str} UTC - {title} (Next)\n"
                else:
                    schedule_text += f"  {time_str} UTC - {title}\n"
        
        self.schedule_text.setText(schedule_text)
        
        if next_anime:
            time_until = next_anime[1] - current_time
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            self.next_anime_label.setText(
                f"Next Episode: {next_anime[0]} at {next_anime[1].strftime('%H:%M UTC')} (in {hours}h {minutes}m)"
            )
            
    def update_tracked_list(self):
        self.tracked_list.clear()
        self.tracked_list.addItems(self.manager.tracked_anime)
        
    def remove_tracked(self):
        current_item = self.tracked_list.currentItem()
        if current_item:
            anime = current_item.text()
            self.manager.tracked_anime.remove(anime)
            self.manager.save_tracked_anime(self.manager.tracked_anime)
            self.update_tracked_list()
            
    def update_downloads_list(self):
        self.downloads_list.clear()
        self.downloads_list.addItems(self.manager.get_downloaded_files())
        
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Download Folder",
            self.manager.settings["download_folder"]
        )
        if folder:
            self.folder_entry.setText(folder)
            
    def save_settings(self):
        new_settings = {
            "download_folder": self.folder_entry.text(),
            "rss_url": self.rss_entry.text(),
            "qb_host": self.qb_host_entry.text(),
            "qb_username": self.qb_username_entry.text(),
            "qb_password": self.qb_password_entry.text()
        }
        
        try:
            self.manager.save_settings(new_settings)
            QMessageBox.information(self, "Success", "Settings saved successfully")
            
            # Try to reconnect to qBittorrent if settings changed
            if (new_settings["qb_host"] != self.manager.settings["qb_host"] or
                new_settings["qb_username"] != self.manager.settings["qb_username"] or
                new_settings["qb_password"] != self.manager.settings["qb_password"]):
                if self.manager.setup_qbittorrent():
                    self.qb_status_label.setText("qBittorrent: Connected ✓")
                    self.qb_status_label.setStyleSheet("color: green; font-weight: bold;")
                else:
                    self.qb_status_label.setText("qBittorrent: Disconnected ✗")
                    self.qb_status_label.setStyleSheet("color: red; font-weight: bold;")
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Set color scheme
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f5f7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#333333"))
    app.setPalette(palette)
    
    # Set font
    font = QFont(".AppleSystemUIFont", 10)  # Use system font
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
