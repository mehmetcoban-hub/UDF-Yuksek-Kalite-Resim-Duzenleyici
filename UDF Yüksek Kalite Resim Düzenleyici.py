import sys
import os
import re
import base64
import io
import traceback
import zipfile
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PIL import Image

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
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

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

class UDFResimcisi(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UDF Yüksek Kalite Resim Düzenleyici")
        self.setGeometry(100, 100, 1150, 750)
        self.setStyleSheet("""
            QMainWindow { background-color: #eaeff2; }
            QPushButton { border-radius: 8px; padding: 8px; font-weight: bold; }
            QScrollArea { border: none; background-color: #eaeff2; }
        """)
        
        self.udf_content = ""
        self.images_data = [] 
        self.is_zip_format = False
        self.zip_other_files = {} 
        self.original_file_size = 0 
        self.last_dir = "" 
        
        self.initUI()

    def initUI(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.top_panel = QHBoxLayout()
        
        self.btn_import = QPushButton("📂 UDF İçe Aktar")
        self.btn_import.setStyleSheet("background-color: #ffffff; border: 1px solid #ccc; font-size: 14px; padding: 10px 20px;")
        self.btn_import.clicked.connect(self.load_udf)
        
        self.lbl_size_info = QLabel("İşlem Sonrası Toplam Boyut\n0.00 MB")
        self.lbl_size_info.setStyleSheet("background-color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: bold;")
        self.lbl_size_info.setAlignment(Qt.AlignCenter)
        
        self.btn_save = QPushButton("💾 Yeni UDF'yi Kaydet")
        self.btn_save.setStyleSheet("background-color: #0078D7; color: white; font-size: 14px; padding: 10px 20px;")
        self.btn_save.clicked.connect(self.save_udf)
        self.btn_save.setEnabled(False)

        self.top_panel.addWidget(self.btn_import)
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
        self.scroll_layout.setSpacing(15)
        self.scroll_area.setWidget(self.scroll_widget)
        self.main_layout.addWidget(self.scroll_area)

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
                        'quality': 100
                    }
                    self.images_data.append(data_dict)
                    
                    try:
                        self.add_image_row(len(self.images_data) - 1, img_data, data_dict)
                    except Exception:
                        pass
                        
                except Exception:
                    pass 
            
            self.update_size_info()
            if len(self.images_data) > 0:
                self.btn_save.setEnabled(True)
            else:
                self.btn_save.setEnabled(False)
                QMessageBox.warning(self, "Uyarı", "UDF okundu ancak içinde resim bulunamadı.")
                
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Dosya okunurken bir hata oluştu:\n{str(e)}")

    def add_image_row(self, index, img_data, data_dict):
        row_widget = QFrame()
        row_widget.setStyleSheet("QFrame { background-color: white; border-radius: 12px; }")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(15, 15, 15, 15)
        
        left_layout = QVBoxLayout()
        lbl_title = QLabel(f"UDF İçindeki Resim {index + 1}")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        
        lbl_original_img = ClickableLabel()
        lbl_original_img.setCursor(QCursor(Qt.PointingHandCursor))
        lbl_original_img.setToolTip("Önizleme için tıklayın (Yakınlaştırılabilir)")
        pixmap = QPixmap()
        pixmap.loadFromData(img_data)
        lbl_original_img.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lbl_original_img.setStyleSheet("border: 2px solid #ddd; border-radius: 5px;")
        
        orig_size_mb = len(img_data) / (1024 * 1024)
        lbl_orig_size = QLabel(f"Resim Boyutu: {orig_size_mb:.2f} MB")
        lbl_orig_size.setStyleSheet("color: gray; font-size: 11px;")
        
        left_layout.addWidget(lbl_title)
        left_layout.addWidget(lbl_original_img)
        left_layout.addWidget(lbl_orig_size)
        left_layout.setAlignment(Qt.AlignTop)

        mid_layout = QVBoxLayout()
        
        btn_change = QPushButton("🔄 Yeni Resim Seç")
        btn_change.setStyleSheet("background-color: #f1f3f5; border: 1px solid #ced4da; padding: 10px;")
        
        quality_layout = QHBoxLayout()
        btn_q100 = QPushButton("Orijinal\n(%100)")
        btn_q75 = QPushButton("Yüksek\n(%75)")
        btn_q50 = QPushButton("Orta\n(%50)")
        btn_q25 = QPushButton("Düşük\n(%25)")
        
        q_buttons = [btn_q100, btn_q75, btn_q50, btn_q25]
        for btn in q_buttons:
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { background-color: #e9ecef; border: none; padding: 8px; font-size: 11px; }
                QPushButton:checked { background-color: #8fa4b8; color: white; }
            """)
            quality_layout.addWidget(btn)
        
        btn_q100.setChecked(True)
        
        q_group = QButtonGroup(self)
        q_group.addButton(btn_q100, 100)
        q_group.addButton(btn_q75, 75)
        q_group.addButton(btn_q50, 50)
        q_group.addButton(btn_q25, 25)
        
        mid_layout.addWidget(btn_change)
        mid_layout.addLayout(quality_layout)
        mid_layout.addStretch()

        right_layout = QVBoxLayout()
        
        lbl_new_img = ClickableLabel()
        lbl_new_img.setCursor(QCursor(Qt.PointingHandCursor))
        lbl_new_img.setToolTip("Karşılaştırmak için tıklayın")
        lbl_new_img.setFixedSize(150, 150)
        lbl_new_img.setAlignment(Qt.AlignCenter)
        lbl_new_img.setText("Karşılaştırma için\nresim seçiniz") 
        lbl_new_img.setStyleSheet("border: 2px dashed #bbb; border-radius: 5px; color: #888; background-color: #f8f9fa;")
        
        lbl_new_size = QLabel("- MB")
        lbl_new_size.setStyleSheet("color: gray; font-size: 11px;")
        lbl_new_size.setAlignment(Qt.AlignCenter)
        
        right_layout.addWidget(lbl_new_img)
        right_layout.addWidget(lbl_new_size)
        right_layout.setAlignment(Qt.AlignTop)

        btn_q100.clicked.connect(lambda checked=False: self.apply_quality(index, 100, lbl_new_img, lbl_new_size))
        btn_q75.clicked.connect(lambda checked=False: self.apply_quality(index, 75, lbl_new_img, lbl_new_size))
        btn_q50.clicked.connect(lambda checked=False: self.apply_quality(index, 50, lbl_new_img, lbl_new_size))
        btn_q25.clicked.connect(lambda checked=False: self.apply_quality(index, 25, lbl_new_img, lbl_new_size))
        
        btn_change.clicked.connect(lambda checked=False: self.change_image(index, lbl_new_img, q_group, lbl_new_size))
        
        lbl_original_img.clicked.connect(lambda: PreviewDialog("Orijinal Resim (Yakınlaştırılabilir)", self.images_data[index]['original_bytes'], parent=self).exec_())
        lbl_new_img.clicked.connect(lambda: self.show_comparison(index))

        row_layout.addLayout(left_layout, 1)
        row_layout.addSpacing(20)
        row_layout.addLayout(mid_layout, 2)
        row_layout.addSpacing(20)
        row_layout.addLayout(right_layout, 1)
        
        self.scroll_layout.addWidget(row_widget)

    def show_comparison(self, index):
        data = self.images_data[index]
        if 'new_image_path' in data:
            PreviewDialog("Karşılaştırma (Yakınlaştırılabilir)", data['new_bytes'], original_data=data['original_bytes'], parent=self).exec_()
        else:
            QMessageBox.information(self, "Bilgi", "Karşılaştırma yapmak için önce 'Yeni Resim Seç' butonunu kullanın.")

    def change_image(self, index, lbl_img, q_group, lbl_size):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Yeni Resim Seç", self.last_dir, "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp)", options=options)
        if file_path:
            self.last_dir = os.path.dirname(file_path) 
            self.images_data[index]['new_image_path'] = file_path
            quality = q_group.checkedId()
            self.apply_quality(index, quality, lbl_img, lbl_size)

    def apply_quality(self, index, quality, lbl_img, lbl_size):
        if 'new_image_path' not in self.images_data[index]:
            return
            
        file_path = self.images_data[index]['new_image_path']
        
        img = Image.open(file_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=quality)
        img_byte_arr = img_byte_arr.getvalue()
        
        new_b64 = base64.b64encode(img_byte_arr).decode('utf-8')
        self.images_data[index]['new_b64'] = new_b64
        self.images_data[index]['new_bytes'] = img_byte_arr
        
        pixmap = QPixmap()
        pixmap.loadFromData(img_byte_arr)
        lbl_img.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lbl_img.setStyleSheet("border: 2px solid #4CAF50; border-radius: 5px;")
        
        new_size_mb = len(img_byte_arr) / (1024 * 1024)
        lbl_size.setText(f"Yeni Boyut: {new_size_mb:.2f} MB")
        
        self.update_size_info()

    def update_size_info(self):
        diff_bytes = 0
        for data in self.images_data:
            diff_bytes += len(data['new_b64'].encode('utf-8')) - len(data['original_b64'].encode('utf-8'))
            
        estimated_bytes = self.original_file_size + diff_bytes
        if estimated_bytes < 0:
            estimated_bytes = 0 
            
        estimated_mb = estimated_bytes / (1024 * 1024)
        
        if estimated_mb > 10.0:
            self.lbl_size_info.setText(f"İşlem Sonrası Toplam Boyut\n{estimated_mb:.2f} MB (Sınır Aşıldı!)")
            self.lbl_size_info.setStyleSheet("background-color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: bold; color: #D32F2F; border: 2px solid #D32F2F;")
        else:
            self.lbl_size_info.setText(f"İşlem Sonrası Toplam Boyut\n{estimated_mb:.2f} MB")
            self.lbl_size_info.setStyleSheet("background-color: white; border-radius: 10px; padding: 10px; font-size: 14px; font-weight: bold; color: black; border: none;")

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
    app = QApplication(sys.argv)
    ex = UDFResimcisi()
    ex.show()
    sys.exit(app.exec_())