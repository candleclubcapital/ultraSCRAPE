import os, re, requests, threading, queue, time, random
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QTextEdit, QLineEdit, QFileDialog, QProgressBar, QCheckBox, QSpinBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

class DomainScraper(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("💥 ultraSCRAPE 💥")
        self.resize(1100, 800)
        self.q = queue.Queue()
        self.links_seen = set()
        self.image_urls = set()
        self.stop_flag = False
        self.lock = threading.Lock()
        self._build_ui()
        self._chaos_colors()

    def _chaos_colors(self):
        bg = QColor.fromHsv(random.randint(0, 359), 255, 100).name()
        fg = QColor.fromHsv(random.randint(0, 359), 255, 255).name()
        self.setStyleSheet(f"""
            QWidget {{background-color:{bg}; color:white; font-family:'Courier New';}}
            QPushButton {{background-color:{fg}; border-radius:10px; padding:6px; font-weight:bold; color:black;}}
            QTextEdit {{background:#000; color:#0f0; border:2px solid {fg};}}
            QProgressBar::chunk {{background:{fg};}}
        """)

    def _build_ui(self):
        layout = QVBoxLayout()
        row1 = QHBoxLayout()
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText("https://example.com")
        self.out_input = QLineEdit(); self.out_input.setPlaceholderText("Output folder")
        browse = QPushButton("📁"); browse.clicked.connect(self._choose_folder)
        row1.addWidget(QLabel("Domain:")); row1.addWidget(self.url_input)
        row1.addWidget(QLabel("Save To:")); row1.addWidget(self.out_input); row1.addWidget(browse)
        layout.addLayout(row1)

        opts = QHBoxLayout()
        self.depth = QSlider(Qt.Horizontal); self.depth.setRange(1,8); self.depth.setValue(3)
        self.depth_lbl = QLabel("Depth: 3")
        self.depth.valueChanged.connect(lambda: self.depth_lbl.setText(f"Depth: {self.depth.value()}"))
        self.threads = QSlider(Qt.Horizontal); self.threads.setRange(1,128); self.threads.setValue(32)
        self.threads_lbl = QLabel("Threads: 32")
        self.threads.valueChanged.connect(lambda: self.threads_lbl.setText(f"Threads: {self.threads.value()}"))
        opts.addWidget(self.depth_lbl); opts.addWidget(self.depth)
        opts.addWidget(self.threads_lbl); opts.addWidget(self.threads)
        layout.addLayout(opts)

        row2 = QHBoxLayout()
        self.subdomains = QCheckBox("Include Subdomains"); self.subdomains.setChecked(True)
        self.external = QCheckBox("Include External Domains")
        self.autopage = QCheckBox("Auto-detect Pagination (?page=)")
        row2.addWidget(self.subdomains); row2.addWidget(self.external); row2.addWidget(self.autopage)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.paginate = QCheckBox("Manual Pagination Pattern")
        self.page_pattern = QLineEdit(); self.page_pattern.setPlaceholderText("https://example.com/gallery?page={n}")
        self.page_start = QSpinBox(); self.page_start.setRange(1, 100000); self.page_start.setValue(1)
        self.page_end = QSpinBox(); self.page_end.setRange(1, 100000); self.page_end.setValue(100)
        row3.addWidget(self.paginate)
        row3.addWidget(self.page_pattern)
        row3.addWidget(QLabel("Start:")); row3.addWidget(self.page_start)
        row3.addWidget(QLabel("End:")); row3.addWidget(self.page_end)
        layout.addLayout(row3)

        ctrl = QHBoxLayout()
        self.start_btn = QPushButton("🚀 START")
        self.stop_btn = QPushButton("🛑 STOP")
        self.color_btn = QPushButton("🌈 CHAOS")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.color_btn.clicked.connect(self._chaos_colors)
        ctrl.addWidget(self.start_btn); ctrl.addWidget(self.stop_btn); ctrl.addWidget(self.color_btn)
        layout.addLayout(ctrl)

        self.progress = QProgressBar(); layout.addWidget(self.progress)
        self.log = QTextEdit(); self.log.setReadOnly(True); layout.addWidget(self.log)
        self.setLayout(layout)

    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if d: self.out_input.setText(d)

    def _log(self, msg):
        self.log.append(msg)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _stop(self):
        self.stop_flag = True
        self._log("[STOP] Graceful shutdown requested...")

    def _start(self):
        self.stop_flag = False
        self.links_seen.clear()
        self.image_urls.clear()
        domain = self.url_input.text().strip()
        out = self.out_input.text().strip()
        if not domain or not out:
            self._log("[ERROR] Domain or output missing.")
            return
        os.makedirs(out, exist_ok=True)
        threading.Thread(target=self._crawl_all, args=(domain, out), daemon=True).start()

    def _crawl_all(self, start_url, out):
        depth = self.depth.value()
        max_threads = self.threads.value()
        self.q.put((start_url, depth))
        self.links_seen.add(start_url)
        if self.paginate.isChecked():
            self._generate_manual_pagination()
        self._log(f"[START] Crawling {start_url} | depth={depth} | threads={max_threads}")
        with ThreadPoolExecutor(max_workers=max_threads) as ex:
            futures = []
            while not self.q.empty() and not self.stop_flag:
                url, lvl = self.q.get()
                futures.append(ex.submit(self._process_page, url, lvl, start_url))
            for f in futures:
                try: f.result()
                except Exception as e: self._log(f"[THREAD ERR] {e}")
        self._download_images(out)
        self._log("[DONE] Crawl complete.")

    def _generate_manual_pagination(self):
        pattern = self.page_pattern.text().strip()
        if "{n}" not in pattern:
            self._log("[WARN] Invalid pagination pattern (missing {n})")
            return
        for i in range(self.page_start.value(), self.page_end.value()+1):
            url = pattern.replace("{n}", str(i))
            self.q.put((url, 1))
            self.links_seen.add(url)
        self._log(f"[PAGE GEN] Added {self.page_end.value()-self.page_start.value()+1} manual pagination URLs")

    def _normalize(self, url):
        u = url.split("#")[0]
        u = re.sub(r'(?<=/)/+', '/', u)
        return u

    def _process_page(self, url, depth, base):
        if self.stop_flag: return
        try:
            r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
            if "text/html" not in r.headers.get("Content-Type", ""): return
            soup = BeautifulSoup(r.text, 'html.parser')
            imgs = [urljoin(url, img.get('src')) for img in soup.find_all('img') if img.get('src')]
            with self.lock:
                for im in imgs:
                    norm = self._normalize(im)
                    if norm not in self.image_urls:
                        self.image_urls.add(norm)
            if self.autopage.isChecked():
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if re.search(r'[\?&]page=\d+', href):
                        purl = urljoin(url, href)
                        if purl not in self.links_seen:
                            self.links_seen.add(purl)
                            self.q.put((purl, depth-1))
            if depth > 0:
                for a in soup.find_all('a', href=True):
                    link = urljoin(url, a['href'])
                    parsed = urlparse(link)
                    if not parsed.scheme.startswith("http"): continue
                    base_dom = urlparse(base).netloc
                    target_dom = parsed.netloc
                    if not self.external.isChecked():
                        if not (base_dom in target_dom if self.subdomains.isChecked() else base_dom == target_dom):
                            continue
                    if link not in self.links_seen:
                        self.links_seen.add(link)
                        self.q.put((link, depth - 1))
            self._log(f"[PAGE] {url} | imgs={len(self.image_urls)} | queue={self.q.qsize()}")
        except Exception as e:
            self._log(f"[ERR] {url}: {e}")

    def _download_images(self, out):
        total = len(self.image_urls)
        self.progress.setMaximum(total)
        self._log(f"[DL] Starting downloads for {total} images")
        def dl_one(i, url):
            if self.stop_flag: return
            try:
                r = requests.get(url, timeout=10, stream=True)
                ctype = r.headers.get("Content-Type", "")
                ext = ".jpg"
                if "png" in ctype: ext = ".png"
                elif "gif" in ctype: ext = ".gif"
                elif "webp" in ctype: ext = ".webp"
                name = os.path.join(out, f"img_{i}{ext}")
                with open(name, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                self.progress.setValue(i + 1)
            except Exception as e:
                self._log(f"[DL ERR] {url}: {e}")

        with ThreadPoolExecutor(max_workers=64) as ex:
            for i, u in enumerate(list(self.image_urls)):
                if self.stop_flag: break
                ex.submit(dl_one, i, u)
        self._log("[DL COMPLETE]")

if __name__ == "__main__":
    app = QApplication([])
    w = DomainScraper()
    w.show()
    app.exec()
