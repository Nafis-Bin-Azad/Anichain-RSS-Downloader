import sys
if sys.version_info[0] == 3 and sys.version_info[1] < 8:
    raise ImportError("This application requires Python 3.8 or higher")

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QComboBox, QScrollArea, 
                           QPushButton, QLineEdit, QGridLayout, QFrame,
                           QStackedWidget, QListWidget, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QImage, QPalette, QColor, QFont
import feedparser
import threading
import time
import requests
from qbittorrentapi import Client
from PIL import Image, ImageTk, UnidentifiedImageError
from io import BytesIO
import os
import json
from datetime import datetime, timedelta
import queue

SETTINGS_FILE = "settings.txt"
TRACKED_FILE = "tracked_anime.txt"
PLACEHOLDER_IMAGE = "placeholder.jpg"
CACHE_DIR = "image_cache"
MAX_RETRIES = 3
JIKAN_RATE_LIMIT = 1

# Create cache directory if it doesn't exist
os.makedirs(CACHE_DIR, exist_ok=True)

class RateLimiter:
    def __init__(self, calls_per_second=1):
        self.calls_per_second = calls_per_second
        self.last_call = 0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            current_time = time.time()
            time_since_last_call = current_time - self.last_call
            if time_since_last_call < 1.0 / self.calls_per_second:
                time.sleep(1.0 / self.calls_per_second - time_since_last_call)
            self.last_call = time.time()

jikan_limiter = RateLimiter(JIKAN_RATE_LIMIT)

def get_cached_image_path(title):
    # Create a safe filename from the title
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    return os.path.join(CACHE_DIR, f"{safe_title}.jpg")

def fetch_anime_image(title):
    # Clean up the title to get the actual anime name
    clean_title = title.replace("[SubsPlease]", "").strip()
    clean_title = clean_title.split(" - ")[0].strip()  # Get the part before the episode number
    clean_title = clean_title.split("[")[0].strip()    # Remove any remaining brackets

    # Check cache first
    cache_path = get_cached_image_path(clean_title)
    if os.path.exists(cache_path):
        print(f"Using cached image for {clean_title}")
        return cache_path

    for attempt in range(MAX_RETRIES):
        try:
            jikan_limiter.wait()  # Respect rate limit
            query_url = f"https://api.jikan.moe/v4/anime?q={clean_title}&limit=1"
            response = requests.get(query_url)
            response.raise_for_status()
            data = response.json()
            
            if data.get("data") and data["data"]:
                image_url = data["data"][0]["images"]["jpg"]["large_image_url"]
                if image_url:
                    # Download and cache the image
                    img_response = requests.get(image_url)
                    img_response.raise_for_status()
                    
                    # Save to cache
                    with open(cache_path, 'wb') as f:
                        f.write(img_response.content)
                    
                    print(f"Successfully cached image for {clean_title}")
                    return cache_path
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)  # Wait before retrying
                
        except Exception as e:
            print(f"Error fetching image for {clean_title} (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)  # Wait before retrying
    
    print(f"Failed to fetch image for {clean_title} after {MAX_RETRIES} attempts")
    return PLACEHOLDER_IMAGE

def fetch_rss_feed(url):
    try:
        feed = feedparser.parse(url)
        return feed
    except Exception as e:
        print(f"Error fetching RSS feed: {e}")
        return None

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "download_folder": os.getcwd(),
        "rss_url": "https://subsplease.org/rss/?r=1080",
        "qb_host": "http://127.0.0.1:8080",
        "qb_username": "admin",
        "qb_password": "adminadmin"
    }

def load_tracked_anime():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, "r") as f:
            return [line.strip() for line in f.readlines()]
    return []

def save_tracked_anime(tracked):
    with open(TRACKED_FILE, "w") as f:
        f.write("\n".join(tracked))

class ImageLoader(QThread):
    image_loaded = pyqtSignal(str, QPixmap)
    
    def __init__(self, title):
        super().__init__()
        self.title = title
        
    def run(self):
        image_path = fetch_anime_image(self.title)
        if image_path:
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(300, 420, Qt.AspectRatioMode.KeepAspectRatio, 
                                        Qt.TransformationMode.SmoothTransformation)
            self.image_loaded.emit(self.title, scaled_pixmap)

class AnimeCard(QFrame):
    clicked = pyqtSignal(str)
    
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
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
        
        # Load image
        self.loader = ImageLoader(clean_title)
        self.loader.image_loaded.connect(self.set_image)
        self.loader.start()
        
    def set_image(self, title, pixmap):
        if title == self.title.replace("[SubsPlease]", "").strip().split(" - ")[0]:
            self.image_label.setPixmap(pixmap)
            
    def mousePressEvent(self, event):
        self.clicked.emit(self.title)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime RSS Downloader")
        self.setMinimumSize(1200, 800)
        self.setup_ui()
        
    def setup_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Filter bar
        filter_bar = QWidget()
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setSpacing(20)
        
        filters = [
            ("Genres", ["Action", "Adventure", "Comedy", "Drama", "Fantasy", "Sci-Fi"]),
            ("Type", ["TV", "Movie", "OVA", "Special"]),
            ("Status", ["Airing", "Completed", "Upcoming"]),
            ("Years", [str(year) for year in range(2024, 2000, -1)]),
            ("Age restriction", ["All Ages", "PG-13", "R - 17+", "R+"])
        ]
        
        for label, values in filters:
            combo = QComboBox()
            combo.addItems(values)
            combo.setFixedWidth(150)
            combo.setStyleSheet("""
                QComboBox {
                    border: 1px solid #e0e0e0;
                    border-radius: 5px;
                    padding: 5px;
                    background: white;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
            """)
            
            filter_group = QWidget()
            group_layout = QVBoxLayout(filter_group)
            group_layout.setSpacing(5)
            
            label_widget = QLabel(label)
            label_widget.setStyleSheet("font-weight: bold;")
            
            group_layout.addWidget(label_widget)
            group_layout.addWidget(combo)
            
            filter_layout.addWidget(filter_group)
            
        filter_layout.addStretch()
        layout.addWidget(filter_bar)
        
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
        
        # Load initial data
        self.settings = load_settings()
        self.tracked_anime = load_tracked_anime()
        self.load_feed()
        
    def load_feed(self):
        feed = fetch_rss_feed(self.settings["rss_url"])
        if feed:
            self.display_anime_tiles(feed.entries)
            
    def display_anime_tiles(self, entries):
        # Clear existing items
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)
            
        # Add new items
        for i, entry in enumerate(entries):
            card = AnimeCard(entry.get("title", "No Title"))
            card.clicked.connect(self.on_anime_clicked)
            self.grid_layout.addWidget(card, i // 4, i % 4)
            
    def on_anime_clicked(self, title):
        if title not in self.tracked_anime:
            self.tracked_anime.append(title)
            save_tracked_anime(self.tracked_anime)
            QMessageBox.information(self, "Anime Tracked", f"Now tracking: {title}")
        else:
            QMessageBox.information(self, "Already Tracked", f"Already tracking: {title}")

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
    font = QFont("SF Pro Display", 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
