import os
import json
import zipfile
import urllib.request
import urllib.parse
import urllib.error
import re
import logging
from typing import Optional, Dict, Any, List

from aqt import mw
from aqt.qt import *
from aqt.editor import Editor
from aqt import gui_hooks
from aqt.utils import askUser, tooltip, showInfo
from aqt.addcards import AddCards
from anki.cards import Card
from anki.notes import Note

# Qt5 / Qt6 compatibility handling
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
except ImportError:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings, QWebEnginePage

# ==========================================
# CONSTANTS & SETUP
# ==========================================
ADDON_DIR = os.path.dirname(__file__)
PDFJS_DIR = os.path.join(ADDON_DIR, "pdfjs")
VIEWER_HTML_PATH = os.path.join(PDFJS_DIR, "web", "viewer.html")

USER_FILES_DIR = os.path.join(ADDON_DIR, "user_files")
CACHE_FILE = os.path.join(USER_FILES_DIR, "pdf_cache.json")

PDFJS_RELEASE_URL = "https://github.com/mozilla/pdf.js/releases/download/v3.11.174/pdfjs-3.11.174-dist.zip"

# Setup basic logging for the add-on
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PDFLinker")


def setup_dependencies() -> None:
    """Downloads the PDF viewer in the background so it doesn't freeze Anki."""
    if os.path.exists(VIEWER_HTML_PATH):
        return

    os.makedirs(PDFJS_DIR, exist_ok=True)
    zip_path = os.path.join(PDFJS_DIR, "pdfjs.zip")
    
    def download_pdfjs() -> None:
        urllib.request.urlretrieve(PDFJS_RELEASE_URL, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(PDFJS_DIR)
        os.remove(zip_path)
        
    def on_download_done(future) -> None:
        try:
            future.result()
            tooltip("PDFLinker: Setup Complete!", period=3000)
            logger.info("PDF.js successfully downloaded and extracted.")
        except Exception as e:
            logger.error(f"Error downloading PDF.js: {e}")
            showInfo(f"PDFLinker failed to download PDF.js: {e}\nPlease check your internet connection.")
            
    tooltip("PDFLinker: Downloading PDF engine for the first time. Please wait...", period=4000)
    logger.info("Downloading PDF.js viewer...")
    mw.taskman.run_in_background(download_pdfjs, on_download_done)

# Initialize dependencies on startup
setup_dependencies()

# ==========================================
# CACHE SYSTEM & TEXT FORMATTING
# ==========================================

def get_cache_data() -> Dict[str, Any]:
    """Loads PDF page cache from disk."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode cache file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error reading cache: {e}")
    return {}

def save_cache_data(data: Dict[str, Any]) -> None:
    """Saves PDF page cache to disk in the protected user_files directory."""
    try:
        os.makedirs(USER_FILES_DIR, exist_ok=True)
        
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save cache data: {e}")

def get_last_page(pdf_path: str) -> str:
    return str(get_cache_data().get(pdf_path, "1"))

def set_last_page(pdf_path: str, page: str) -> None:
    cache = get_cache_data()
    cache[pdf_path] = str(page)
    save_cache_data(cache)

def clean_ai_text(text: str) -> str:
    """Formats raw AI markdown text into Anki-ready HTML."""
    if not text:
        return ""
    
    # Try using the robust markdown library if Anki has it, including table support
    try:
        import markdown
        return markdown.markdown(text.strip(), extensions=['tables'])
    except ImportError:
        logger.warning("Markdown library not found. Falling back to regex parser.")

    # Regex fallback for formatting markdown manually
    text = text.strip()
    
    # --- 0. Tables (Line-by-line parsing fallback) ---
    lines = text.split('\n')
    in_table = False
    html_lines = []
    
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('|') and stripped_line.endswith('|'):
            if not in_table:
                html_lines.append('<table border="1" style="border-collapse: collapse; width: 100%; margin-bottom: 15px;">')
                in_table = True
            
            # Skip separator row (e.g., |---|---|)
            if re.match(r'^\|[\s\-\|:]+\|$', stripped_line):
                continue
                
            row_html = "<tr>"
            cells = [c.strip() for c in stripped_line.split('|')][1:-1]
            for cell in cells:
                row_html += f"<td style='padding: 8px;'>{cell}</td>"
            row_html += "</tr>"
            html_lines.append(row_html)
        else:
            if in_table:
                html_lines.append('</table>')
                in_table = False
            html_lines.append(line)
            
    if in_table:
        html_lines.append('</table>')
        
    text = '\n'.join(html_lines)
    
    # --- 1. Headers ---
    for i in range(6, 0, -1):
        hashes = '#' * i
        text = re.sub(fr'^{hashes}\s+(.*?)$', fr'<h{i}>\1</h{i}>', text, flags=re.MULTILINE)
    
    # --- 2. Lists (Unordered & Ordered) ---
    text = re.sub(r'^(\s*)[-*+]\s+(.*?)$', r'<ul><li>\2</li></ul>', text, flags=re.MULTILINE)
    text = re.sub(r'^(\s*)\d+\.\s+(.*?)$', r'<ol><li>\2</li></ol>', text, flags=re.MULTILINE)
    text = re.sub(r'</ul>\s*<ul>', '', text)
    text = re.sub(r'</ol>\s*<ol>', '', text)
    
    # --- 3. Bold & Italic ---
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)
    
    # --- 4. Paragraphs / Newlines ---
    text = text.replace('\n\n', '<br><br>')
    text = text.replace('\n', '<br>')
    
    # Clean up stray <br> around block HTML elements
    block_elements = ['ul', 'ol', 'table', 'tr']
    for el in block_elements:
        text = re.sub(fr'<br>\s*<{el}', f'<{el}', text)
        text = re.sub(fr'</{el}>\s*<br>', f'</{el}>', text)
    text = re.sub(r'<br>\s*<h(\d)>', r'<h\1>', text)
    text = re.sub(r'</h(\d)>\s*<br>', r'</h\1>', text)
    
    return text

# ==========================================
# AUTO-FILL ENGINE (REAL-TIME BRIDGE)
# ==========================================

def auto_fill_open_editors(path: str, page: str) -> None:
    """Finds any open Anki Add/Edit window and updates the PDF fields."""
    for widget in mw.app.topLevelWidgets():
        editor = getattr(widget, 'editor', None)
        if editor and getattr(editor, 'note', None):
            note = editor.note
            changed = False
            
            if "PDF_Path" in note and note["PDF_Path"] != path:
                note["PDF_Path"] = path
                changed = True
            if "PDF_Page" in note and note["PDF_Page"] != str(page):
                note["PDF_Page"] = str(page)
                changed = True
            
            if changed:
                editor.loadNote()

class CustomWebPage(QWebEnginePage):
    """Intercepts invisible messages sent from Javascript to Python."""
    def javaScriptConsoleMessage(self, level, message: str, lineNumber: int, sourceID: str) -> None:
        if message.startswith("PDF_PAGE_CHANGED:"):
            page_num = message.split(":")[1]
            if creator_viewer and creator_viewer.current_pdf_path:
                auto_fill_open_editors(creator_viewer.current_pdf_path, page_num)
                set_last_page(creator_viewer.current_pdf_path, page_num)
                
        elif message.startswith("PDF_EXTRACT_FLASHCARD:"):
            text = message[len("PDF_EXTRACT_FLASHCARD:"):]
            if creator_viewer:
                creator_viewer.process_extracted_text(text, task="flashcard")

        elif message.startswith("PDF_EXTRACT_EXPLAIN:"):
            text = message[len("PDF_EXTRACT_EXPLAIN:"):]
            if creator_viewer:
                creator_viewer.process_extracted_text(text, task="explain")
                
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)

# ==========================================
# UI COMPONENTS
# ==========================================

class ClozeTextEdit(QTextEdit):
    """A custom QTextEdit that deletes cloze hints or entirely un-clozes text when double-clicked."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet("border: 1px solid rgba(128, 128, 128, 0.5); border-radius: 4px;")

    def mouseDoubleClickEvent(self, event) -> None:
        cursor = self.cursorForPosition(event.pos())
        pos = cursor.position()
        block = cursor.block()
        block_pos = block.position()
        relative_pos = pos - block_pos
        text = block.text()
        
        try:
            keep_anchor = QTextCursor.MoveMode.KeepAnchor
        except AttributeError:
            keep_anchor = QTextCursor.KeepAnchor
        
        for match in re.finditer(r'\{\{c\d+::.+?\}\}', text):
            cloze_text = match.group(0)
            start = match.start()
            end = match.end()
            
            first_colon_idx = cloze_text.find('::')
            last_colon_idx = cloze_text.rfind('::')
            has_hint = (last_colon_idx != -1 and last_colon_idx != first_colon_idx)
            
            # 1. Clicked on the prefix? Un-cloze entirely.
            c_prefix_end = start + first_colon_idx + 2
            if start <= relative_pos <= c_prefix_end:
                answer = cloze_text[first_colon_idx + 2 : last_colon_idx] if has_hint else cloze_text[first_colon_idx + 2 : -2]
                selection_cursor = self.textCursor()
                selection_cursor.setPosition(block_pos + start)
                selection_cursor.setPosition(block_pos + end, keep_anchor)
                selection_cursor.insertText(answer)
                return 
                
            # 2. Clicked on the hint? Delete just the hint.
            if has_hint:
                hint_start = start + last_colon_idx
                hint_end = end - 2 
                if hint_start <= relative_pos <= end:
                    selection_cursor = self.textCursor()
                    selection_cursor.setPosition(block_pos + hint_start)
                    selection_cursor.setPosition(block_pos + hint_end, keep_anchor)
                    selection_cursor.removeSelectedText()
                    return 
        
        super().mouseDoubleClickEvent(event)


class GeneratedCardsWindow(QMainWindow):
    def __init__(self, main_viewer, cards_data: List[Dict], extracted_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Generated Flashcards")
        self.resize(750, 600)
        
        self.main_viewer = main_viewer
        self.cards_data = cards_data
        self.extracted_text = extracted_text
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        try:
            self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        except AttributeError:
            self.scroll_area.setFrameShape(QFrame.NoFrame)
        
        self.main_layout.addWidget(self.scroll_area)
        
        self.control_layout = QHBoxLayout()
        self.control_layout.addStretch()
        self.regen_all_btn = QPushButton("Regenerate All")
        self.regen_all_btn.clicked.connect(self.on_regenerate_all)
        self.control_layout.addWidget(self.regen_all_btn)
        self.main_layout.addLayout(self.control_layout)
        
        self.populate_list()

    def populate_list(self) -> None:
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(12)
        
        for card in self.cards_data:
            item_widget = QWidget()
            item_widget.setObjectName("cardContainer")
            item_widget.setStyleSheet("""
                #cardContainer {
                    background-color: rgba(128, 128, 128, 0.15);
                    border-radius: 8px;
                    border: 1px solid rgba(128, 128, 128, 0.3);
                }
            """)
            
            item_layout = QVBoxLayout(item_widget)
            item_layout.setSpacing(8)
            item_layout.setContentsMargins(14, 14, 14, 14)
            
            text_str = card.get('text', '')
            extra_str = card.get('extra', '')
            
            # Setup Text Field
            text_label = QLabel("<b>Text:</b>")
            text_edit = ClozeTextEdit()
            text_edit.setHtml(text_str)
            text_edit.setMinimumHeight(70)
            text_edit.setMaximumHeight(200)
            
            # Setup Extra Field
            extra_label = QLabel("<b>Extra:</b>")
            extra_edit = QTextEdit()
            extra_edit.setHtml(extra_str)
            extra_edit.setMinimumHeight(70)
            extra_edit.setMaximumHeight(200)
            extra_edit.setStyleSheet("border: 1px solid rgba(128, 128, 128, 0.5); border-radius: 4px;")
            
            # Controls
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 4, 0, 0)
            
            import_extra_cb = QCheckBox("Import Extra Field")
            import_extra_cb.setChecked(True)
            
            send_btn = QPushButton("Send to Add Window")
            send_btn.clicked.connect(lambda _, te=text_edit, ee=extra_edit, cb=import_extra_cb, w=item_widget: 
                                     self.send_to_add_window(te, ee, cb, w))
            
            btn_layout.addWidget(import_extra_cb)
            btn_layout.addStretch()
            btn_layout.addWidget(send_btn)
            
            item_layout.addWidget(text_label)
            item_layout.addWidget(text_edit)
            item_layout.addWidget(extra_label)
            item_layout.addWidget(extra_edit)
            item_layout.addLayout(btn_layout)
            
            self.cards_layout.addWidget(item_widget)
        
        self.cards_layout.addStretch()
        self.scroll_area.setWidget(self.cards_container)

    def on_regenerate_all(self) -> None:
        self.main_viewer.regenerate_all_cards(self.extracted_text)

    def get_anki_html(self, text_edit: QTextEdit) -> str:
        """Translates Qt styles to pure b, i, u tags and strips extra HTML."""
        html = text_edit.toHtml()
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if not body_match:
            return text_edit.toPlainText()
            
        content = body_match.group(1).strip()
        content = re.sub(r'</p>\s*<p[^>]*>', '<br>', content, flags=re.IGNORECASE)
        
        def replace_span(match):
            style = match.group(1).lower()
            res = match.group(2)
            if re.search(r'font-weight:\s*(600|700|800|900|bold)', style):
                res = f'<b>{res}</b>'
            if re.search(r'font-style:\s*italic', style):
                res = f'<i>{res}</i>'
            if re.search(r'text-decoration:\s*underline', style):
                res = f'<u>{res}</u>'
            return res

        old_content = ""
        while old_content != content:
            old_content = content
            content = re.sub(r'<span[^>]*style="([^"]*)"[^>]*>((?:(?!<span).)*?)</span>', replace_span, content, flags=re.IGNORECASE | re.DOTALL)
            
        content = re.sub(r'</?(?!(?:b|i|u|br)\b)[a-z0-9]+[^>]*>', '', content, flags=re.IGNORECASE)
        return content.strip()

    def send_to_add_window(self, text_edit: QTextEdit, extra_edit: QTextEdit, import_extra_cb: QCheckBox, widget_to_style: QWidget) -> None:
        add_window = None
        for widget in mw.app.topLevelWidgets():
            if isinstance(widget, AddCards):
                add_window = widget
                break
                
        if not add_window:
            tooltip("Please open the 'Add' window in Anki first.")
            return
            
        note = add_window.editor.note
        changed = False
        
        final_text = self.get_anki_html(text_edit)
        final_extra = self.get_anki_html(extra_edit) if import_extra_cb.isChecked() else ""
        
        text_fields = ["Text", "Front", "Question"]
        extra_fields = ["Extra", "Back", "Answer"]
        
        for field in note.keys():
            if field in text_fields or field.lower() == "text":
                note[field] = final_text
                changed = True
            elif field in extra_fields or field.lower() == "extra":
                note[field] = final_extra if import_extra_cb.isChecked() else ""
                changed = True
                
        if changed:
            add_window.editor.loadNote()
            tooltip("Fields updated in Add Window!")
            widget_to_style.setStyleSheet("""
                #cardContainer {
                    background-color: rgba(128, 128, 128, 0.15);
                    border-radius: 8px;
                    border: 1px solid #4CAF50;
                }
            """)
        else:
            tooltip("Could not find suitable fields (e.g., 'Text', 'Extra') in the current Note Type.")


class ExplanationWindow(QMainWindow):
    def __init__(self, main_viewer, explanation_text: str, extracted_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Explanation")
        self.resize(600, 500)
        
        self.main_viewer = main_viewer
        self.raw_explanation_text = explanation_text
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.main_layout.addWidget(self.text_browser)
        
        self.control_layout = QHBoxLayout()
        self.control_layout.addStretch()
        self.gen_cards_btn = QPushButton("Generate Flashcards from this Explanation")
        self.gen_cards_btn.clicked.connect(self.generate_cards_from_explanation)
        self.control_layout.addWidget(self.gen_cards_btn)
        self.main_layout.addLayout(self.control_layout)
        
        self.update_explanation(explanation_text, extracted_text)

    def update_explanation(self, explanation_text: str, extracted_text: str) -> None:
        self.raw_explanation_text = explanation_text 
        formatted_text = clean_ai_text(explanation_text)
        self.text_browser.setHtml(formatted_text)

    def generate_cards_from_explanation(self) -> None:
        if self.main_viewer:
            self.main_viewer.process_extracted_text(self.raw_explanation_text, task="flashcard")


# ==========================================
# MAIN VIEWER LOGIC
# ==========================================

review_viewer = None
creator_viewer = None
review_action = None
creator_action = None

class PDFViewerWindow(QMainWindow):
    def __init__(self, mode: str = "review", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.current_pdf_path = None 
        self.web_view = QWebEngineView(self)
        
        if self.mode == "create":
            self.setWindowTitle("PDFLinker Reader (Creator Mode)")
            self.resize(1000, 1000)
            
            toolbar = QToolBar("PDF Toolbar", self)
            toolbar.setMovable(False)
            toolbar.toggleViewAction().setEnabled(False)
            self.addToolBar(toolbar)
            
            open_action = QAction("📂 Open PDF for Study...", self)
            open_action.triggered.connect(self.open_local_pdf)
            toolbar.addAction(open_action)
            
            analyze_action = QAction("⚡ Generate Flashcards", self)
            analyze_action.triggered.connect(self.analyze_current_page)
            toolbar.addAction(analyze_action)
            
            explain_action = QAction("🧠 Explain", self)
            explain_action.triggered.connect(self.explain_current_page)
            toolbar.addAction(explain_action)
            
            # --- NEW: Support Button ---
            toolbar.addSeparator()
            support_action = QAction("☕ Buy me a coffee", self)
            support_action.triggered.connect(self.open_support_link)
            toolbar.addAction(support_action)
            
            self.web_page = CustomWebPage(self.web_view)
            self.web_view.setPage(self.web_page)
        else:
            self.setWindowTitle("PDFLinker Reader (Review Mode)")
            self.resize(800, 1000)

        self.setCentralWidget(self.web_view)
        self.web_view.loadFinished.connect(self.on_load_finished)
        
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self._load_empty_viewer()

    def open_support_link(self) -> None:
        """Opens the Buy Me A Coffee link in the user's default web browser."""
        import webbrowser
        webbrowser.open("https://www.buymeacoffee.com/filippocristallo")

    def _load_empty_viewer(self) -> None:
        if os.path.exists(VIEWER_HTML_PATH):
            base_url = QUrl.fromLocalFile(VIEWER_HTML_PATH).toString()
            self.web_view.setUrl(QUrl(base_url))

    def on_load_finished(self, ok: bool) -> None:
        if not ok: return
        anti_scroll_js = """
        function disableSearchScroll() {
            if (typeof PDFViewerApplication !== 'undefined' && PDFViewerApplication.findController) {
                PDFViewerApplication.findController.scrollMatchIntoView = function() { return; };
            } else {
                setTimeout(disableSearchScroll, 100);
            }
        }
        disableSearchScroll();
        """
        
        if self.mode == "create":
            js_code = anti_scroll_js + """
            function initPdfListeners() {
                if (typeof PDFViewerApplication !== 'undefined' && PDFViewerApplication.eventBus) {
                    PDFViewerApplication.eventBus.on('pagechanging', function(e) {
                        console.log("PDF_PAGE_CHANGED:" + e.pageNumber);
                    });
                } else {
                    setTimeout(initPdfListeners, 500);
                }
            }
            initPdfListeners();
            """
            self.web_view.page().runJavaScript(js_code)
        elif self.mode == "review":
            self.web_view.page().runJavaScript(anti_scroll_js)

    def open_local_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if file_path:
            last_page = get_last_page(file_path)
            self.load_pdf(file_path, last_page)

    def load_pdf(self, path: str, page: str, note: Optional[Note] = None) -> None:
        if not path or not os.path.exists(path):
            return
        self.current_pdf_path = path 
        base_viewer_url = QUrl.fromLocalFile(VIEWER_HTML_PATH).toString()
        file_url = QUrl.fromLocalFile(path).toString()
        encoded_file_url = urllib.parse.quote(file_url, safe="%/:=&?~#+!$,;'@()*[]")
        
        full_url = f"{base_viewer_url}?file={encoded_file_url}#page={page}"
        self.web_view.setUrl(QUrl(full_url))

    def _get_api_config(self) -> Optional[Dict[str, Any]]:
        config = mw.addonManager.getConfig(__name__) or {}
        if not config.get("gemini_api_key", ""):
            showInfo("Please set your 'gemini_api_key' in the add-on config.")
            return None
        return config

    def analyze_current_page(self) -> None:
        if not self._get_api_config(): return
        js_extract = "(function() { console.log('PDF_EXTRACT_FLASHCARD:' + window.getSelection().toString().trim()); })();"
        self.web_view.page().runJavaScript(js_extract)

    def explain_current_page(self) -> None:
        if not self._get_api_config(): return
        js_extract = "(function() { console.log('PDF_EXTRACT_EXPLAIN:' + window.getSelection().toString().trim()); })();"
        self.web_view.page().runJavaScript(js_extract)

    def process_extracted_text(self, extracted_text: str, task: str = "flashcard") -> None:
        config = self._get_api_config()
        if config:
            self._call_ai_api(extracted_text, config, config.get("gemini_api_key", ""), task)

    def regenerate_all_cards(self, extracted_text: str) -> None:
        config = self._get_api_config()
        if config:
            self._call_ai_api(extracted_text, config, config.get("gemini_api_key", ""), task="flashcard")

    def _call_ai_api(self, extracted_text: str, config: Dict[str, Any], api_key: str, task: str = "flashcard") -> None:
        if not extracted_text or not str(extracted_text).strip():
            showInfo("No text selected! Please highlight the text you want to analyze in the PDF first.")
            return
            
        model_name = config.get("gemini_model")
        thinking_level = config.get("thinking_level", "")
        
        if task == "flashcard":
            prompt_template = config.get("ai_prompt")
            mime_type = "application/json"
        else:
            prompt_template = config.get("explain_prompt", "Explain this text simply and clearly.")
            mime_type = "text/plain"

        if not model_name or not prompt_template:
            showInfo("Please set 'gemini_model' and the respective prompt in your Anki add-on config.")
            return
            
        tooltip("Calling AI... Please wait.", period=4000)
        
        # Clean the prompt template
        system_prompt = prompt_template.replace("{extracted_text}", "").strip()

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        data = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": extracted_text}]}],
            "generationConfig": {"response_mime_type": mime_type}
        }
        
        if thinking_level:
            data["generationConfig"]["thinkingConfig"] = {"thinkingLevel": thinking_level}
        
        def fetch_from_api():
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), method='POST')
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                parts = result['candidates'][0]['content']['parts']
                content_text = "".join(part.get("text", "") for part in parts if not part.get("thought", False))
                        
                if task == "flashcard":
                    cards_data = json.loads(content_text)
                    for card in cards_data:
                        if 'text' in card: card['text'] = clean_ai_text(card['text'])
                        if 'extra' in card: card['extra'] = clean_ai_text(card['extra'])
                    return cards_data
                return content_text

        def on_api_done(future):
            try:
                result_data = future.result()
                if task == "flashcard":
                    if hasattr(self, 'generated_cards_window') and self.generated_cards_window.isVisible():
                        self.generated_cards_window.cards_data = result_data
                        self.generated_cards_window.extracted_text = extracted_text
                        self.generated_cards_window.populate_list()
                        tooltip("Flashcards Updated!", period=2000)
                    else:
                        self.generated_cards_window = GeneratedCardsWindow(self, result_data, extracted_text)
                        self.generated_cards_window.show()
                elif task == "explain":
                    if hasattr(self, 'explanation_window') and self.explanation_window.isVisible():
                        self.explanation_window.update_explanation(result_data, extracted_text)
                        tooltip("Explanation Updated!", period=2000)
                    else:
                        self.explanation_window = ExplanationWindow(self, result_data, extracted_text)
                        self.explanation_window.show()
            except urllib.error.HTTPError as e:
                error_msg = f"HTTP Error calling AI API: {e.code} - {e.reason}"
                if e.code == 404:
                    error_msg = f"Error 404: Model not found. Check if '{model_name}' is correct in config."
                elif e.code == 400:
                    error_msg = f"Error 400 (Bad Request): The model '{model_name}' might not support the requested configuration (e.g., thinking_level)."
                logger.error(error_msg)
                showInfo(error_msg)
            except Exception as e:
                logger.exception("AI API Call Failed")
                msg = f"Error parsing AI response: {str(e)}\n\nThe AI might not have returned valid JSON." if task == "flashcard" else f"Error returning AI explanation: {str(e)}"
                showInfo(msg)

        mw.taskman.run_in_background(fetch_from_api, on_api_done)

    def closeEvent(self, event) -> None:
        global review_viewer, creator_viewer
        if self.mode == "review":
            if review_action: review_action.setChecked(False)
            review_viewer = None
        elif self.mode == "create":
            if creator_action: creator_action.setChecked(False)
            creator_viewer = None
            
        if hasattr(self, 'generated_cards_window') and self.generated_cards_window:
            self.generated_cards_window.close()
            
        if hasattr(self, 'explanation_window') and self.explanation_window:
            self.explanation_window.close()
            
        self.deleteLater()
        event.accept()


# ==========================================
# TOGGLE & MENU REGISTRATION
# ==========================================

def toggle_review_viewer(checked: bool) -> None:
    global review_viewer
    if checked:
        if not review_viewer:
            review_viewer = PDFViewerWindow(mode="review", parent=mw)
        review_viewer.show()
        if mw.state == "review" and getattr(mw.reviewer, 'state', None) == "answer":
            update_pdf_for_current_card(mw.reviewer.card)
    else:
        if review_viewer: review_viewer.hide()

def toggle_creator_viewer(checked: bool) -> None:
    global creator_viewer
    if checked:
        if not creator_viewer:
            creator_viewer = PDFViewerWindow(mode="create", parent=mw)
        creator_viewer.show()
    else:
        if creator_viewer: creator_viewer.hide()

def update_pdf_for_current_card(card: Optional[Card]) -> None:
    global review_viewer
    if not review_viewer or not review_viewer.isVisible() or not card: 
        return
        
    note = card.note()
    if "PDF_Path" in note and "PDF_Page" in note:
        path = note["PDF_Path"]
        page = note["PDF_Page"]
        if path and page and os.path.exists(path):
            review_viewer.load_pdf(path, page, note)

def setup_menu() -> None:
    global review_action, creator_action
    
    mw.form.menuTools.addSeparator()
    
    review_action = QAction("PDFLinker: Review Mode", mw)
    review_action.setCheckable(True)
    review_action.triggered.connect(toggle_review_viewer)
    mw.form.menuTools.addAction(review_action)
    
    creator_action = QAction("PDFLinker: Creator Mode", mw)
    creator_action.setCheckable(True)
    creator_action.triggered.connect(toggle_creator_viewer)
    mw.form.menuTools.addAction(creator_action)

gui_hooks.reviewer_did_show_answer.append(update_pdf_for_current_card)
setup_menu()
