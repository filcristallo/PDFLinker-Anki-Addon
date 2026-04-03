# PDFLinker: The Ultimate PDF Workflow for Anki

This add-on is free, support me if you want!

<a href="https://www.buymeacoffee.com/filippocristallo" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

<img width="1532" height="1035" alt="Screenshot 2026-04-02 alle 10 33 15" src="https://github.com/user-attachments/assets/ce8b9b00-2d14-4923-a187-b869829753cb" />

PDFLinker is a powerful Anki add-on that bridges the gap between your study materials and your flashcards. Read PDFs directly within Anki, automatically generate high-quality cloze-deletion flashcards using the Gemini API, and instantly tie those flashcards back to the exact page they came from.

## ✨ Features

* **Manual Card Creation (No AI Required):** You don't have to use the AI! You can simply open a PDF, open your Anki 'Add' window, and type your flashcards manually. PDFLinker will still track your position and link the exact PDF page to your card.
* **Creator Mode (AI Generation):** Open a PDF, highlight complex text, and click a button to generate perfectly formatted Anki flashcards using Google's Gemini models.
* **Auto-Fill Engine:** Whether you send AI-generated cards to the 'Add' window or type them manually, PDFLinker automatically fills in custom `PDF_Path` and `PDF_Page` fields in real-time so you never lose your source.
* **Review Mode:** When reviewing flashcards, the add-on reads the `PDF_Path` and `PDF_Page` fields and automatically pulls up the exact PDF page alongside your review window for instant context.
* **AI Explanations:** Highlight confusing academic or medical text and ask the AI to break it down into plain language.
* **Smart UI:** Double-click generated cloze deletions in the preview window to easily adjust or remove hints before sending them to Anki.

## 🚀 Installation

**Method 1: Install via AnkiWeb (Recommended)**
The absolute easiest way to install PDFLinker and get automatic updates is through AnkiWeb.
1. Open Anki and go to **Tools -> Add-ons**.
2. Click **Get Add-ons...**
3. Paste the code **`962234340`** and click OK.
4. Restart Anki.
*(You can view the official AnkiWeb page [here](https://ankiweb.net/shared/info/962234340)).*

**Method 2: Install via GitHub Release**
1. Go to the [Releases](../../releases/latest) page of this GitHub repository.
2. Under the "Assets" section of the latest release, download the `pdflinker.ankiaddon` file.
3. Double-click the downloaded file. Anki will automatically open and ask to install it. 
4. Restart Anki.

**Method 3: Manual Installation (For Developers)**
1. Clone this repository or download the source code `.zip`.
2. Place the extracted folder into your Anki `addons21` directory. **Important:** Make sure the folder is named exactly `pdflinker` (no spaces, hyphens, or periods).
    * *Windows:* `%APPDATA%\Anki2\addons21`
    * *Mac:* `~/Library/Application Support/Anki2/addons21`
    * *Linux:* `~/.local/share/Anki2/addons21`
3. Restart Anki.

*(Note: On its first run, PDFLinker will automatically download the required Mozilla PDF.js engine in the background).*

## ⚙️ Configuration

To use the AI generation features, you need a free Google Gemini API key.

1. Get an API key from [Google AI Studio](https://aistudio.google.com/).
2. In Anki, go to **Tools -> Add-ons -> PDFLinker -> Config**.
3. Paste your key into the `gemini_api_key` field.
4. (Optional) Adjust the `ai_prompt` or `explain_prompt` to fit your specific study needs.

### Field Setup (Important)
For the auto-sync to work, ensure your Anki Note Type has the following fields:
* `PDF_Path`
* `PDF_Page`

The add-on will look for fields named `Text` or `Front` to drop the question in, and `Extra` or `Back` for the explanation.

## 🤝 Contributing

Contributions are welcome! If you want to improve the markdown parser, add new AI models, or refine the UI, please check out our [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 License

This project is open-source and licensed under the MIT License. 

You are absolutely free to share, edit, modify, and distribute this code. The only requirement is that you must provide clear attribution by citing **Fil Cristallo** as the original author of the project and include the original license file in any forks or distributions. 

See the [LICENSE](LICENSE) file for more details.

<a href="https://www.buymeacoffee.com/filippocristallo" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>
