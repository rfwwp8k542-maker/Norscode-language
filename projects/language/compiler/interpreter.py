

from __future__ import annotations

import html
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
import webbrowser

try:  # pragma: no cover - GUI backend is optional at runtime
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover - fallback when Tk is unavailable
    tk = None
    ttk = None

TK_BG = "#12151d"
TK_PANEL = "#171c26"
TK_PANEL_ALT = "#1f2532"
TK_TEXT = "#f3f7ff"
TK_MUTED = "#9ea9bf"
TK_HEADLINE = "#dbe8ff"
TK_ACCENT = "#86c7ff"
TK_BORDER = "#2f3849"
TK_BUTTON_BG = "#dce7f5"
TK_BUTTON_ACTIVE = "#c6d8ef"
TK_BODY_FONT = ("Helvetica", 10)
TK_HEADER_FONT = ("Helvetica", 11, "bold")
TK_TITLE_FONT = ("Helvetica", 14, "bold")
TK_EDITOR_FONT = ("Courier New", 11)

from .ast_nodes import (
    BinOpNode,
    BlockNode,
    BoolNode,
    BreakNode,
    CallNode,
    ContinueNode,
    ExprStmtNode,
    IfExprNode,
    IfNode,
    FunctionNode,
    ForEachNode,
    IndexNode,
    IndexSetNode,
    ModuleCallNode,
    ListLiteralNode,
    NumberNode,
    ProgramNode,
    PrintNode,
    ReturnNode,
    StringNode,
    UnaryOpNode,
    VarAccessNode,
    VarDeclareNode,
    VarSetNode,
    WhileNode,
)


class ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value
        super().__init__()


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


@dataclass
class UserFunction:
    node: FunctionNode


class _HeadlessGuiBackend:
    def __init__(self):
        self.objects: dict[int, dict[str, Any]] = {}
        self.next_id = 1
        self.callback_runner = None
        self._active_events: set[tuple[int, str]] = set()

    def set_callback_runner(self, runner):
        self.callback_runner = runner

    def create_window(self, title: str) -> int:
        return self._create("window", None, title)

    def create_widget(self, kind: str, parent_id: int | None, text: str) -> int:
        return self._create(kind, parent_id, text)

    def _create(self, kind: str, parent_id: int | None, text: str) -> int:
        object_id = self.next_id
        self.next_id += 1
        self.objects[object_id] = {
            "kind": kind,
            "parent": parent_id,
            "text": "" if text is None else str(text),
            "visible": False,
            "click_callback": None,
            "change_callback": None,
            "key_callbacks": {},
            "selected_index": -1,
            "cursor_line": 1,
            "cursor_col": 1,
        }
        return object_id

    def _get(self, object_id: int) -> dict[str, Any]:
        if object_id not in self.objects:
            raise RuntimeError(f"Ukjent GUI-element: {object_id}")
        return self.objects[object_id]

    def set_text(self, object_id: int, text: Any) -> int:
        obj = self._get(object_id)
        obj["text"] = "" if text is None else str(text)
        if obj.get("kind") == "text_field":
            self._dispatch_event(object_id, "change", obj.get("change_callback"))
        elif obj.get("kind") == "editor":
            obj["cursor_line"] = 1
            obj["cursor_col"] = 1
        return object_id

    def get_text(self, object_id: int) -> str:
        return str(self._get(object_id).get("text", ""))

    def list_add(self, object_id: int, text: Any) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        obj.setdefault("items", []).append("" if text is None else str(text))
        return object_id

    def list_get(self, object_id: int, index: int) -> str:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        if 0 <= index < len(items):
            return str(items[index])
        return ""

    def list_clear(self, object_id: int) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        obj["items"] = []
        obj["selected_index"] = -1
        return object_id

    def list_remove(self, object_id: int, index: int) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        if 0 <= index < len(items):
            items.pop(index)
            selected = int(obj.get("selected_index", -1))
            if selected == index:
                obj["selected_index"] = -1
                self._dispatch_event(object_id, "change", obj.get("change_callback"))
            elif selected > index:
                obj["selected_index"] = selected - 1
        return object_id

    def list_select(self, object_id: int, index: int) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        previous = int(obj.get("selected_index", -1))
        obj["selected_index"] = index if 0 <= index < len(items) else -1
        if obj["selected_index"] != previous:
            self._dispatch_event(object_id, "change", obj.get("change_callback"))
        return object_id

    def list_selected_text(self, object_id: int) -> str:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        index = int(obj.get("selected_index", -1))
        if 0 <= index < len(items):
            return str(items[index])
        return ""

    def show(self, object_id: int) -> int:
        obj = self._get(object_id)
        obj["visible"] = True
        return object_id

    def close(self, object_id: int) -> int:
        obj = self._get(object_id)
        obj["visible"] = False
        return object_id

    def register_click(self, object_id: int, callback_name: Any) -> int:
        obj = self._get(object_id)
        obj["click_callback"] = "" if callback_name is None else str(callback_name)
        return object_id

    def register_change(self, object_id: int, callback_name: Any) -> int:
        obj = self._get(object_id)
        obj["change_callback"] = "" if callback_name is None else str(callback_name)
        return object_id

    def register_key(self, object_id: int, key_name: Any, callback_name: Any) -> int:
        obj = self._get(object_id)
        key_callbacks = obj.setdefault("key_callbacks", {})
        key_callbacks[self._normalize_key_name(key_name)] = "" if callback_name is None else str(callback_name)
        return object_id

    def trigger_click(self, object_id: int) -> int:
        obj = self._get(object_id)
        self._dispatch_event(object_id, "click", obj.get("click_callback"))
        return object_id

    def trigger_change(self, object_id: int) -> int:
        obj = self._get(object_id)
        self._dispatch_event(object_id, "change", obj.get("change_callback"))
        return object_id

    def trigger_key(self, object_id: int, key_name: Any) -> Any:
        obj = self._get(object_id)
        key_callbacks = obj.setdefault("key_callbacks", {})
        callback_name = key_callbacks.get(self._normalize_key_name(key_name))
        return self._dispatch_event(object_id, f"key:{self._normalize_key_name(key_name)}", callback_name)

    def editor_cursor(self, object_id: int) -> list[str]:
        obj = self._get(object_id)
        if obj.get("kind") != "editor":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        return [str(int(obj.get("cursor_line", 1))), str(int(obj.get("cursor_col", 1)))]

    def _replace_text_range(
        self,
        text: str,
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
        replacement: str,
    ) -> tuple[str, int, int]:
        lines = str(text).split("\n")
        if not lines:
            lines = [""]
        start_line = max(1, int(start_line))
        start_col = max(1, int(start_col))
        end_line = max(start_line, int(end_line))
        end_col = max(1, int(end_col))
        if start_line > len(lines):
            lines.extend([""] * (start_line - len(lines)))
        if end_line > len(lines):
            lines.extend([""] * (end_line - len(lines)))
        start_idx = start_line - 1
        end_idx = end_line - 1
        prefix = lines[start_idx][: max(0, start_col - 1)]
        suffix = lines[end_idx][max(0, end_col - 1) :]
        if start_idx == end_idx:
            lines[start_idx] = prefix + replacement + suffix
        else:
            lines[start_idx : end_idx + 1] = [prefix + replacement + suffix]
        updated = "\n".join(lines)
        if "\n" in replacement:
            repl_lines = replacement.split("\n")
            return updated, start_line + len(repl_lines) - 1, len(repl_lines[-1]) + 1
        return updated, start_line, start_col + len(replacement)

    def editor_replace_range(
        self,
        object_id: int,
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
        replacement: str,
    ) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "editor":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        updated, cursor_line, cursor_col = self._replace_text_range(
            self.get_text(object_id),
            start_line,
            start_col,
            end_line,
            end_col,
            "" if replacement is None else str(replacement),
        )
        obj["text"] = updated
        obj["cursor_line"] = cursor_line
        obj["cursor_col"] = cursor_col
        self._dispatch_event(object_id, "change", obj.get("change_callback"))
        return object_id

    def _dispatch_event(self, object_id: int, event_name: str, callback_name: Any):
        if not callback_name or self.callback_runner is None:
            return None
        key = (object_id, event_name)
        if key in self._active_events:
            return None
        self._active_events.add(key)
        try:
            return self.callback_runner(str(callback_name), object_id)
        finally:
            self._active_events.discard(key)

    def _normalize_key_name(self, key_name: Any) -> str:
        key = "" if key_name is None else str(key_name).strip()
        lowered = key.lower()
        if lowered in {"return", "kp_enter"}:
            return "enter"
        if lowered in {"tab"}:
            return "tab"
        if lowered in {"ctrl+space", "ctrl-space", "control+space", "control-space"}:
            return "ctrl+space"
        return lowered

    def parent_id(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception as exc:
            raise RuntimeError("GUI-forelder må være et heltall") from exc

    def child_at(self, parent_id: int, index: int) -> int:
        children = [object_id for object_id, obj in self.objects.items() if obj.get("parent") == parent_id]
        if index < 0 or index >= len(children):
            return 0
        return children[index]

    def has_visible_windows(self) -> bool:
        return any(obj.get("kind") == "window" and obj.get("visible") for obj in self.objects.values())

    def run(self) -> None:
        return None


class _BrowserGuiBackend(_HeadlessGuiBackend):
    def __init__(self):
        super().__init__()
        self.server: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.browser_url: str = ""

    def _children_of(self, parent_id: int | None) -> list[int]:
        return [object_id for object_id, obj in self.objects.items() if obj.get("parent") == parent_id]

    def _render_children(self, parent_id: int | None) -> str:
        return "".join(self._render_object(object_id) for object_id in self._children_of(parent_id))

    def _render_object(self, object_id: int) -> str:
        obj = self._get(object_id)
        kind = str(obj.get("kind", ""))
        text = html.escape(str(obj.get("text", "")))
        if kind == "window":
            title = html.escape(str(obj.get("text", "")))
            return (
                f"<section class='window' data-id='{object_id}'>"
                f"<header class='window-title'>{title}</header>"
                f"{self._render_children(object_id)}"
                "</section>"
            )
        if kind == "panel":
            return f"<section class='panel' data-id='{object_id}'>{self._render_children(object_id)}</section>"
        if kind == "row":
            return f"<section class='row' data-id='{object_id}'>{self._render_children(object_id)}</section>"
        if kind == "text":
            return f"<div class='text' data-id='{object_id}'>{text}</div>"
        if kind == "label":
            return f"<div class='label' data-id='{object_id}'>{text}</div>"
        if kind == "button":
            return (
                "<form class='widget-form button-form' method='post' action='/event'>"
                f"<input type='hidden' name='action' value='click'>"
                f"<input type='hidden' name='id' value='{object_id}'>"
                f"<button type='submit' class='button'>{text}</button>"
                "</form>"
            )
        if kind == "text_field":
            return (
                "<form class='widget-form text-form' method='post' action='/event'>"
                f"<input type='hidden' name='action' value='change'>"
                f"<input type='hidden' name='id' value='{object_id}'>"
                f"<input class='text-field' name='value' type='text' value='{text}' autocomplete='off'>"
                "<button type='submit' class='button'>Oppdater</button>"
                "</form>"
            )
        if kind == "editor":
            cursor_line = int(obj.get("cursor_line", 1))
            cursor_col = int(obj.get("cursor_col", 1))
            return (
                "<form class='widget-form editor-form' method='post' action='/event'>"
                f"<input type='hidden' name='action' value='editor-change'>"
                f"<input type='hidden' name='id' value='{object_id}'>"
                f"<textarea class='editor' name='value' spellcheck='false'>{text}</textarea>"
                "<div class='status-line'>"
                f"<span>Cursor {cursor_line}:{cursor_col}</span>"
                "<button type='submit' class='button'>Oppdater editor</button>"
                "</div>"
                "</form>"
            )
        if kind == "list":
            items = obj.get("items", [])
            selected_index = int(obj.get("selected_index", -1))
            options = []
            for index, item in enumerate(items):
                escaped_item = html.escape(str(item))
                selected = " selected" if index == selected_index else ""
                options.append(f"<option value='{index}'{selected}>{escaped_item}</option>")
            return (
                "<form class='widget-form list-form' method='post' action='/event'>"
                f"<input type='hidden' name='action' value='list-select'>"
                f"<input type='hidden' name='id' value='{object_id}'>"
                "<select class='list' name='value' size='8'>"
                + "".join(options)
                + "</select>"
                "<button type='submit' class='button'>Velg</button>"
                "</form>"
            )
        return f"<div class='text' data-id='{object_id}'>{text}</div>"

    def _render_page(self) -> str:
        windows = [object_id for object_id, obj in self.objects.items() if obj.get("kind") == "window" and obj.get("visible")]
        if not windows:
            windows = [object_id for object_id, obj in self.objects.items() if obj.get("kind") == "window"]
        body = "".join(self._render_object(object_id) for object_id in windows)
        if not body:
            body = "<section class='window'><header class='window-title'>Norscode</header><div class='text'>Ingen vinduer er åpne.</div></section>"
        return f"""<!doctype html>
<html lang='nb'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Norscode GUI</title>
<style>
body{{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e5e7eb;}}
.shell{{max-width:1280px;margin:0 auto;padding:24px;}}
.headline{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px;padding:16px 18px;border:1px solid rgba(148,163,184,.18);border-radius:18px;background:rgba(15,23,42,.92);}}
.headline h1{{margin:0;font-size:24px;}}
.headline p{{margin:4px 0 0;color:#94a3b8;}}
.window{{margin-bottom:18px;padding:18px;border-radius:18px;background:rgba(17,24,39,.92);border:1px solid rgba(148,163,184,.14);box-shadow:0 18px 42px rgba(15,23,42,.3);}}
.window-title{{font-size:18px;font-weight:700;margin-bottom:14px;color:#dbeafe;}}
.panel{{padding:14px;border-radius:16px;background:rgba(30,41,59,.7);border:1px solid rgba(148,163,184,.12);margin-bottom:12px;}}
.row{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:12px;}}
.text,.label{{padding:4px 0;line-height:1.45;white-space:pre-wrap;word-break:break-word;}}
.widget-form{{display:flex;flex-direction:column;gap:10px;margin-bottom:12px;}}
.button{{appearance:none;border:none;border-radius:12px;background:#dbeafe;color:#0f172a;font-weight:700;padding:10px 14px;cursor:pointer;}}
.button:hover{{background:#bfdbfe;}}
.text-field,.editor,.list{{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid rgba(148,163,184,.2);background:#111827;color:#e5e7eb;padding:10px;font:inherit;}}
.editor{{min-height:220px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;white-space:pre;}}
.status-line{{display:flex;justify-content:space-between;align-items:center;gap:12px;color:#94a3b8;font-size:13px;}}
.footer{{margin-top:18px;color:#94a3b8;font-size:13px;}}
</style>
</head>
<body>
<main class='shell'>
<section class='headline'>
<div>
<h1>Norscode GUI</h1>
<p>Lokalt vindu åpnet av Norscode. Bruk knapper, felt, editor og lister direkte i browseren.</p>
</div>
<div>Backend: browser</div>
</section>
{body}
<div class='footer'>Lukk denne fanen eller avslutt prosessen for å stoppe appen.</div>
</main>
</body>
</html>"""

    def _handle_event(self, payload: dict[str, list[str]]) -> None:
        action = (payload.get("action", [""])[0] or "").strip()
        object_id = int(payload.get("id", ["0"])[0] or 0)
        value = payload.get("value", [""])[0] if payload.get("value") else ""
        if action == "click":
            self.trigger_click(object_id)
        elif action == "change":
            self.set_text(object_id, value)
        elif action == "editor-change":
            self.set_text(object_id, value)
        elif action == "list-select":
            try:
                self.list_select(object_id, int(value))
            except Exception:
                self.list_select(object_id, -1)
        else:
            raise RuntimeError(f"Ukjent GUI-handling: {action}")

    def run(self) -> None:
        if not self.has_visible_windows():
            return

        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.startswith("/favicon"):
                    self.send_response(204)
                    self.end_headers()
                    return
                page = backend._render_page().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(length).decode("utf-8") if length else ""
                payload = parse_qs(body, keep_blank_values=True)
                try:
                    backend._handle_event(payload)
                    self.send_response(303)
                    self.send_header("Location", "/")
                except Exception as exc:
                    error_page = (
                        "<html><body style='font-family: system-ui; background:#0f172a; color:#e5e7eb; padding:24px;'>"
                        f"<h1>GUI-feil</h1><pre>{html.escape(str(exc))}</pre><p><a href='/'>Tilbake</a></p>"
                        "</body></html>"
                    ).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(error_page)))
                    self.end_headers()
                    self.wfile.write(error_page)
                    return
                self.end_headers()

            def log_message(self, *_args):  # noqa: D401
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = int(self.server.server_port)
        self.browser_url = f"http://127.0.0.1:{port}/"
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        webbrowser.open(self.browser_url)
        try:
            while self.has_visible_windows():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                if self.server is not None:
                    self.server.shutdown()
                    self.server.server_close()
            finally:
                self.server = None
                self.server_thread = None


class _TkGuiBackend(_HeadlessGuiBackend):
    def __init__(self):
        super().__init__()
        self.root = None
        self.window_roots: dict[int, Any] = {}
        self.widget_refs: dict[int, Any] = {}
        self.widget_vars: dict[int, Any] = {}
        self._suppress_widget_events: set[int] = set()

    def _ensure_tk(self):
        if tk is None:
            raise RuntimeError("Tkinter er ikke tilgjengelig")
        return tk

    def _apply_theme(self, root):
        if ttk is None:
            return
        try:
            style = ttk.Style(root)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            root.configure(bg=TK_BG)
            style.configure("TFrame", background=TK_BG)
            style.configure("TLabel", background=TK_BG, foreground=TK_HEADLINE)
            style.configure("TButton", background=TK_BUTTON_BG, foreground=TK_BG, padding=(10, 6))
            style.map(
                "TButton",
                background=[("active", TK_BUTTON_ACTIVE), ("pressed", TK_ACCENT)],
                foreground=[("active", TK_BG), ("pressed", TK_BG)],
            )
            style.configure(
                "TEntry",
                fieldbackground=TK_PANEL,
                foreground=TK_TEXT,
                insertcolor=TK_TEXT,
                bordercolor=TK_BORDER,
                lightcolor=TK_BORDER,
                darkcolor=TK_BORDER,
            )
        except Exception:
            pass

    def create_window(self, title: str) -> int:
        tk_mod = self._ensure_tk()
        object_id = super().create_window(title)
        root = tk_mod.Tk() if self.root is None else tk_mod.Toplevel(self.root)
        if self.root is None:
            self.root = root
            root.withdraw()
        else:
            root.withdraw()
        root.title(str(title))
        self._apply_theme(root)
        frame = tk_mod.Frame(root, bg=TK_BG, padx=18, pady=18)
        frame.pack(fill="both", expand=True)
        self.window_roots[object_id] = root
        self.widget_refs[object_id] = frame
        return object_id

    def create_widget(self, kind: str, parent_id: int | None, text: str) -> int:
        tk_mod = self._ensure_tk()
        parent_widget = self._parent_widget(parent_id)
        parent_kind = self._get(parent_id).get("kind") if parent_id is not None else "window"
        object_id = super().create_widget(kind, parent_id, text)

        if kind == "panel":
            widget = tk_mod.Frame(
                parent_widget,
                bg=TK_PANEL,
                bd=1,
                relief="solid",
                highlightbackground=TK_BORDER,
                highlightthickness=1,
                padx=12,
                pady=12,
            )
            if parent_kind == "row":
                widget.pack(side="left", fill="both", expand=True, padx=6, pady=6)
            else:
                widget.pack(fill="both", expand=True, pady=6)
        elif kind == "row":
            widget = tk_mod.Frame(
                parent_widget,
                bg=TK_BG,
                bd=0,
                highlightthickness=0,
                padx=10,
                pady=10,
            )
            widget.pack(fill="both", expand=True, pady=6)
        elif kind == "text":
            widget = tk_mod.Label(
                parent_widget,
                text=str(text),
                bg=TK_PANEL,
                fg=TK_MUTED,
                anchor="w",
                justify="left",
                font=TK_BODY_FONT,
            )
            if parent_kind == "row":
                widget.pack(side="left", anchor="w", pady=6, padx=6)
            else:
                widget.pack(anchor="w", pady=6)
        elif kind == "button":
            widget = tk_mod.Button(
                parent_widget,
                text=str(text),
                command=lambda oid=object_id: self._dispatch_event(oid, "click", self._get(oid).get("click_callback")),
                bg=TK_BUTTON_BG,
                fg=TK_BG,
                activebackground=TK_BUTTON_ACTIVE,
                activeforeground=TK_BG,
                relief="flat",
                bd=0,
                padx=10,
                pady=6,
                highlightthickness=0,
                font=TK_BODY_FONT,
            )
            if parent_kind == "row":
                widget.pack(side="left", pady=6, padx=6)
            else:
                widget.pack(fill="x", pady=6)
        elif kind == "label":
            widget = tk_mod.Label(
                parent_widget,
                text=str(text),
                bg=TK_PANEL,
                fg=TK_HEADLINE,
                anchor="w",
                justify="left",
                font=TK_HEADER_FONT,
            )
            if parent_kind == "row":
                widget.pack(side="left", anchor="w", pady=6, padx=6)
            else:
                widget.pack(anchor="w", pady=6)
        elif kind == "text_field":
            var = tk_mod.StringVar(master=self.root, value=str(text))
            widget = tk_mod.Entry(
                parent_widget,
                textvariable=var,
                bg=TK_PANEL_ALT,
                fg=TK_HEADLINE,
                insertbackground=TK_TEXT,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=TK_BORDER,
                highlightcolor=TK_ACCENT,
                font=TK_BODY_FONT,
            )
            if parent_kind == "row":
                widget.pack(side="left", fill="x", expand=True, pady=6, padx=6)
            else:
                widget.pack(fill="x", pady=6)
            self.widget_vars[object_id] = var
            var.trace_add(
                "write",
                lambda *_args, oid=object_id: None
                if oid in self._suppress_widget_events
                else self._dispatch_event(oid, "change", self._get(oid).get("change_callback")),
            )
        elif kind == "editor":
            widget = tk.Text(
                parent_widget,
                wrap="word",
                height=14,
                undo=True,
                bg=TK_PANEL,
                fg=TK_TEXT,
                insertbackground=TK_TEXT,
                selectbackground=TK_ACCENT,
                selectforeground=TK_BG,
                relief="flat",
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=TK_BORDER,
                highlightcolor=TK_ACCENT,
            )
            widget.configure(font=TK_EDITOR_FONT)
            widget.tag_configure("studio_keyword", foreground="#93ddff")
            widget.tag_configure("studio_string", foreground="#ffd37a")
            widget.tag_configure("studio_comment", foreground="#8791a8")
            widget.tag_configure("studio_number", foreground="#b6e891")
            widget.tag_configure("studio_current_line", background=TK_PANEL_ALT)
            if parent_kind == "row":
                widget.pack(side="left", fill="both", expand=True, pady=6, padx=6)
            else:
                widget.pack(fill="both", expand=True, pady=6)
            widget.insert("1.0", "" if text is None else str(text))
            self.widget_refs[object_id] = widget
            self._refresh_editor_highlighting(object_id)
            self._refresh_current_line(object_id)
            widget.bind(
                "<KeyRelease>",
                lambda _event, oid=object_id: self._on_editor_key_release(oid),
            )
            widget.bind(
                "<KeyPress>",
                lambda event, oid=object_id: self._on_editor_key_press(oid, event.keysym),
            )
            widget.bind(
                "<Control-space>",
                lambda _event, oid=object_id: self._on_editor_key_press(oid, "Ctrl+Space"),
            )
            widget.bind(
                "<ButtonRelease-1>",
                lambda _event, oid=object_id: self._sync_editor_cursor(oid) or self._refresh_current_line(oid),
            )
        elif kind == "list":
            widget = tk_mod.Listbox(
                parent_widget,
                height=6,
                bg=TK_PANEL_ALT,
                fg=TK_TEXT,
                selectbackground=TK_ACCENT,
                selectforeground=TK_BG,
                activestyle="none",
                highlightthickness=1,
                highlightbackground=TK_BORDER,
                relief="flat",
                bd=0,
                font=TK_BODY_FONT,
            )
            if parent_kind == "row":
                widget.pack(side="left", fill="both", expand=True, pady=6, padx=6)
            else:
                widget.pack(fill="both", expand=True, pady=6)
            widget.bind(
                "<<ListboxSelect>>",
                lambda _event, oid=object_id: self._sync_list_selection(oid),
            )
        else:
            raise RuntimeError(f"Ukjent GUI-widget: {kind}")

        self.widget_refs[object_id] = widget
        return object_id

    def _on_editor_key_release(self, object_id: int) -> None:
        if object_id in self._suppress_widget_events:
            return None
        self._sync_editor_cursor(object_id)
        self._dispatch_event(object_id, "change", self._get(object_id).get("change_callback"))
        self._refresh_editor_highlighting(object_id)
        self._refresh_current_line(object_id)
        return None

    def _on_editor_key_press(self, object_id: int, key_name: Any) -> str | None:
        if object_id in self._suppress_widget_events:
            return None
        normalized = self._normalize_key_name(key_name)
        widget = self.widget_refs.get(object_id)
        obj = self._get(object_id)
        callback_name = obj.setdefault("key_callbacks", {}).get(normalized)
        handled = self._dispatch_event(object_id, f"key:{normalized}", callback_name)
        if handled:
            return "break"
        if normalized == "ctrl+space":
            return "break"
        if normalized == "tab" and widget is not None:
            try:
                widget.insert("insert", "    ")
                self._sync_editor_cursor(object_id)
                self._refresh_editor_highlighting(object_id)
                self._refresh_current_line(object_id)
                return "break"
            except Exception:
                return "break"
        return None

    def _sync_editor_cursor(self, object_id: int) -> None:
        widget = self.widget_refs.get(object_id)
        if widget is None or self._get(object_id).get("kind") != "editor":
            return
        try:
            line_text, col_text = widget.index("insert").split(".")
            obj = self._get(object_id)
            obj["cursor_line"] = int(line_text)
            obj["cursor_col"] = int(col_text) + 1
        except Exception:
            return

    def _refresh_current_line(self, object_id: int) -> None:
        widget = self.widget_refs.get(object_id)
        if widget is None or self._get(object_id).get("kind") != "editor":
            return
        try:
            widget.tag_remove("studio_current_line", "1.0", "end")
            line = widget.index("insert").split(".")[0]
            widget.tag_add("studio_current_line", f"{line}.0", f"{line}.0 lineend")
            widget.tag_lower("studio_current_line")
        except Exception:
            return

    def editor_jump_to_line(self, object_id: int, line_number: int) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "editor":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        line = int(line_number)
        if line < 1:
            line = 1
        obj["cursor_line"] = line
        obj["cursor_col"] = 1
        widget = self.widget_refs.get(object_id)
        if widget is not None:
            try:
                target = f"{line}.0"
                widget.mark_set("insert", target)
                widget.see(target)
                widget.focus_set()
                self._sync_editor_cursor(object_id)
                self._refresh_current_line(object_id)
            except Exception:
                pass
        return object_id

    def editor_cursor(self, object_id: int) -> list[str]:
        obj = self._get(object_id)
        if obj.get("kind") != "editor":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        self._sync_editor_cursor(object_id)
        return [str(int(obj.get("cursor_line", 1))), str(int(obj.get("cursor_col", 1)))]

    def editor_replace_range(
        self,
        object_id: int,
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
        replacement: str,
    ) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "editor":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        widget = self.widget_refs.get(object_id)
        updated, cursor_line, cursor_col = self._replace_text_range(
            widget.get("1.0", "end-1c") if widget is not None else obj.get("text", ""),
            start_line,
            start_col,
            end_line,
            end_col,
            "" if replacement is None else str(replacement),
        )
        self._suppress_widget_events.add(object_id)
        try:
            if widget is not None:
                widget.delete("1.0", "end")
                widget.insert("1.0", updated)
                target = f"{cursor_line}.{max(0, cursor_col - 1)}"
                widget.mark_set("insert", target)
                widget.see(target)
        finally:
            self._suppress_widget_events.discard(object_id)
        obj["text"] = updated
        obj["cursor_line"] = cursor_line
        obj["cursor_col"] = cursor_col
        self._refresh_editor_highlighting(object_id)
        self._refresh_current_line(object_id)
        self._dispatch_event(object_id, "change", obj.get("change_callback"))
        return object_id

    def _refresh_editor_highlighting(self, object_id: int) -> None:
        widget = self.widget_refs.get(object_id)
        if widget is None or self._get(object_id).get("kind") != "editor":
            return
        try:
            text = widget.get("1.0", "end-1c")
            for tag in ("studio_keyword", "studio_string", "studio_comment", "studio_number"):
                widget.tag_remove(tag, "1.0", "end")
            patterns = (
                ("studio_comment", r"#[^\n]*"),
                ("studio_string", r"\"[^\"\\]*(?:\\.[^\"\\]*)*\""),
                ("studio_string", r"'[^'\\]*(?:\\.[^'\\]*)*'"),
                (
                    "studio_keyword",
                    r"\b(?:bruk|som|funksjon|start|returner|hvis|ellers|da|mens|for|i|bryt|fortsett|sann|usann|og|eller|ikke|la)\b",
                ),
                ("studio_number", r"\b\d+\b"),
            )
            for tag, pattern in patterns:
                for match in re.finditer(pattern, text, re.MULTILINE):
                    start = f"1.0 + {match.start()} chars"
                    end = f"1.0 + {match.end()} chars"
                    widget.tag_add(tag, start, end)
        except Exception:
            return

    def _parent_widget(self, parent_id: int | None):
        if parent_id is None:
            if self.root is None:
                raise RuntimeError("GUI-vindu må opprettes før widgets")
            return self.widget_refs.get(next(iter(self.window_roots.keys())), self.root)
        if parent_id in self.widget_refs:
            widget = self.widget_refs[parent_id]
            if parent_id in self.window_roots:
                return widget
            return widget
        raise RuntimeError(f"Ukjent GUI-forelder: {parent_id}")

    def set_text(self, object_id: int, text: Any) -> int:
        obj = self._get(object_id)
        obj["text"] = "" if text is None else str(text)
        widget = self.widget_refs.get(object_id)
        if widget is None:
            if obj.get("kind") == "text_field":
                self._dispatch_event(object_id, "change", obj.get("change_callback"))
            return object_id
        if object_id in self.widget_vars:
            self._suppress_widget_events.add(object_id)
            try:
                self.widget_vars[object_id].set("" if text is None else str(text))
            finally:
                self._suppress_widget_events.discard(object_id)
            return object_id
        if obj.get("kind") == "editor":
            self._suppress_widget_events.add(object_id)
            try:
                widget.delete("1.0", "end")
                widget.insert("1.0", "" if text is None else str(text))
            finally:
                self._suppress_widget_events.discard(object_id)
            obj["cursor_line"] = 1
            obj["cursor_col"] = 1
            try:
                widget.mark_set("insert", "1.0")
            except Exception:
                pass
            self._refresh_editor_highlighting(object_id)
            self._refresh_current_line(object_id)
            return object_id
        try:
            widget.configure(text="" if text is None else str(text))
        except Exception:
            pass
        return object_id

    def get_text(self, object_id: int) -> str:
        if object_id in self.widget_vars:
            return str(self.widget_vars[object_id].get())
        widget = self.widget_refs.get(object_id)
        if widget is not None:
            if self._get(object_id).get("kind") == "editor":
                return str(widget.get("1.0", "end-1c"))
            try:
                return str(widget.cget("text"))
            except Exception:
                pass
        return super().get_text(object_id)

    def list_add(self, object_id: int, text: Any) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        widget = self.widget_refs.get(object_id)
        if widget is not None:
            widget.insert("end", "" if text is None else str(text))
        obj.setdefault("items", []).append("" if text is None else str(text))
        return object_id

    def list_clear(self, object_id: int) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        widget = self.widget_refs.get(object_id)
        if widget is not None:
            widget.delete(0, "end")
        obj["items"] = []
        obj["selected_index"] = -1
        return object_id

    def list_select(self, object_id: int, index: int) -> int:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        widget = self.widget_refs.get(object_id)
        items = obj.setdefault("items", [])
        if 0 <= index < len(items):
            obj["selected_index"] = index
            if widget is not None:
                widget.selection_clear(0, "end")
                widget.selection_set(index)
                widget.see(index)
        else:
            obj["selected_index"] = -1
            if widget is not None:
                widget.selection_clear(0, "end")
        return object_id

    def list_selected_text(self, object_id: int) -> str:
        obj = self._get(object_id)
        if obj.get("kind") != "list":
            raise RuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        index = int(obj.get("selected_index", -1))
        if 0 <= index < len(items):
            return str(items[index])
        return ""

    def _sync_list_selection(self, object_id: int) -> None:
        widget = self.widget_refs.get(object_id)
        if widget is None:
            return
        selection = widget.curselection()
        obj = self._get(object_id)
        previous = int(obj.get("selected_index", -1))
        obj["selected_index"] = int(selection[0]) if selection else -1
        if obj["selected_index"] != previous:
            self._dispatch_event(object_id, "change", obj.get("change_callback"))

    def show(self, object_id: int) -> int:
        obj = self._get(object_id)
        obj["visible"] = True
        root = self.window_roots.get(object_id)
        if root is not None:
            root.deiconify()
            root.lift()
            root.focus_force()
        return object_id

    def close(self, object_id: int) -> int:
        obj = self._get(object_id)
        obj["visible"] = False
        root = self.window_roots.get(object_id)
        if root is not None:
            root.destroy()
        return object_id

    def register_click(self, object_id: int, callback_name: Any) -> int:
        obj = self._get(object_id)
        obj["click_callback"] = "" if callback_name is None else str(callback_name)
        widget = self.widget_refs.get(object_id)
        if widget is not None and obj.get("kind") == "button":
            widget.configure(command=lambda oid=object_id: self._dispatch_event(oid, "click", self._get(oid).get("click_callback")))
        return object_id

    def register_change(self, object_id: int, callback_name: Any) -> int:
        obj = self._get(object_id)
        obj["change_callback"] = "" if callback_name is None else str(callback_name)
        return object_id

    def register_key(self, object_id: int, key_name: Any, callback_name: Any) -> int:
        obj = self._get(object_id)
        obj.setdefault("key_callbacks", {})[self._normalize_key_name(key_name)] = "" if callback_name is None else str(callback_name)
        return object_id

    def trigger_click(self, object_id: int) -> int:
        widget = self.widget_refs.get(object_id)
        if widget is not None and self._get(object_id).get("kind") == "button":
            try:
                widget.invoke()
                return object_id
            except Exception:
                pass
        return super().trigger_click(object_id)

    def trigger_change(self, object_id: int) -> int:
        return self._dispatch_event(object_id, "change", self._get(object_id).get("change_callback")) or object_id

    def trigger_key(self, object_id: int, key_name: Any) -> Any:
        obj = self._get(object_id)
        callback_name = obj.setdefault("key_callbacks", {}).get(self._normalize_key_name(key_name))
        return self._dispatch_event(object_id, f"key:{self._normalize_key_name(key_name)}", callback_name)

    def child_at(self, parent_id: int, index: int) -> int:
        return super().child_at(parent_id, index)

    def has_visible_windows(self) -> bool:
        return any(
            obj.get("kind") == "window" and obj.get("visible") and root.winfo_exists()
            for object_id, obj in self.objects.items()
            if (root := self.window_roots.get(object_id)) is not None
        )

    def run(self) -> None:
        if self.root is None:
            return
        if self.has_visible_windows():
            self.root.mainloop()


class Interpreter:
    def __init__(self, gui_backend: str = "headless", alias_map: dict[str, str] | None = None):
        self.globals: dict[str, Any] = {}
        self.functions: dict[str, UserFunction] = {}
        self.modules: dict[str, Any] = {}
        self.scopes: list[dict[str, Any]] = [self.globals]
        self.function_stack: list[str] = []
        self.alias_map = alias_map or {}
        self.gui_backend = self._make_gui_backend(gui_backend)
        if hasattr(self.gui_backend, "set_callback_runner"):
            self.gui_backend.set_callback_runner(self._invoke_gui_callback)

    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        self.scopes.pop()

    def current_scope(self) -> dict[str, Any]:
        return self.scopes[-1]

    def _make_gui_backend(self, mode: str):
        if mode == "browser":
            return _BrowserGuiBackend()
        if mode != "tk" or tk is None:
            return _HeadlessGuiBackend()
        try:
            return _TkGuiBackend()
        except Exception:
            return _HeadlessGuiBackend()

    def _callback_candidates(self, name: str) -> list[str]:
        candidates = [name]
        if "." in name:
            module_name, func_name = name.rsplit(".", 1)
            real_module = self.alias_map.get(module_name, module_name)
            for candidate in (
                f"{module_name}.{func_name}",
                f"{real_module}.{func_name}",
            ):
                if candidate not in candidates:
                    candidates.append(candidate)
        return candidates

    def _invoke_gui_callback(self, callback_name: str, widget_id: int):
        for candidate in self._callback_candidates(callback_name):
            if candidate in self.functions:
                return self.call_user_function(candidate, [widget_id])
        raise RuntimeError(f"Ukjent GUI-callback: {callback_name}")

    def _current_function_candidates(self, name: str) -> list[str]:
        candidates = [name]
        if self.function_stack:
            current_name = self.function_stack[-1]
            fn = self.functions.get(current_name)
            if fn is not None:
                module_name = getattr(fn.node, "module_name", None)
                if module_name and module_name != "__main__":
                    scoped_name = f"{module_name}.{name}"
                    if scoped_name not in candidates:
                        candidates.insert(0, scoped_name)
        return candidates

    def _sass_replace_variables(self, text: str, variables: dict[str, str]) -> str:
        result = text
        for name, value in variables.items():
            result = result.replace(f"${name}", value)
        return result

    def _sass_to_css(self, source: str) -> str:
        variables: dict[str, str] = {}
        selector_stack: list[str] = []
        output: list[str] = []

        for raw_line in source.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("/*") or line.startswith("*"):
                continue

            if line.startswith("$") and ":" in line and line.endswith(";"):
                name, value = line[1:].split(":", 1)
                variables[name.strip()] = self._sass_replace_variables(value.strip().rstrip(";"), variables)
                continue

            line = self._sass_replace_variables(line, variables)

            if line.endswith("{"):
                selector = line[:-1].strip()
                if selector.startswith("&") and selector_stack:
                    selector = selector.replace("&", selector_stack[-1], 1)
                elif selector_stack:
                    selector = f"{selector_stack[-1]} {selector}"
                selector_stack.append(selector)
                continue

            if line == "}":
                if selector_stack:
                    selector_stack.pop()
                continue

            if ":" in line and line.endswith(";"):
                current_selector = selector_stack[-1] if selector_stack else ""
                if current_selector:
                    output.append(f"{current_selector} {{ {line} }}")
                else:
                    output.append(line)
                continue

        return "\n".join(output) + ("\n" if output else "")

    def define_var(self, name: str, value: Any):
        self.current_scope()[name] = value

    def set_var(self, name: str, value: Any):
        for scope in reversed(self.scopes):
            if name in scope:
                scope[name] = value
                return value
        raise NameError(f"Ukjent variabel: {name}")

    def get_var(self, name: str) -> Any:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise NameError(f"Ukjent variabel: {name}")

    def run(self, program: ProgramNode):
        for fn in getattr(program, "functions", []):
            key = fn.name
            module_name = getattr(fn, "module_name", None)
            if module_name and module_name != "__main__":
                key = f"{module_name}.{fn.name}"
            self.functions[key] = UserFunction(fn)
            if key == fn.name:
                self.functions[fn.name] = UserFunction(fn)

        for fn in getattr(program, "tests", []):
            key = fn.name
            module_name = getattr(fn, "module_name", None)
            if module_name and module_name != "__main__":
                key = f"{module_name}.{fn.name}"
            self.functions[key] = UserFunction(fn)
            if key == fn.name:
                self.functions[fn.name] = UserFunction(fn)

        if "start" not in self.functions:
            return None
        result = self.call_user_function("start", [])
        self.gui_backend.run()
        return result

    def eval(self, node):
        if isinstance(node, NumberNode):
            return node.value

        if isinstance(node, StringNode):
            return node.value

        if isinstance(node, BoolNode):
            return node.value

        if isinstance(node, VarAccessNode):
            return self.get_var(node.name)

        if isinstance(node, VarDeclareNode):
            value = self.eval(node.expr)
            self.define_var(node.name, value)
            return value

        if isinstance(node, VarSetNode):
            value = self.eval(node.expr)
            return self.set_var(node.name, value)

        if isinstance(node, IndexNode):
            target = self.eval(node.target)
            index = self.eval(node.index_expr)
            try:
                return target[index]
            except Exception as exc:
                raise RuntimeError(f"Ugyldig indeksbruk: {exc}") from exc

        if isinstance(node, IndexSetNode):
            target = self.get_var(node.target_name)
            index = self.eval(node.index_expr)
            value = self.eval(node.value_expr)
            try:
                target[index] = value
                return value
            except Exception as exc:
                raise RuntimeError(f"Ugyldig indeks-oppdatering: {exc}") from exc

        if isinstance(node, UnaryOpNode):
            value = self.eval(node.node)
            op_type = node.op.typ

            if op_type == "PLUS":
                return +value
            if op_type == "MINUS":
                return -value
            if op_type == "IKKE":
                return not value

            raise RuntimeError(f"Ukjent unary operator: {op_type}")

        if isinstance(node, BinOpNode):
            left = self.eval(node.left)
            right = self.eval(node.right)
            op_type = node.op.typ

            if op_type == "PLUS":
                return left + right
            if op_type == "MINUS":
                return left - right
            if op_type == "MUL":
                return left * right
            if op_type == "DIV":
                return left / right
            if op_type == "PERCENT":
                return left % right
            if op_type == "EQ":
                return left == right
            if op_type == "NE":
                return left != right
            if op_type == "GT":
                return left > right
            if op_type == "LT":
                return left < right
            if op_type == "GTE":
                return left >= right
            if op_type == "LTE":
                return left <= right
            if op_type == "OG":
                return bool(left) and bool(right)
            if op_type == "ELLER":
                return bool(left) or bool(right)

            raise RuntimeError(f"Ukjent operator: {op_type}")

        if isinstance(node, IfExprNode):
            return self.eval(node.then_expr if self.eval(node.condition) else node.else_expr)

        if isinstance(node, IfNode):
            if self.eval(node.condition):
                self.eval(node.then_block)
                return None
            for elif_cond, elif_block in getattr(node, "elif_blocks", []):
                if self.eval(elif_cond):
                    self.eval(elif_block)
                    return None
            if node.else_block is not None:
                self.eval(node.else_block)
            return None

        if isinstance(node, WhileNode):
            while self.eval(node.condition):
                try:
                    self.eval(node.body)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return None

        if isinstance(node, ExprStmtNode):
            return self.eval(node.expr)

        if isinstance(node, PrintNode):
            value = self.eval(node.expr)
            print(value)
            return value

        if isinstance(node, ReturnNode):
            raise ReturnSignal(self.eval(node.expr))

        if isinstance(node, BreakNode):
            raise BreakSignal()

        if isinstance(node, ContinueNode):
            raise ContinueSignal()

        if isinstance(node, BlockNode):
            result = None
            for stmt in node.statements:
                result = self.eval(stmt)
            return result

        if isinstance(node, WhileNode):
            while self.eval(node.condition):
                try:
                    self.eval(node.body)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return None

        if isinstance(node, ForEachNode):
            items = self.eval(node.list_expr)
            for item in items:
                self.push_scope()
                try:
                    self.define_var(node.item_name, item)
                    try:
                        self.eval(node.body)
                    except ContinueSignal:
                        continue
                    except BreakSignal:
                        break
                finally:
                    self.pop_scope()
            return None

        if isinstance(node, CallNode):
            return self.eval_call(node.name, node.args)

        if isinstance(node, ModuleCallNode):
            return self.eval_module_call(node.module_name, node.func_name, node.args)

        if isinstance(node, ListLiteralNode):
            return [self.eval(item) for item in node.items]

        raise RuntimeError(f"Kan ikke evaluere node: {type(node).__name__}")

    def eval_call(self, name: str, args: list[Any]):
        values = [self.eval(arg) for arg in args]

        if name == "skriv":
            print(*values)
            return None

        if name == "assert":
            if not values[0]:
                raise AssertionError("Assert feilet")
            return None

        if name == "assert_eq":
            if values[0] != values[1]:
                raise AssertionError(f"assert_eq feilet: {values[0]!r} != {values[1]!r}")
            return None

        if name == "assert_ne":
            if values[0] == values[1]:
                raise AssertionError(f"assert_ne feilet: {values[0]!r} == {values[1]!r}")
            return None

        if name == "tekst_fra_heltall":
            return str(values[0])

        if name == "tekst_fra_bool":
            return "sann" if values[0] else "usann"

        if name == "tekst_til_små":
            return str(values[0]).lower()

        if name == "tekst_til_store":
            return str(values[0]).upper()

        if name == "tekst_til_tittel":
            text = str(values[0])
            out: list[str] = []
            new_word = True
            for ch in text:
                if ch.isalnum() or ch == "_" or ch in "æøåÆØÅ":
                    out.append(ch.upper() if new_word else ch.lower())
                    new_word = False
                else:
                    out.append(ch)
                    new_word = True
            return "".join(out)

        if name == "tekst_omvendt":
            return str(values[0])[::-1]

        if name == "tekst_del_på":
            text = str(values[0])
            separator = str(values[1] if len(values) > 1 else "")
            if separator == "":
                return [text]
            return text.split(separator)

        if name == "del_på":
            text = str(values[0])
            separator = str(values[1] if len(values) > 1 else "")
            if separator == "":
                return [text]
            return text.split(separator)

        if name == "heltall_fra_tekst":
            try:
                return int(str(values[0]).strip())
            except Exception:
                return 0

        if name == "tekst_slutter_med":
            return str(values[0]).endswith(str(values[1] if len(values) > 1 else ""))

        if name == "tekst_starter_med":
            return str(values[0]).startswith(str(values[1] if len(values) > 1 else ""))

        if name == "tekst_inneholder":
            return str(values[1] if len(values) > 1 else "") in str(values[0])

        if name == "tekst_erstatt":
            return str(values[0]).replace(str(values[1] if len(values) > 1 else ""), str(values[2] if len(values) > 2 else ""))

        if name == "del_linjer":
            return str(values[0]).split("\n")

        if name == "del_ord":
            return str(values[0]).split()

        if name == "tekst_er_ordtegn":
            text = str(values[0])
            return len(text) == 1 and (text[0].isalnum() or text in "_æøåÆØÅ")

        if name == "tokeniser_enkel":
            text = str(values[0])
            tokens: list[str] = []
            current: list[str] = []
            in_comment = False
            for ch in text:
                if in_comment:
                    if ch == "\n":
                        in_comment = False
                    continue
                if ch == "#":
                    if current:
                        tokens.append("".join(current))
                        current = []
                    in_comment = True
                    continue
                if ch.isalnum() or ch in "_-":
                    current.append(ch)
                else:
                    if current:
                        tokens.append("".join(current))
                        current = []
            if current:
                tokens.append("".join(current))
            return tokens

        if name == "tokeniser_uttrykk":
            import re

            token_re = re.compile(
                r"<=>|<->|=>|->|<-|&&|\|\||\+=|-=|\*=|/=|%=|==|!=|<=|>=|<>|[=!(){}\[\],.:;+\-*/%<>]|\"[^\"\\]*(?:\\.[^\"\\]*)*\"|[A-Za-zÆØÅæøå_][A-Za-zÆØÅæøå0-9_]*|\d+|\S"
            )
            return [m.group(0) for m in token_re.finditer(str(values[0])) if m.group(0).strip()]

        if name == "les_input":
            return ""

        if name == "fil_eksisterer":
            from pathlib import Path

            return Path(str(values[0])).expanduser().exists()

        if name == "les_miljo":
            import os

            return os.environ.get(str(values[0]), "")

        if name == "argv":
            import os

            raw_args = os.environ.get("NORSCODE_ARGS", "")
            return [line for line in raw_args.splitlines() if line != ""]

        if name == "tekst_trim":
            return str(values[0]).strip()

        if name == "tekst_slice":
            text = str(values[0])
            start = int(values[1]) if len(values) > 1 else 0
            end = int(values[2]) if len(values) > 2 else len(text)
            if start < 0:
                start = 0
            if end < start:
                end = start
            if start > len(text):
                start = len(text)
            if end > len(text):
                end = len(text)
            return text[start:end]

        if name == "tekst_lengde":
            return len(str(values[0]))

        if name == "sass_til_css":
            return self._sass_to_css(str(values[0]))

        if name == "kjør_kommando":
            command = [str(item) for item in (values[0] if values else [])]
            if not command:
                return 1
            completed = subprocess.run(command, check=False)
            return int(completed.returncode)

        if name == "liste_filer":
            from pathlib import Path

            root = Path(str(values[0] if values else ".")).expanduser()
            if not root.exists():
                return []
            result: list[str] = []
            for path in sorted(root.rglob("*")):
                if path.is_file() and not any(part.startswith(".") for part in path.parts):
                    if path.suffix.lower() in {".no", ".md", ".toml", ".py", ".sh", ".ps1"}:
                        try:
                            result.append(str(path.relative_to(root)))
                        except Exception:
                            result.append(str(path))
            return result

        if name == "liste_filer_tre" or name == "gui_liste_filer_tre":
            from pathlib import Path

            root = Path(str(values[0] if values else ".")).expanduser()
            if not root.exists():
                return []
            result: list[str] = []

            def walk(path: Path, prefix: str = "") -> None:
                entries = sorted(
                    [child for child in path.iterdir() if not child.name.startswith(".") and child.name not in {"build", "dist", "__pycache__", ".venv"}],
                    key=lambda child: (not child.is_dir(), child.name.lower()),
                )
                for child in entries:
                    if child.is_dir():
                        result.append(f"{prefix}{child.name}/")
                        walk(child, prefix + "  ")
                    elif child.suffix.lower() in {".no", ".md", ".toml", ".py", ".sh", ".ps1"}:
                        try:
                            rel = child.relative_to(root)
                            result.append(f"{prefix}{rel.as_posix()}")
                        except Exception:
                            result.append(f"{prefix}{child.name}")

            walk(root)
            return result

        if name == "les_fil":
            from pathlib import Path

            path = Path(str(values[0])).expanduser()
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return ""

        if name == "skriv_fil":
            from pathlib import Path

            path = Path(str(values[0])).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("" if len(values) < 2 or values[1] is None else str(values[1]), encoding="utf-8")
            return 1

        if name == "kjor_kilde":
            import io
            from contextlib import redirect_stdout, redirect_stderr
            from pathlib import Path

            source = "" if not values else str(values[0])
            buffer = io.StringIO()
            try:
                from .lexer import Lexer
                from .parser import Parser
                from .semantic import SemanticAnalyzer

                program = Parser(Lexer(source)).parse()
                SemanticAnalyzer(alias_map=self.alias_map).analyze(program)
                runner = Interpreter(gui_backend="headless", alias_map=self.alias_map)
                with redirect_stdout(buffer), redirect_stderr(buffer):
                    runner.run(program)
            except Exception as exc:
                return f"Feil: {exc}"
            return buffer.getvalue()

        if name == "lengde":
            return len(values[0])

        if name == "legg_til":
            values[0].append(values[1])
            return None

        if name == "pop_siste":
            if not values[0]:
                return "" if isinstance(values[0], list) and any(isinstance(x, str) for x in values[0]) else 0
            return values[0].pop()

        if name == "fjern_indeks":
            if values[1] < 0 or values[1] >= len(values[0]):
                return len(values[0])
            values[0].pop(values[1])
            return len(values[0])

        if name == "sett_inn":
            lst = values[0]
            idx = int(values[1])
            value = values[2]
            if idx < 0:
                idx = 0
            if idx < len(lst):
                lst[idx] = value
            elif idx == len(lst):
                lst.append(value)
            else:
                while len(lst) < idx:
                    lst.append(0 if not lst or not isinstance(lst[0], str) else "")
                lst.append(value)
            return None

        if name == "gui_vindu":
            return self.gui_backend.create_window(values[0] if values else "")

        if name == "gui_panel":
            return self.gui_backend.create_widget("panel", self.gui_backend.parent_id(values[0] if values else None), "")

        if name == "gui_rad":
            return self.gui_backend.create_widget("row", self.gui_backend.parent_id(values[0] if values else None), "")

        if name == "gui_tekst":
            return self.gui_backend.create_widget("text", self.gui_backend.parent_id(values[0] if values else None), values[1] if len(values) > 1 else "")

        if name == "gui_tekstboks":
            return self.gui_backend.create_widget("text_field", self.gui_backend.parent_id(values[0] if values else None), values[1] if len(values) > 1 else "")

        if name == "gui_editor":
            return self.gui_backend.create_widget("editor", self.gui_backend.parent_id(values[0] if values else None), values[1] if len(values) > 1 else "")

        if name == "gui_editor_hopp_til":
            return self.gui_backend.editor_jump_to_line(int(values[0]), int(values[1]) if len(values) > 1 else 1)

        if name == "gui_editor_cursor":
            return self.gui_backend.editor_cursor(int(values[0]))

        if name == "gui_editor_erstatt_fra_til":
            return self.gui_backend.editor_replace_range(
                int(values[0]),
                int(values[1]) if len(values) > 1 else 1,
                int(values[2]) if len(values) > 2 else 1,
                int(values[3]) if len(values) > 3 else int(values[1]) if len(values) > 1 else 1,
                int(values[4]) if len(values) > 4 else int(values[2]) if len(values) > 2 else 1,
                values[5] if len(values) > 5 else "",
            )

        if name == "gui_liste":
            return self.gui_backend.create_widget("list", self.gui_backend.parent_id(values[0] if values else None), "")

        if name == "gui_liste_legg_til":
            return self.gui_backend.list_add(int(values[0]), values[1] if len(values) > 1 else "")

        if name == "gui_liste_tom":
            return self.gui_backend.list_clear(int(values[0]))

        if name == "gui_liste_antall":
            return len(self.gui_backend._get(int(values[0])).get("items", []))

        if name == "gui_liste_filer_tre":
            from pathlib import Path

            root = Path(str(values[0] if values else ".")).expanduser()
            if not root.exists():
                return []
            result: list[str] = []

            def walk(path: Path, prefix: str = "") -> None:
                entries = sorted(
                    [child for child in path.iterdir() if not child.name.startswith(".") and child.name not in {"build", "dist", "__pycache__", ".venv"}],
                    key=lambda child: (not child.is_dir(), child.name.lower()),
                )
                for child in entries:
                    if child.is_dir():
                        result.append(f"{prefix}{child.name}/")
                        walk(child, prefix + "  ")
                    elif child.suffix.lower() in {".no", ".md", ".toml", ".py", ".sh", ".ps1"}:
                        try:
                            rel = child.relative_to(root)
                            result.append(f"{prefix}{rel.as_posix()}")
                        except Exception:
                            result.append(f"{prefix}{child.name}")

            walk(root)
            return result

        if name == "gui_liste_hent":
            return self.gui_backend.list_get(int(values[0]), int(values[1]) if len(values) > 1 else 0)

        if name == "gui_liste_fjern":
            return self.gui_backend.list_remove(int(values[0]), int(values[1]) if len(values) > 1 else 0)

        if name == "gui_liste_valgt":
            return self.gui_backend.list_selected_text(int(values[0]))

        if name == "gui_liste_velg":
            return self.gui_backend.list_select(int(values[0]), int(values[1]) if len(values) > 1 else 0)

        if name == "gui_på_klikk":
            return self.gui_backend.register_click(int(values[0]), values[1] if len(values) > 1 else "")

        if name == "gui_på_endring":
            return self.gui_backend.register_change(int(values[0]), values[1] if len(values) > 1 else "")

        if name == "gui_på_tast":
            return self.gui_backend.register_key(
                int(values[0]),
                values[1] if len(values) > 1 else "",
                values[2] if len(values) > 2 else "",
            )

        if name == "gui_trykk":
            return self.gui_backend.trigger_click(int(values[0]))

        if name == "gui_trykk_tast":
            return self.gui_backend.trigger_key(int(values[0]), values[1] if len(values) > 1 else "")

        if name == "gui_foresatt":
            parent_id = self.gui_backend._get(int(values[0])).get("parent")
            return 0 if parent_id is None else int(parent_id)

        if name == "gui_barn":
            return self.gui_backend.child_at(int(values[0]), int(values[1]) if len(values) > 1 else 0)

        if name == "gui_knapp":
            return self.gui_backend.create_widget("button", self.gui_backend.parent_id(values[0] if values else None), values[1] if len(values) > 1 else "")

        if name == "gui_etikett":
            return self.gui_backend.create_widget("label", self.gui_backend.parent_id(values[0] if values else None), values[1] if len(values) > 1 else "")

        if name == "gui_tekstfelt":
            return self.gui_backend.create_widget("text_field", self.gui_backend.parent_id(values[0] if values else None), values[1] if len(values) > 1 else "")

        if name == "gui_sett_tekst":
            return self.gui_backend.set_text(int(values[0]), values[1] if len(values) > 1 else "")

        if name == "gui_hent_tekst":
            return self.gui_backend.get_text(int(values[0]))

        if name == "gui_vis":
            return self.gui_backend.show(int(values[0]))

        if name == "gui_lukk":
            return self.gui_backend.close(int(values[0]))

        for candidate in self._current_function_candidates(name):
            if candidate in self.functions:
                return self.call_user_function(candidate, values)

        raise RuntimeError(f"Ukjent funksjon: {name}")

    def eval_module_call(self, module_name: str, func_name: str, args: list[Any]):
        values = [self.eval(arg) for arg in args]

        if module_name == "math":
            if func_name == "pluss":
                return values[0] + values[1]
            if func_name == "minus":
                return values[0] - values[1]

        real_module = self.alias_map.get(module_name, module_name)

        for candidate in (
            f"{module_name}.{func_name}",
            f"{real_module}.{func_name}",
            f"std.{module_name}.{func_name}",
            f"std.{real_module}.{func_name}",
        ):
            if candidate in self.functions:
                return self.call_user_function(candidate, values)

        raise RuntimeError(f"Ukjent modulfunksjon: {module_name}.{func_name}")

    def call_user_function(self, name: str, args: list[Any]):
        fn = self.functions[name].node
        self.function_stack.append(name)
        self.push_scope()
        try:
            for param, value in zip(fn.params, args):
                self.define_var(param.name, value)

            try:
                self.eval(fn.body)
            except ReturnSignal as signal:
                return signal.value
            return None
        finally:
            self.pop_scope()
            self.function_stack.pop()
