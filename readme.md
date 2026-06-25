# SuPY-IDE

**SuPY-IDE** is a lightweight, single-file Python IDE built with **PyQt5**. It lets
you write, run and debug Python in a clean, distraction-free editor with syntax
highlighting, smart editing, autocompletion, themes and a real (non-blocking)
code runner.

> Made with ❤️ by **Sukhpreet Singh**

---

## ✨ Features

### Editor
- **Syntax highlighting** — keywords, builtins, numbers, decorators, `def`/`class`
  names, `self`/`cls`, and strings (including multi-line triple-quoted strings).
- **Smart editing**
  - Auto-indentation (keeps indent, adds one level after `:`).
  - `Tab` inserts 4 spaces; `Tab`/`Shift+Tab` indent/dedent whole selections.
  - Bracket & quote **auto-closing** (`()`, `[]`, `{}`, `""`, `''`) with
    skip-over and smart backspace that deletes empty pairs.
  - **Comment toggling** for the current line or selection (`Ctrl+/`).
- **Autocompletion** for Python keywords and builtins.
- **Line numbers** with the current line highlighted in the gutter.
- **Find & Replace** bar with wrap-around search and *Replace All* (`Ctrl+F` / `Ctrl+H`).
- **Editor zoom** (`Ctrl+=` / `Ctrl+-` / `Ctrl+0`).

### Running code
- Code runs in a **separate process**, so:
  - the UI **never freezes**, even on long-running or infinite loops;
  - you get **real Python tracebacks**;
  - **`input()` works** via the interactive input box below the output;
  - you can **Stop** a run at any time (`Shift+F5`).
- The line that raised an exception is **highlighted** in the editor.
- Execution time and exit code are shown in the status bar.

### Workflow & UI
- **Light / dark themes** (`Ctrl+T`).
- Menu bar, toolbar and status bar (cursor position, run status).
- File handling with **modified-state tracking** (a `*` in the title) and
  **unsaved-changes prompts** when you open/new/close.
- Resizable editor / output split.

---

## ⌨️ Keyboard shortcuts

| Action            | Shortcut        | Action            | Shortcut        |
|-------------------|-----------------|-------------------|-----------------|
| New file          | `Ctrl+N`        | Run code          | `F5`            |
| Open file         | `Ctrl+O`        | Stop run          | `Shift+F5`      |
| Save              | `Ctrl+S`        | Clear output      | `Ctrl+L`        |
| Save As           | `Ctrl+Shift+S`  | Toggle comment    | `Ctrl+/`        |
| Find / Replace    | `Ctrl+F` / `Ctrl+H` | Toggle theme  | `Ctrl+T`        |
| Zoom in / out     | `Ctrl+=` / `Ctrl+-` | Reset zoom    | `Ctrl+0`        |
| Quit              | `Ctrl+Q`        |                   |                 |

---

## 🚀 Installation and Setup

### 1. Clone the repository
```bash
git clone https://github.com/spsokhi/SuPY-IDE.git
cd SuPY-IDE
```

### 2. Create and activate a virtual environment (recommended)
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the IDE
```bash
python ide.py
```

---

## 📦 Packaging as an executable (optional)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed ide.py
```

The standalone executable will be created in the `dist/` folder.

> **Note:** when packaged, SuPY-IDE looks for a `python`/`python3` on your `PATH`
> to run your scripts in a separate process. Make sure Python is installed and on
> `PATH` on the target machine.

---

## 🗂️ Project structure

SuPY-IDE is intentionally kept as a **single file** so it is trivial to read,
copy and run:

```
SuPY-IDE/
├── ide.py            # the entire application
├── requirements.txt  # dependencies
├── .gitignore
└── readme.md
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to fork the project, open issues and submit
pull requests.

## 📄 License

This project is licensed under the **MIT License**.
