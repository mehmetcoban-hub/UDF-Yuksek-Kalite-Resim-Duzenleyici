import sys
import os
import re
import json
import base64
import io
import traceback
import zipfile
import urllib.request
import urllib.error
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PIL import Image

CURRENT_VERSION = "1.0.1"
GITHUB_REPO = "mehmetcoban-hub/UDF-Yuksek-Kalite-Resim-Duzenleyici"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def parse_version(v_str):
    v_clean = re.sub(r'^[vV]', '', str(v_str).strip())
    parts = []
    for p in re.findall(r'\d+', v_clean):
        try:
            parts.append(int(p))
        except ValueError:
            pass
    return parts if parts else [0]

def is_newer_version(latest_str, current_str):
    latest_parts = parse_version(latest_str)
    current_parts = parse_version(current_str)
    max_len = max(len(latest_parts), len(current_parts))
    latest_parts += [0] * (max_len - len(latest_parts))
    current_parts += [0] * (max_len - len(current_parts))
    return latest_parts > current_parts

class ImageViewer(QGraphicsView):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.item)
        self.setScene(self.scene)
        
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setStyleSheet("background-color: #e9ecef; border: 1px solid #ccc; border-radius: 8px;")

    def showEvent(self, event):
        super().showEvent(event)
        self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor
        
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp']:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fpath = url.toLocalFile()
                ext = os.path.splitext(fpath)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp']:
                    self.file_dropped.emit(fpath)
                    event.acceptProposedAction()
                    return


class PreviewDialog(QDialog):
    def __init__(self, title, img_data, original_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(1100, 750)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setStyleSheet("background-color: #f8f9fa;")
        
        layout = QVBoxLayout(self)
        lbl_info = QLabel("💡 <b>İpucu:</b> Yakınlaştırmak için <b>mouse tekerleğini</b> kullanın. Resmi kaydırmak için <b>basılı tutup sürükleyin</b>.")
        lbl_info.setAlignment(Qt.AlignCenter)
        lbl_info.setStyleSheet("font-size: 13px; color: #555; padding: 5px;")
        layout.addWidget(lbl_info)
        
        if original_data:
            compare_layout = QHBoxLayout()
            
            # Boyutları KB cinsinden hesapla
            orig_size_kb = len(original_data) / 1024
            new_size_kb = len(img_data) / 1024
            
            vbox_orig = QVBoxLayout()
            lbl_title_orig = QLabel(f"Orijinal Resim\nBoyut: {orig_size_kb:,.1f} KB")
            lbl_title_orig.setAlignment(Qt.AlignCenter)
            lbl_title_orig.setStyleSheet("font-weight: bold; font-size: 15px;")
            
            pix_orig = QPixmap()
            pix_orig.loadFromData(original_data)
            viewer_orig = ImageViewer(pix_orig)
            
            vbox_orig.addWidget(lbl_title_orig)
            vbox_orig.addWidget(viewer_orig)
            
            vbox_new = QVBoxLayout()
            lbl_title_new = QLabel(f"Sıkıştırılmış (Yeni) Resim\nBoyut: {new_size_kb:,.1f} KB")
            lbl_title_new.setAlignment(Qt.AlignCenter)
            lbl_title_new.setStyleSheet("font-weight: bold; font-size: 15px; color: #0078D7;")
            
            pix_new = QPixmap()
            pix_new.loadFromData(img_data)
            viewer_new = ImageViewer(pix_new)
            
            vbox_new.addWidget(lbl_title_new)
            vbox_new.addWidget(viewer_new)
            
            compare_layout.addLayout(vbox_orig)
            compare_layout.addLayout(vbox_new)
            layout.addLayout(compare_layout)
        else:
            # Tekli gösterim boyutu (Sadece orijinal önizleme yapıldığında)
            size_kb = len(img_data) / 1024
            lbl_title = QLabel(f"Resim Boyutu: {size_kb:,.1f} KB")
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet("font-weight: bold; font-size: 15px;")
            layout.addWidget(lbl_title)
            
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            viewer = ImageViewer(pixmap)
            layout.addWidget(viewer)

class UpdateCheckerThread(QThread):
    finished_signal = pyqtSignal(bool, dict, str)

    def __init__(self, current_ver, repo=GITHUB_REPO, parent=None):
        super().__init__(parent)
        self.current_ver = current_ver
        self.repo = repo

    def run(self):
        if not self.repo:
            self.finished_signal.emit(
                False, {}, 
                "GitHub deposu henüz tanımlanmamış.\n\nGüncellemeleri otomatik kontrol etmek için kaynak kodundaki GITHUB_REPO değişkenine GitHub depo adınızı ('kullanici/repo') ekleyebilirsiniz."
            )
            return

        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "UDF-Resim-Duzenleyici-App"}
            )
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    tag_name = data.get("tag_name", "")
                    release_name = data.get("name", tag_name)
                    body = data.get("body", "Bu sürüm için detaylı not girilmedi.")
                    html_url = data.get("html_url", "")
                    
                    has_update = is_newer_version(tag_name, self.current_ver)
                    info = {
                        "version": tag_name,
                        "title": release_name,
                        "notes": body,
                        "url": html_url
                    }
                    self.finished_signal.emit(has_update, info, "")
                else:
                    self.finished_signal.emit(False, {}, f"Sunucu yanıt kodu: {response.status}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.finished_signal.emit(False, {}, f"'{self.repo}' deposunda henüz yayınlanmış bir sürüm (Release) bulunamadı.")
            else:
                self.finished_signal.emit(False, {}, f"Sunucu hatası: HTTP {e.code}")
        except Exception as e:
            self.finished_signal.emit(False, {}, f"İnternet bağlantısı kurulamadı:\n{str(e)}")

class UpdateDialog(QDialog):
    def __init__(self, current_ver, new_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎉 Yeni Sürüm Mevcut!")
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog { background-color: #f8f9fa; }
            QPushButton { border-radius: 6px; padding: 8px 16px; font-weight: bold; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        icon_lbl = QLabel("🚀")
        icon_lbl.setStyleSheet("font-size: 34px;")
        header_layout.addWidget(icon_lbl)
        
        title_box = QVBoxLayout()
        title_lbl = QLabel(new_info.get('title', 'Yeni Sürüm Yayınlandı!'))
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078D7;")
        ver_lbl = QLabel(f"Mevcut: <b>v{current_ver}</b>  ➜  Yeni Sürüm: <b style='color: #2e7d32; font-size: 14px;'>{new_info.get('version', '')}</b>")
        ver_lbl.setStyleSheet("font-size: 13px; color: #555;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(ver_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        notes_title = QLabel("📝 Yenilikler ve Sürüm Notları:")
        notes_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        layout.addWidget(notes_title)
        
        text_browser = QTextBrowser()
        text_browser.setPlainText(new_info.get('notes', 'Bu sürüm için detaylı not girilmedi.'))
        text_browser.setStyleSheet("background-color: white; border: 1px solid #ced4da; border-radius: 6px; padding: 10px; font-size: 12px;")
        text_browser.setMaximumHeight(180)
        layout.addWidget(text_browser)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_later = QPushButton("Daha Sonra")
        btn_later.setStyleSheet("background-color: #e9ecef; color: #495057; border: 1px solid #ced4da;")
        btn_later.clicked.connect(self.reject)
        btn_layout.addWidget(btn_later)
        
        btn_download = QPushButton("⬇️ Güncellemeyi İndir")
        btn_download.setStyleSheet("background-color: #0078D7; color: white; border: none; font-size: 13px;")
        download_url = new_info.get('url', '')
        btn_download.clicked.connect(lambda: self.open_download(download_url))
        btn_layout.addWidget(btn_download)
        
        layout.addLayout(btn_layout)

    def open_download(self, url):
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.accept()

class AboutDialog(QDialog):
    def __init__(self, current_ver, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hakkında")
        self.setFixedSize(440, 300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("background-color: #ffffff;")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)
        
        icon_path = resource_path("app_icon.png")
        if os.path.exists(icon_path):
            lbl_icon = QLabel()
            lbl_icon.setPixmap(QPixmap(icon_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl_icon.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl_icon)
            
        title = QLabel("UDF Yüksek Kalite Resim Düzenleyici")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078D7;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        lbl_ver = QLabel(f"Sürüm: v{current_ver}")
        lbl_ver.setStyleSheet("color: #666; font-size: 13px; font-weight: bold;")
        lbl_ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_ver)
        
        desc = QLabel("UYAP (.udf) evraklarındaki resimleri yüksek kalitede\ndüzenlemek ve dosya boyutunu optimize etmek için geliştirilmiştir.")
        desc.setStyleSheet("color: #555; font-size: 12px;")
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        btn_close = QPushButton("Tamam")
        btn_close.setFixedWidth(100)
        btn_close.setStyleSheet("background-color: #0078D7; color: white; border-radius: 5px; padding: 6px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignCenter)

class UDFResimcisi(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UDF Yüksek Kalite Resim Düzenleyici")
        icon_path = resource_path("app_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = resource_path("app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.setGeometry(80, 80, 1180, 780)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QMainWindow { background-color: #eaeff2; }
            QPushButton { border-radius: 6px; padding: 7px 12px; font-weight: bold; }
            QScrollArea { border: none; background-color: #eaeff2; }
        """)
        
        self.udf_content = ""
        self.images_data = [] 
        self.is_zip_format = False
        self.zip_other_files = {} 
        self.original_file_size = 0 
        self.last_dir = "" 
        self.current_udf_path = ""
        self.updater_thread = None
        
        self.initUI()
        QTimer.singleShot(2500, lambda: self.check_for_updates(silent=True))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext == '.udf':
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fpath = url.toLocalFile()
                if fpath.lower().endswith('.udf'):
                    self.last_dir = os.path.dirname(fpath)
                    self.process_udf(fpath)
                    event.acceptProposedAction()
                    return

    def create_menu_bar(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar { background-color: #ffffff; color: #333; font-size: 13px; border-bottom: 1px solid #ddd; }
            QMenuBar::item { padding: 6px 14px; background: transparent; }
            QMenuBar::item:selected { background-color: #0078D7; color: white; border-radius: 4px; }
            QMenu { background-color: #ffffff; border: 1px solid #ccc; font-size: 13px; padding: 4px; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background-color: #e9ecef; color: black; border-radius: 4px; }
        """)

        # Dosya Menüsü
        file_menu = menubar.addMenu("📁 Dosya")
        action_open = QAction("UDF İçe Aktar...", self)
        action_open.setShortcut("Ctrl+O")
        action_open.triggered.connect(self.load_udf)
        file_menu.addAction(action_open)

        self.action_save = QAction("Yeni UDF Olarak Kaydet...", self)
        self.action_save.setShortcut("Ctrl+S")
        self.action_save.triggered.connect(self.save_udf)
        self.action_save.setEnabled(False)
        file_menu.addAction(self.action_save)

        file_menu.addSeparator()
        action_exit = QAction("Çıkış", self)
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

        # Araçlar Menüsü
        tools_menu = menubar.addMenu("🛠️ Araçlar")
        self.action_auto_compress = QAction("⚡ 9.5 MB'a Otomatik Sığdır", self)
        self.action_auto_compress.setShortcut("Ctrl+Shift+O")
        self.action_auto_compress.triggered.connect(self.auto_compress_to_limit)
        self.action_auto_compress.setEnabled(False)
        tools_menu.addAction(self.action_auto_compress)

        self.action_export_all = QAction("📦 Tüm Resimleri Bir Klasöre Kaydet...", self)
        self.action_export_all.setShortcut("Ctrl+Shift+E")
        self.action_export_all.triggered.connect(self.export_all_images)
        self.action_export_all.setEnabled(False)
        tools_menu.addAction(self.action_export_all)

        # Yardım Menüsü
        help_menu = menubar.addMenu("❓ Yardım")
        action_update = QAction("🔄 Güncellemeleri Denetle...", self)
        action_update.triggered.connect(lambda: self.check_for_updates(silent=False))
        help_menu.addAction(action_update)

        help_menu.addSeparator()
        action_about = QAction("ℹ️ Hakkında", self)
        action_about.triggered.connect(self.show_about)
        help_menu.addAction(action_about)

    def initUI(self):
        self.create_menu_bar()
        self.statusBar().showMessage(f"Hazır | Sürüm: v{CURRENT_VERSION}")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(14, 10, 14, 14)
        self.main_layout.setSpacing(10)

        self.top_panel = QHBoxLayout()
        self.top_panel.setSpacing(8)
        
        self.btn_import = QPushButton("📂 UDF İçe Aktar")
        self.btn_import.setStyleSheet("background-color: #ffffff; border: 1px solid #ced4da; font-size: 13px; padding: 9px 16px;")
        self.btn_import.clicked.connect(self.load_udf)

        self.btn_auto_compress = QPushButton("⚡ 9.5 MB'a Sığdır")
        self.btn_auto_compress.setStyleSheet("""
            QPushButton { background-color: #ff9800; color: white; border: none; font-size: 13px; padding: 9px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #f57c00; }
            QPushButton:disabled { background-color: #e0e0e0; color: #a0a0a0; }
        """)
        self.btn_auto_compress.setToolTip("UYAP 10 MB sınırını aşmamak için resimleri otomatik sıkıştırır")
        self.btn_auto_compress.clicked.connect(self.auto_compress_to_limit)
        self.btn_auto_compress.setEnabled(False)

        self.btn_export_all = QPushButton("📦 Tüm Resimleri Kaydet")
        self.btn_export_all.setStyleSheet("""
            QPushButton { background-color: #ffffff; border: 1px solid #ced4da; font-size: 13px; padding: 9px 16px; }
            QPushButton:disabled { color: #aaa; border-color: #eee; }
        """)
        self.btn_export_all.setToolTip("Evraktaki tüm resimleri toplu olarak bir klasöre kaydeder")
        self.btn_export_all.clicked.connect(self.export_all_images)
        self.btn_export_all.setEnabled(False)

        self.btn_update = QPushButton("🔄 Güncelleme Kontrolü")
        self.btn_update.setStyleSheet("background-color: #ffffff; border: 1px solid #ced4da; font-size: 13px; padding: 9px 14px;")
        self.btn_update.setToolTip("Yeni sürüm olup olmadığını denetle")
        self.btn_update.clicked.connect(lambda: self.check_for_updates(silent=False))
        
        self.lbl_size_info = QLabel("İşlem Sonrası Toplam Boyut\n0.00 MB")
        self.lbl_size_info.setStyleSheet("background-color: white; border-radius: 10px; padding: 8px 16px; font-size: 13px; font-weight: bold;")
        self.lbl_size_info.setAlignment(Qt.AlignCenter)
        
        self.btn_save = QPushButton("💾 Yeni UDF'yi Kaydet")
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #0078D7; color: white; font-size: 13px; padding: 9px 20px; font-weight: bold; }
            QPushButton:hover { background-color: #0063b1; }
            QPushButton:disabled { background-color: #b0c4de; color: #f0f0f0; }
        """)
        self.btn_save.clicked.connect(self.save_udf)
        self.btn_save.setEnabled(False)

        self.top_panel.addWidget(self.btn_import)
        self.top_panel.addWidget(self.btn_auto_compress)
        self.top_panel.addWidget(self.btn_export_all)
        self.top_panel.addWidget(self.btn_update)
        self.top_panel.addStretch()
        self.top_panel.addWidget(self.lbl_size_info)
        self.top_panel.addWidget(self.btn_save)
        self.main_layout.addLayout(self.top_panel)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: #eaeff2;") 
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_layout.setSpacing(14)
        self.scroll_area.setWidget(self.scroll_widget)
        self.main_layout.addWidget(self.scroll_area)
        
        self.show_empty_placeholder()

    def show_empty_placeholder(self):
        for i in reversed(range(self.scroll_layout.count())): 
            widget = self.scroll_layout.itemAt(i).widget()
            if widget: widget.deleteLater()

        empty_frame = QFrame()
        empty_frame.setStyleSheet("background-color: white; border-radius: 12px; border: 2px dashed #b0bec5; margin: 30px;")
        empty_layout = QVBoxLayout(empty_frame)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setContentsMargins(40, 60, 40, 60)
        empty_layout.setSpacing(14)

        lbl_icon = QLabel("📂")
        lbl_icon.setStyleSheet("font-size: 56px;")
        lbl_icon.setAlignment(Qt.AlignCenter)

        lbl_msg = QLabel("Lütfen bir UDF Dosyası Seçin veya Buraya Sürükleyip Bırakın")
        lbl_msg.setStyleSheet("font-size: 16px; font-weight: bold; color: #37474f;")
        lbl_msg.setAlignment(Qt.AlignCenter)

        lbl_hint = QLabel("UDF içindeki tüm resimler taranacak; kaliteleri tek tek veya tek tıkla\nUYAP 10 MB sınırının altına çekilebilecek şekilde optimize edilebilecektir.")
        lbl_hint.setStyleSheet("font-size: 13px; color: #78909c; line-height: 1.4;")
        lbl_hint.setAlignment(Qt.AlignCenter)

        btn_select = QPushButton("📂 UDF Dosyası Seç...")
        btn_select.setCursor(QCursor(Qt.PointingHandCursor))
        btn_select.setStyleSheet("background-color: #0078D7; color: white; padding: 10px 24px; font-size: 13px; font-weight: bold; border-radius: 6px;")
        btn_select.clicked.connect(self.load_udf)

        empty_layout.addWidget(lbl_icon)
        empty_layout.addWidget(lbl_msg)
        empty_layout.addWidget(lbl_hint)
        empty_layout.addSpacing(10)
        empty_layout.addWidget(btn_select, alignment=Qt.AlignCenter)

        self.scroll_layout.addWidget(empty_frame)

    def check_for_updates(self, silent=False):
        if self.updater_thread and self.updater_thread.isRunning():
            if not silent:
                QMessageBox.information(self, "Bilgi", "Güncelleme kontrolü zaten devam ediyor...")
            return

        if not silent:
            self.statusBar().showMessage("Güncellemeler denetleniyor...", 3000)

        self.updater_thread = UpdateCheckerThread(CURRENT_VERSION, GITHUB_REPO, self)
        self.updater_thread.finished_signal.connect(
            lambda has_up, info, err: self.on_update_check_finished(has_up, info, err, silent)
        )
        self.updater_thread.start()

    def on_update_check_finished(self, has_update, info, error_msg, silent):
        if has_update:
            dialog = UpdateDialog(CURRENT_VERSION, info, parent=self)
            dialog.exec_()
        elif error_msg:
            if not silent:
                QMessageBox.warning(self, "Güncelleme Kontrolü", error_msg)
        else:
            if not silent:
                QMessageBox.information(
                    self, 
                    "Güncelleme Kontrolü", 
                    f"Harika! En güncel sürümü kullanıyorsunuz.\n\nMevcut Sürüm: v{CURRENT_VERSION}"
                )

    def show_about(self):
        AboutDialog(CURRENT_VERSION, parent=self).exec_()

    def load_udf(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "UDF Dosyası Seç", self.last_dir, "UDF Dosyaları (*.udf);;Tüm Dosyalar (*)", options=options)
        if file_path:
            self.last_dir = os.path.dirname(file_path) 
            self.process_udf(file_path)

    def process_udf(self, file_path):
        for i in reversed(range(self.scroll_layout.count())): 
            widget = self.scroll_layout.itemAt(i).widget()
            if widget: widget.deleteLater()
            
        self.images_data.clear()
        self.zip_other_files.clear()
        self.is_zip_format = False
        self.original_file_size = os.path.getsize(file_path)
        self.current_udf_path = file_path

        try:
            if zipfile.is_zipfile(file_path):
                self.is_zip_format = True
                with zipfile.ZipFile(file_path, 'r') as z:
                    for file_name in z.namelist():
                        if file_name == 'content.xml':
                            self.udf_content = z.read(file_name).decode('utf-8', errors='ignore')
                        else:
                            self.zip_other_files[file_name] = z.read(file_name)
                
                if not self.udf_content:
                    raise Exception("ZIP okundu ancak içinde 'content.xml' bulunamadı.")
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    self.udf_content = f.read()
            
            pattern = re.compile(r'([A-Za-z0-9+/\n\r]{1000,}={0,2})')
            matches = pattern.finditer(self.udf_content)
            
            for match in matches:
                b64_raw = match.group(1)
                b64_clean = re.sub(r'\s+', '', b64_raw)
                try:
                    img_data = base64.b64decode(b64_clean)
                    img = Image.open(io.BytesIO(img_data))
                    data_dict = {
                        'original_b64': b64_raw,
                        'new_b64': b64_raw,
                        'original_bytes': img_data,
                        'new_bytes': img_data,
                        'match_span': match.span(),
                        'quality': 100,
                        'rotation': 0,
                        'is_modified': False
                    }
                    self.images_data.append(data_dict)
                    
                    try:
                        self.add_image_row(len(self.images_data) - 1, img_data, data_dict)
                    except Exception:
                        pass
                        
                except Exception:
                    pass 
            
            has_images = len(self.images_data) > 0
            self.btn_save.setEnabled(has_images)
            self.btn_auto_compress.setEnabled(has_images)
            self.btn_export_all.setEnabled(has_images)
            if hasattr(self, 'action_save'):
                self.action_save.setEnabled(has_images)
            if hasattr(self, 'action_auto_compress'):
                self.action_auto_compress.setEnabled(has_images)
            if hasattr(self, 'action_export_all'):
                self.action_export_all.setEnabled(has_images)
                
            self.update_size_info()
            
            if not has_images:
                self.show_empty_placeholder()
                QMessageBox.warning(self, "Uyarı", "UDF dosyası okundu ancak içinde gömülü resim bulunamadı.")
            else:
                self.statusBar().showMessage(f"Dosya Yüklendi: {os.path.basename(file_path)} ({len(self.images_data)} resim)", 5000)
                
        except Exception as e:
            self.show_empty_placeholder()
            QMessageBox.critical(self, "Hata", f"Dosya okunurken bir hata oluştu:\n{str(e)}")

    def add_image_row(self, index, img_data, data_dict):
        row_widget = QFrame()
        row_widget.setStyleSheet("""
            QFrame#ImageCard { 
                background-color: white; 
                border-radius: 12px; 
                border: 1px solid #cfd8dc;
            }
        """)
        row_widget.setObjectName("ImageCard")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(16, 16, 16, 16)
        
        # --- SOL: Orijinal Resim ---
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignTop)
        left_layout.setSpacing(6)

        lbl_title = QLabel(f"📄 UDF İçindeki Resim {index + 1}")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #263238;")
        
        lbl_original_img = ClickableLabel()
        lbl_original_img.setCursor(QCursor(Qt.PointingHandCursor))
        lbl_original_img.setToolTip("Orijinal resmi tam boyutta görüntülemek için tıklayın\n(Yeni resim sürükleyip bırakabilirsiniz)")
        pixmap = QPixmap()
        pixmap.loadFromData(img_data)
        lbl_original_img.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lbl_original_img.setStyleSheet("border: 2px solid #cfd8dc; border-radius: 6px; background-color: #fafafa;")
        
        orig_size_mb = len(img_data) / (1024 * 1024)
        lbl_orig_size = QLabel(f"Orijinal: {orig_size_mb:.2f} MB")
        lbl_orig_size.setStyleSheet("color: #546e7a; font-size: 12px; font-weight: bold;")
        lbl_orig_size.setAlignment(Qt.AlignCenter)
        
        left_layout.addWidget(lbl_title)
        left_layout.addWidget(lbl_original_img)
        left_layout.addWidget(lbl_orig_size)

        # --- ORTA: İşlem ve Araçlar ---
        mid_layout = QVBoxLayout()
        mid_layout.setSpacing(10)
        
        lbl_q_header = QLabel("🎯 <b>Sıkıştırma Oranı:</b>")
        lbl_q_header.setStyleSheet("color: #37474f; font-size: 12px;")
        
        quality_layout = QHBoxLayout()
        btn_q100 = QPushButton("Orijinal\n(%100)")
        btn_q75 = QPushButton("Yüksek\n(%75)")
        btn_q50 = QPushButton("Orta\n(%50)")
        btn_q25 = QPushButton("Düşük\n(%25)")
        
        q_buttons = [btn_q100, btn_q75, btn_q50, btn_q25]
        for btn in q_buttons:
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { background-color: #f1f3f5; border: 1px solid #ced4da; padding: 6px; font-size: 11px; border-radius: 6px; }
                QPushButton:checked { background-color: #0078D7; color: white; font-weight: bold; border-color: #0078D7; }
                QPushButton:hover:!checked { background-color: #e9ecef; }
            """)
            quality_layout.addWidget(btn)
        
        btn_q100.setChecked(True)
        
        q_group = QButtonGroup(self)
        q_group.addButton(btn_q100, 100)
        q_group.addButton(btn_q75, 75)
        q_group.addButton(btn_q50, 50)
        q_group.addButton(btn_q25, 25)

        rot_revert_layout = QHBoxLayout()
        btn_rot_left = QPushButton("↶ 90° Sola")
        btn_rot_left.setStyleSheet("background-color: #ffffff; border: 1px solid #ced4da; padding: 6px 12px; font-size: 12px;")
        btn_rot_left.setToolTip("Resmi 90 derece sola döndürür")
        
        btn_rot_right = QPushButton("↷ 90° Sağa")
        btn_rot_right.setStyleSheet("background-color: #ffffff; border: 1px solid #ced4da; padding: 6px 12px; font-size: 12px;")
        btn_rot_right.setToolTip("Resmi 90 derece sağa döndürür")
        
        btn_revert = QPushButton("↩️ Orijinale Dön")
        btn_revert.setStyleSheet("""
            QPushButton { background-color: #fff3e0; color: #e65100; border: 1px solid #ffe0b2; padding: 6px 12px; font-size: 12px; }
            QPushButton:hover { background-color: #ffe0b2; }
            QPushButton:disabled { background-color: #f5f5f5; color: #bdbdbd; border-color: #eeeeee; }
        """)
        btn_revert.setToolTip("Tüm kalite ve döndürme değişikliklerini geri alıp orijinal haline sıfırlar")
        btn_revert.setEnabled(False)
        
        rot_revert_layout.addWidget(btn_rot_left)
        rot_revert_layout.addWidget(btn_rot_right)
        rot_revert_layout.addWidget(btn_revert)

        file_actions_layout = QHBoxLayout()
        btn_change = QPushButton("🔄 Farklı Resim Seç...")
        btn_change.setStyleSheet("background-color: #e3f2fd; color: #0277bd; border: 1px solid #b3e5fc; padding: 7px 14px; font-size: 12px;")
        btn_change.setToolTip("UDF içindeki bu resmin yerine bilgisayarınızdan yeni bir görsel seçin")
        
        btn_export = QPushButton("💾 Resmi Kaydet")
        btn_export.setStyleSheet("background-color: #f1f8e9; color: #33691e; border: 1px solid #dcedc8; padding: 7px 14px; font-size: 12px;")
        btn_export.setToolTip("Bu resmi bilgisayarınıza JPG olarak kaydedin")
        
        file_actions_layout.addWidget(btn_change)
        file_actions_layout.addWidget(btn_export)

        hint_lbl = QLabel("💡 <i>İpucu: Sağdaki kutucuğa doğrudan yeni resim sürükleyip bırakabilirsiniz.</i>")
        hint_lbl.setStyleSheet("color: #90a4ae; font-size: 11px;")

        mid_layout.addWidget(lbl_q_header)
        mid_layout.addLayout(quality_layout)
        mid_layout.addLayout(rot_revert_layout)
        mid_layout.addLayout(file_actions_layout)
        mid_layout.addWidget(hint_lbl)
        mid_layout.addStretch()

        # --- SAĞ: Yeni / İşlenmiş Resim ---
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignTop)
        right_layout.setSpacing(6)
        
        lbl_right_title = QLabel("✨ İşlenmiş / Yeni Resim")
        lbl_right_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078D7;")
        
        lbl_new_img = ClickableLabel()
        lbl_new_img.setCursor(QCursor(Qt.PointingHandCursor))
        lbl_new_img.setToolTip("Büyük boyutta karşılaştırma için tıklayın (Sürükle & Bırak desteklenir)")
        lbl_new_img.setFixedSize(150, 150)
        lbl_new_img.setAlignment(Qt.AlignCenter)
        lbl_new_img.setText("Henüz bir işlem\nyapılmadı") 
        lbl_new_img.setStyleSheet("border: 2px dashed #b0bec5; border-radius: 6px; color: #78909c; background-color: #fafafa; font-size: 11px;")
        
        lbl_new_size = QLabel("- MB")
        lbl_new_size.setStyleSheet("color: gray; font-size: 12px; font-weight: bold;")
        lbl_new_size.setAlignment(Qt.AlignCenter)
        
        right_layout.addWidget(lbl_right_title)
        right_layout.addWidget(lbl_new_img)
        right_layout.addWidget(lbl_new_size)

        # Referansları data_dict içine saklayalım
        data_dict['lbl_new_img'] = lbl_new_img
        data_dict['lbl_new_size'] = lbl_new_size
        data_dict['btn_group'] = q_group
        data_dict['btn_revert'] = btn_revert

        # Sinyal bağlantıları
        btn_q100.clicked.connect(lambda: self.set_quality(index, 100))
        btn_q75.clicked.connect(lambda: self.set_quality(index, 75))
        btn_q50.clicked.connect(lambda: self.set_quality(index, 50))
        btn_q25.clicked.connect(lambda: self.set_quality(index, 25))

        btn_rot_left.clicked.connect(lambda: self.rotate_image(index, -90))
        btn_rot_right.clicked.connect(lambda: self.rotate_image(index, 90))
        btn_revert.clicked.connect(lambda: self.revert_to_original(index))
        btn_change.clicked.connect(lambda: self.change_image_dialog(index))
        btn_export.clicked.connect(lambda: self.export_single_image(index))

        lbl_original_img.clicked.connect(lambda: PreviewDialog("Orijinal Resim (Yakınlaştırılabilir)", self.images_data[index]['original_bytes'], parent=self).exec_())
        lbl_new_img.clicked.connect(lambda: self.show_comparison(index))

        # Sürükle-Bırak ile resim değiştirme
        lbl_new_img.file_dropped.connect(lambda fpath: self.change_image_from_path(index, fpath))
        lbl_original_img.file_dropped.connect(lambda fpath: self.change_image_from_path(index, fpath))

        row_layout.addLayout(left_layout, 1)
        row_layout.addSpacing(16)
        row_layout.addLayout(mid_layout, 2)
        row_layout.addSpacing(16)
        row_layout.addLayout(right_layout, 1)
        
        self.scroll_layout.addWidget(row_widget)

    def set_quality(self, index, quality):
        self.images_data[index]['quality'] = quality
        self.render_processed_image(index)

    def rotate_image(self, index, angle):
        cur_rot = self.images_data[index].get('rotation', 0)
        self.images_data[index]['rotation'] = (cur_rot + angle) % 360
        self.render_processed_image(index)

    def change_image_dialog(self, index):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Yeni Resim Seç", self.last_dir, 
            "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp *.webp)", options=options
        )
        if file_path:
            self.last_dir = os.path.dirname(file_path) 
            self.change_image_from_path(index, file_path)

    def change_image_from_path(self, index, file_path):
        self.images_data[index]['new_image_path'] = file_path
        self.render_processed_image(index)

    def render_processed_image(self, index):
        data = self.images_data[index]
        quality = data.get('quality', 100)
        rotation = data.get('rotation', 0)
        
        has_new_file = 'new_image_path' in data
        is_modified = has_new_file or quality != 100 or rotation != 0
        data['is_modified'] = is_modified
        
        if not is_modified:
            self.revert_to_original(index)
            return

        try:
            if has_new_file:
                img = Image.open(data['new_image_path'])
            else:
                img = Image.open(io.BytesIO(data['original_bytes']))
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Görsel açılamadı:\n{str(e)}")
            return

        # Saat yönünde döndürme için negatif açı verilir
        if rotation != 0:
            img = img.rotate(-rotation, expand=True)

        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=quality)
        processed_bytes = img_byte_arr.getvalue()
        
        data['new_bytes'] = processed_bytes
        data['new_b64'] = base64.b64encode(processed_bytes).decode('utf-8')

        lbl_img = data.get('lbl_new_img')
        lbl_size = data.get('lbl_new_size')
        btn_revert = data.get('btn_revert')
        q_group = data.get('btn_group')

        if q_group:
            btn = q_group.button(quality)
            if btn: btn.setChecked(True)

        if lbl_img:
            pixmap = QPixmap()
            pixmap.loadFromData(processed_bytes)
            lbl_img.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl_img.setStyleSheet("border: 2px solid #4CAF50; border-radius: 6px; background-color: #fafafa;")
            
        if lbl_size:
            orig_size = len(data['original_bytes'])
            new_size = len(processed_bytes)
            new_mb = new_size / (1024 * 1024)
            diff_pct = ((orig_size - new_size) / orig_size) * 100 if orig_size > 0 else 0
            if diff_pct > 0:
                lbl_size.setText(f"Yeni: {new_mb:.2f} MB (-%{diff_pct:.0f})")
                lbl_size.setStyleSheet("color: #2e7d32; font-size: 12px; font-weight: bold;")
            elif diff_pct < 0:
                lbl_size.setText(f"Yeni: {new_mb:.2f} MB (+%{-diff_pct:.0f})")
                lbl_size.setStyleSheet("color: #c62828; font-size: 12px; font-weight: bold;")
            else:
                lbl_size.setText(f"Yeni: {new_mb:.2f} MB")
                lbl_size.setStyleSheet("color: #546e7a; font-size: 12px; font-weight: bold;")
                
        if btn_revert:
            btn_revert.setEnabled(True)
            
        self.update_size_info()

    def revert_to_original(self, index):
        data = self.images_data[index]
        data['new_bytes'] = data['original_bytes']
        data['new_b64'] = data['original_b64']
        data['quality'] = 100
        data['rotation'] = 0
        data.pop('new_image_path', None)
        data['is_modified'] = False

        lbl_img = data.get('lbl_new_img')
        lbl_size = data.get('lbl_new_size')
        btn_revert = data.get('btn_revert')
        q_group = data.get('btn_group')

        if q_group:
            b100 = q_group.button(100)
            if b100: b100.setChecked(True)

        if lbl_img:
            lbl_img.clear()
            lbl_img.setText("Henüz bir işlem\nyapılmadı")
            lbl_img.setStyleSheet("border: 2px dashed #b0bec5; border-radius: 6px; color: #78909c; background-color: #fafafa; font-size: 11px;")

        if lbl_size:
            lbl_size.setText("- MB")
            lbl_size.setStyleSheet("color: gray; font-size: 12px; font-weight: bold;")

        if btn_revert:
            btn_revert.setEnabled(False)

        self.update_size_info()

    def show_comparison(self, index):
        data = self.images_data[index]
        if data.get('is_modified'):
            PreviewDialog("Karşılaştırma (Yakınlaştırılabilir)", data['new_bytes'], original_data=data['original_bytes'], parent=self).exec_()
        else:
            QMessageBox.information(
                self, "Bilgi", 
                "Karşılaştırma yapmak için önce kaliteyi değiştirin, resmi döndürün veya 'Farklı Resim Seç' butonunu kullanın."
            )

    def export_single_image(self, index):
        data = self.images_data[index]
        bytes_to_save = data['new_bytes'] if data.get('is_modified') else data['original_bytes']
        
        default_name = os.path.join(self.last_dir, f"resim_{index + 1}.jpg") if self.last_dir else f"resim_{index + 1}.jpg"
        save_path, _ = QFileDialog.getSaveFileName(
            self, f"Resim {index + 1}'i Kaydet", default_name, "JPEG (*.jpg);;Tüm Dosyalar (*)"
        )
        if save_path:
            self.last_dir = os.path.dirname(save_path)
            try:
                with open(save_path, 'wb') as f:
                    f.write(bytes_to_save)
                QMessageBox.information(self, "Başarılı", f"Resim başarıyla kaydedildi:\n{save_path}")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Resim kaydedilemedi:\n{str(e)}")

    def export_all_images(self):
        if not self.images_data:
            QMessageBox.warning(self, "Uyarı", "Dışa aktarılacak resim bulunamadı. Lütfen önce bir UDF dosyası açın.")
            return

        folder = QFileDialog.getExistingDirectory(self, "Resimlerin Kaydedileceği Klasörü Seç", self.last_dir)
        if folder:
            self.last_dir = folder
            success_count = 0
            for idx, data in enumerate(self.images_data):
                bytes_to_save = data['new_bytes'] if data.get('is_modified') else data['original_bytes']
                out_path = os.path.join(folder, f"resim_{idx + 1}.jpg")
                try:
                    with open(out_path, 'wb') as f:
                        f.write(bytes_to_save)
                    success_count += 1
                except Exception:
                    pass
            QMessageBox.information(
                self, "Başarılı", 
                f"{success_count} adet resim klasöre başarıyla kaydedildi:\n{folder}"
            )

    def get_estimated_total_bytes(self):
        diff_bytes = 0
        for data in self.images_data:
            diff_bytes += len(data['new_b64'].encode('utf-8')) - len(data['original_b64'].encode('utf-8'))
        estimated_bytes = self.original_file_size + diff_bytes
        return max(0, estimated_bytes)

    def auto_compress_to_limit(self):
        if not self.images_data:
            QMessageBox.warning(self, "Uyarı", "İşlem yapılacak resim bulunamadı. Lütfen önce bir UDF açın.")
            return

        target_bytes = int(9.5 * 1024 * 1024)
        current_total = self.get_estimated_total_bytes()
        
        if current_total <= target_bytes:
            cur_mb = current_total / (1024 * 1024)
            QMessageBox.information(
                self, "Bilgi", 
                f"Evrak boyutu zaten 9.5 MB sınırının altında ({cur_mb:.2f} MB).\nEkstra sıkıştırmaya gerek yok."
            )
            return

        # En büyük resimlerden başlayarak kaliteyi kademeli düşürelim
        indices = list(range(len(self.images_data)))
        indices.sort(key=lambda i: len(self.images_data[i]['new_bytes']), reverse=True)

        for quality in [75, 50, 25]:
            for idx in indices:
                cur_q = self.images_data[idx].get('quality', 100)
                if cur_q > quality:
                    self.images_data[idx]['quality'] = quality
                    self.render_processed_image(idx)
                    if self.get_estimated_total_bytes() <= target_bytes:
                        break
            if self.get_estimated_total_bytes() <= target_bytes:
                break

        final_bytes = self.get_estimated_total_bytes()
        final_mb = final_bytes / (1024 * 1024)
        
        if final_bytes <= target_bytes:
            QMessageBox.information(
                self, "🎉 Başarılı!", 
                f"Tüm resimler başarıyla optimize edildi!\n\n"
                f"Yeni Toplam Boyut: {final_mb:.2f} MB\n"
                f"(UYAP 10 MB sınırının altına çekildi)"
            )
        else:
            QMessageBox.warning(
                self, "Uyarı", 
                f"Resimler maksimum sıkıştırma (%25) seviyesine getirildi ancak toplam boyut {final_mb:.2f} MB kaldı.\n"
                f"UYAP sınırını yakalamak için bazı resimleri 'Farklı Resim Seç' ile daha küçük boyutlu alternatiflerle değiştirebilirsiniz."
            )

    def update_size_info(self):
        estimated_bytes = self.get_estimated_total_bytes()
        estimated_mb = estimated_bytes / (1024 * 1024)
        
        has_images = len(self.images_data) > 0
        if hasattr(self, 'btn_auto_compress'):
            self.btn_auto_compress.setEnabled(has_images)
            self.action_auto_compress.setEnabled(has_images)
        if hasattr(self, 'btn_export_all'):
            self.btn_export_all.setEnabled(has_images)
            self.action_export_all.setEnabled(has_images)
            
        if estimated_mb > 10.0:
            self.lbl_size_info.setText(f"İşlem Sonrası Toplam Boyut\n{estimated_mb:.2f} MB (UYAP Sınırı Aşıldı!)")
            self.lbl_size_info.setStyleSheet("background-color: #ffebee; border-radius: 10px; padding: 8px 16px; font-size: 13px; font-weight: bold; color: #c62828; border: 2px solid #ef5350;")
        elif estimated_mb > 9.5:
            self.lbl_size_info.setText(f"İşlem Sonrası Toplam Boyut\n{estimated_mb:.2f} MB (Sınıra Çok Yakın)")
            self.lbl_size_info.setStyleSheet("background-color: #fff8e1; border-radius: 10px; padding: 8px 16px; font-size: 13px; font-weight: bold; color: #f57f17; border: 2px solid #ffb74d;")
        else:
            self.lbl_size_info.setText(f"İşlem Sonrası Toplam Boyut\n{estimated_mb:.2f} MB")
            self.lbl_size_info.setStyleSheet("background-color: white; border-radius: 10px; padding: 8px 16px; font-size: 13px; font-weight: bold; color: #2e7d32; border: 1px solid #c8e6c9;")

    def save_udf(self):
        options = QFileDialog.Options()
        default_save_path = os.path.join(self.last_dir, "duzenlenmis_evrak.udf") if self.last_dir else "duzenlenmis_evrak.udf"
        save_path, _ = QFileDialog.getSaveFileName(self, "Yeni UDF Olarak Kaydet", default_save_path, "UDF Dosyaları (*.udf)", options=options)
        
        if save_path:
            self.last_dir = os.path.dirname(save_path) 
            new_content = self.udf_content
            sorted_data = sorted(self.images_data, key=lambda x: x['match_span'][0], reverse=True)
            
            for data in sorted_data:
                start, end = data['match_span']
                new_content = new_content[:start] + data['new_b64'] + new_content[end:]
                
            try:
                if self.is_zip_format:
                    with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as z:
                        z.writestr('content.xml', new_content.encode('utf-8'))
                        for file_name, file_data in self.zip_other_files.items():
                            z.writestr(file_name, file_data)
                else:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                        
                QMessageBox.information(self, "Başarılı", "Yeni UDF dosyası başarıyla kaydedildi!")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Dosya kaydedilirken bir hata oluştu:\n{str(e)}")


if __name__ == '__main__':
    try:
        import ctypes
        myappid = 'udf.resim.duzenleyici.app.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)
    icon_path = resource_path("app_icon.ico")
    if not os.path.exists(icon_path):
        icon_path = resource_path("app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    ex = UDFResimcisi()
    ex.show()
    sys.exit(app.exec_())