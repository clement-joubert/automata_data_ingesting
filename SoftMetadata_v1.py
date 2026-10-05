#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SoftMetadata - ALTAG3D Metadata Generator (mdacst3D)
=============================================================

Graphical interface allowing an operator to enter the metadata
of an acquisition/analysis batch of archaeological objects and generate
the "mdacst3D" XML file used as a common reference by the different
measurement and visualization devices.

This version integrates GeoNames lookup for all location fields.
"""

import json
import os
import re
import copy
import uuid
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# --------------------------------------------------------------------------
# General Constants
# --------------------------------------------------------------------------

APP_TITLE = "SoftMetadata - AUTOMATA / ALTAG3D"
APP_VERSION = "1.1"

NS = "https://altag3d.huma-num.fr/data"
XSI_NS = "https://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = f"{NS} https://altag3d.huma-num.fr/data/mdacst3d.xsd"

MAX_SAMPLES = 60
MAX_CREATORS = 5
MAX_LIST_ITEMS = 5

ACTOR_TYPES = ["person", "organization"]
ACTOR_TYPE_LABELS = {"person": "Person", "organization": "Organization"}

PO_TYPE_OPTIONS = ["artefact", "ecofact", "sample", "structure", "other"]
OBJECT_NATURE_OPTIONS = ["acquisition", "processing", "documentation",
                          "publication", "other"]
YES_NO_OPTIONS = ["yes", "no"]

DESC_MAXLEN = 150

# --------------------------------------------------------------------------
# GeoNames configuration
# --------------------------------------------------------------------------
# 1. Create a free account at https://www.geonames.org/login
# 2. Enable it for API usage (link on your account page:
#    "Click here to enable your account for free web services")
# 3. Put your username below.
GEONAMES_USER = "VOTRE_USERNAME_GEONAMES"
GEONAMES_TIMEOUT = 10  # seconds


# --------------------------------------------------------------------------
# GeoNames API helpers
# --------------------------------------------------------------------------

def geonames_search(query, max_rows=20):
    """Search GeoNames by name prefix. Returns a list of result dicts."""
    if GEONAMES_USER in ("", "VOTRE_USERNAME_GEONAMES"):
        raise RuntimeError("Configurez GEONAMES_USER en haut du fichier "
                           "(compte gratuit sur geonames.org, à activer "
                           "pour l'API).")
    params = urllib.parse.urlencode({
        "name_startsWith": query,
        "maxRows": max_rows,
        "username": GEONAMES_USER,
        "orderby": "relevance",
    })
    url = f"http://api.geonames.org/searchJSON?{params}"
    try:
        with urllib.request.urlopen(url, timeout=GEONAMES_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"GeoNames indisponible (réseau) : {exc}")
    if "geonames" not in data:
        msg = data.get("status", {}).get("message", "réponse invalide")
        raise RuntimeError(f"Erreur GeoNames : {msg}")
    return data["geonames"]


def geonames_details(geoname_id):
    """Fetch full details (incl. alternate names) for a given geonameId."""
    if GEONAMES_USER in ("", "VOTRE_USERNAME_GEONAMES"):
        raise RuntimeError("Configurez GEONAMES_USER en haut du fichier.")
    params = urllib.parse.urlencode({
        "geonameId": geoname_id,
        "username": GEONAMES_USER,
    })
    url = f"http://api.geonames.org/getJSON?{params}"
    try:
        with urllib.request.urlopen(url, timeout=GEONAMES_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"GeoNames indisponible (réseau) : {exc}")
    if "geonameId" not in data:
        msg = data.get("status", {}).get("message", "réponse invalide")
        raise RuntimeError(f"Erreur GeoNames : {msg}")
    return data


def geonames_localized_names(geoname_id):
    """Return (french, english) localized names for a geonameId, or None."""
    try:
        details = geonames_details(geoname_id)
    except RuntimeError:
        return None
    fr = en = None
    for alt in details.get("alternateNames", []):
        lang = alt.get("lang")
        if lang == "fr" and fr is None:
            fr = alt.get("name", "")
        elif lang == "en" and en is None:
            en = alt.get("name", "")
    return fr, en


# --------------------------------------------------------------------------
# XML Helpers
# --------------------------------------------------------------------------

def new_id():
    return f"_{uuid.uuid4()}"

def qn(tag):
    return f"{{{NS}}}{tag}"

def sub(parent, tag, text=None, with_id=False):
    attrs = {"id": new_id()} if with_id else {}
    el = ET.SubElement(parent, qn(tag), attrs)
    if text is not None:
        el.text = str(text)
    return el

def local_name(tag):
    return tag.split("}")[-1] if "}" in tag else tag

def find_ln(parent, name):
    if parent is None:
        return None
    for child in parent:
        if local_name(child.tag) == name:
            return child
    return None

def findall_ln(parent, name):
    if parent is None:
        return []
    return [c for c in parent if local_name(c.tag) == name]

def text_of(el, default=""):
    if el is None or el.text is None:
        return default
    return el.text.strip()

def is_valid_date(s):
    s = (s or "").strip()
    if not s:
        return True
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Graphic Style
# --------------------------------------------------------------------------

COLOR_BG = "#F4F6F9"
COLOR_PANEL = "#FFFFFF"
COLOR_PRIMARY = "#0B5394"
COLOR_PRIMARY_DARK = "#073763"
COLOR_ACCENT = "#2E7D32"
COLOR_ACCENT_DARK = "#1B5E20"
COLOR_DANGER = "#B00020"
COLOR_DANGER_DARK = "#7F0016"
COLOR_WARN = "#E65100"
COLOR_TEXT = "#1C2530"
COLOR_MUTED = "#6B7785"
COLOR_BORDER = "#D6DCE3"


def apply_style(root):
    root.configure(bg=COLOR_BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT,
                     font=("Segoe UI", 10))
    style.configure("TFrame", background=COLOR_BG)
    style.configure("Panel.TFrame", background=COLOR_PANEL)
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("Panel.TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT)
    style.configure("Hint.TLabel", background=COLOR_BG, foreground=COLOR_MUTED,
                     font=("Segoe UI", 8, "italic"))
    style.configure("Hint.Panel.TLabel", background=COLOR_PANEL, foreground=COLOR_MUTED,
                     font=("Segoe UI", 8, "italic"))
    style.configure("Required.TLabel", background=COLOR_BG, foreground=COLOR_DANGER,
                     font=("Segoe UI", 9, "bold"))
    style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_PRIMARY_DARK,
                     font=("Segoe UI", 15, "bold"))
    style.configure("Subtitle.TLabel", background=COLOR_BG, foreground=COLOR_MUTED,
                     font=("Segoe UI", 9))
    style.configure("Counter.TLabel", background=COLOR_BG, foreground=COLOR_PRIMARY,
                     font=("Segoe UI", 10, "bold"))

    style.configure("Section.TLabelframe", background=COLOR_PANEL,
                     bordercolor=COLOR_BORDER, relief="solid", borderwidth=1)
    style.configure("Section.TLabelframe.Label", background=COLOR_PANEL,
                     foreground=COLOR_PRIMARY_DARK, font=("Segoe UI", 11, "bold"))
    style.configure("Sub.TLabelframe", background=COLOR_PANEL,
                     bordercolor=COLOR_BORDER, relief="solid", borderwidth=1)
    style.configure("Sub.TLabelframe.Label", background=COLOR_PANEL,
                     foreground=COLOR_WARN, font=("Segoe UI", 9, "bold"))

    style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"))
    style.map("TNotebook.Tab",
              background=[("selected", COLOR_PANEL), ("!selected", COLOR_BG)],
              foreground=[("selected", COLOR_PRIMARY_DARK), ("!selected", COLOR_MUTED)])

    style.configure("TEntry", fieldbackground="white", padding=4)
    style.configure("TCombobox", fieldbackground="white", padding=4)

    style.configure("Primary.TButton", background=COLOR_PRIMARY, foreground="white",
                     font=("Segoe UI", 10, "bold"), padding=(12, 6))
    style.map("Primary.TButton", background=[("active", COLOR_PRIMARY_DARK)])

    style.configure("Accent.TButton", background=COLOR_ACCENT, foreground="white",
                     font=("Segoe UI", 10, "bold"), padding=(12, 6))
    style.map("Accent.TButton", background=[("active", COLOR_ACCENT_DARK)])

    style.configure("Danger.TButton", background=COLOR_DANGER, foreground="white",
                     font=("Segoe UI", 10, "bold"), padding=(12, 6))
    style.map("Danger.TButton", background=[("active", COLOR_DANGER_DARK)])

    style.configure("Flat.TButton", background=COLOR_PANEL, foreground=COLOR_PRIMARY_DARK,
                     font=("Segoe UI", 9, "bold"), padding=(8, 4))
    style.map("Flat.TButton", background=[("active", "#E8ECF1")])

    style.configure("Small.TButton", font=("Segoe UI", 8, "bold"), padding=(4, 2))

    style.configure("Treeview", background="white", fieldbackground="white",
                     rowheight=26, font=("Segoe UI", 9))
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),
                     background="#E8ECF1", foreground=COLOR_PRIMARY_DARK)
    style.map("Treeview", background=[("selected", COLOR_PRIMARY)],
              foreground=[("selected", "white")])

    return style


# --------------------------------------------------------------------------
# Reusable Widgets
# --------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *a, **kw):
        super().__init__(parent, *a, **kw)
        self.canvas = tk.Canvas(self, bg=COLOR_BG, highlightthickness=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        for widget in (self.canvas, self.inner):
            widget.bind("<Enter>", lambda e: self._bind_wheel())
            widget.bind("<Leave>", lambda e: self._unbind_wheel())

    def _resize_inner(self, event):
        self.canvas.itemconfig(self._win, width=event.width)

    def _bind_wheel(self):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", self._on_wheel)
        self.canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(3, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)) * 3, "units")

def section(parent, title):
    f = ttk.LabelFrame(parent, text=title, style="Section.TLabelframe")
    f.pack(fill="x", padx=12, pady=8)
    return f

def field_label(parent, text, required=False):
    lbl = ttk.Label(parent, text=(text + (" *" if required else "")),
                     style="Required.TLabel" if required else
                     ("Panel.TLabel" if _is_panel(parent) else "TLabel"))
    lbl.pack(anchor="w", padx=8, pady=(8, 0))
    return lbl

def _is_panel(widget):
    try:
        return str(widget.cget("style")).startswith("Section") or \
               str(widget.cget("style")).startswith("Sub")
    except tk.TclError:
        return False

def add_entry(parent, label, default="", width=50, hint=None, required=False):
    field_label(parent, label, required=required)
    e = ttk.Entry(parent, width=width)
    if default:
        e.insert(0, default)
    e.pack(anchor="w", fill="x", padx=8)
    if hint:
        ttk.Label(parent, text=hint, style="Hint.Panel.TLabel").pack(anchor="w", padx=8)
    return e

def add_text(parent, label, default="", height=2, hint=None, maxlen=None):
    field_label(parent, label)
    holder = tk.Frame(parent, bg=COLOR_BORDER, bd=0)
    holder.pack(anchor="w", fill="x", padx=8, pady=(0, 2))
    t = tk.Text(holder, height=height, wrap="word", font=("Segoe UI", 10),
                relief="flat", padx=6, pady=4, highlightthickness=0)
    t.pack(fill="both", expand=True, padx=1, pady=1)
    if default:
        t.insert("1.0", default)
    if hint:
        ttk.Label(parent, text=hint, style="Hint.Panel.TLabel").pack(anchor="w", padx=8)
    if maxlen:
        counter = ttk.Label(parent, text=f"0/{maxlen}", style="Hint.Panel.TLabel")
        counter.pack(anchor="e", padx=8)
        def update_counter(event=None):
            n = len(t.get("1.0", "end-1c"))
            counter.config(text=f"{n}/{maxlen}",
                            foreground=(COLOR_DANGER if n > maxlen else COLOR_MUTED))
        t.bind("<KeyRelease>", update_counter)
        update_counter()
    return t

def add_combo(parent, label, values, default=None, width=25, editable=True, hint=None):
    field_label(parent, label)
    cb = ttk.Combobox(parent, values=values, width=width,
                       state="normal" if editable else "readonly")
    if default is not None:
        cb.set(default)
    cb.pack(anchor="w", padx=8)
    if hint:
        ttk.Label(parent, text=hint, style="Hint.Panel.TLabel").pack(anchor="w", padx=8)
    return cb

def text_value(widget, maxlen=None):
    val = widget.get("1.0", "end-1c").strip()
    if maxlen:
        val = val[:maxlen]
    return val

def set_text_value(widget, value):
    widget.delete("1.0", tk.END)
    if value:
        widget.insert("1.0", value)


# --------------------------------------------------------------------------
# Actor Block
# --------------------------------------------------------------------------

class ActorBlock:
    def __init__(self, parent, title="Actor", removable_cmd=None):
        self.frame = ttk.LabelFrame(parent, text=title, style="Sub.TLabelframe")
        self.frame.pack(fill="x", padx=6, pady=4)

        top = tk.Frame(self.frame, bg=COLOR_PANEL)
        top.pack(fill="x", padx=6, pady=(6, 2))

        if removable_cmd:
            ttk.Button(top, text="✕ Remove", style="Small.TButton",
                       command=removable_cmd).pack(side="right")

        row1 = tk.Frame(self.frame, bg=COLOR_PANEL)
        row1.pack(fill="x", padx=6, pady=2)
        tk.Label(row1, text="Type:", bg=COLOR_PANEL).grid(row=0, column=0, sticky="w")
        self.type_cb = ttk.Combobox(row1, values=ACTOR_TYPES, width=13, state="readonly")
        self.type_cb.set("person")
        self.type_cb.grid(row=0, column=1, padx=(4, 16))
        tk.Label(row1, text="Name / Title:", bg=COLOR_PANEL).grid(row=0, column=2, sticky="w")
        self.literal_e = ttk.Entry(row1, width=30)
        self.literal_e.grid(row=0, column=3, padx=4, sticky="we")
        row1.columnconfigure(3, weight=1)

        row2 = tk.Frame(self.frame, bg=COLOR_PANEL)
        row2.pack(fill="x", padx=6, pady=(2, 6))
        tk.Label(row2, text="Identifier (ORCID / ROR / URI):", bg=COLOR_PANEL).pack(side="left")
        self.uri_e = ttk.Entry(row2, width=45)
        self.uri_e.pack(side="left", padx=4, fill="x", expand=True)

    def get(self):
        code = self.type_cb.get().strip() or "person"
        label = ACTOR_TYPE_LABELS.get(code, code.capitalize())
        return {"type_code": code, "type_label": label,
                "literal": self.literal_e.get().strip(),
                "uri": self.uri_e.get().strip()}

    def set(self, d):
        d = d or {}
        self.type_cb.set(d.get("type_code", "person"))
        self.literal_e.delete(0, tk.END)
        self.literal_e.insert(0, d.get("literal", ""))
        self.uri_e.delete(0, tk.END)
        self.uri_e.insert(0, d.get("uri", ""))

    def is_empty(self):
        v = self.get()
        return not v["literal"] and not v["uri"]

    def destroy(self):
        self.frame.destroy()


# --------------------------------------------------------------------------
# Date Block
# --------------------------------------------------------------------------

class DateBlock:
    def __init__(self, parent, title="Date"):
        self.frame = ttk.LabelFrame(parent, text=title, style="Sub.TLabelframe")
        self.frame.pack(fill="x", padx=6, pady=4)

        row1 = tk.Frame(self.frame, bg=COLOR_PANEL)
        row1.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(row1, text="Date (YYYY-MM-DD):", bg=COLOR_PANEL).pack(side="left")
        self.min_e = ttk.Entry(row1, width=12)
        self.min_e.pack(side="left", padx=(4, 16))
        tk.Label(row1, text="Literal dating:", bg=COLOR_PANEL).pack(side="left")
        self.lit_e = ttk.Entry(row1, width=18)
        self.lit_e.pack(side="left", padx=4)

        row2 = tk.Frame(self.frame, bg=COLOR_PANEL)
        row2.pack(fill="x", padx=6, pady=(2, 6))
        tk.Label(row2, text="PeriodO (period 1):", bg=COLOR_PANEL).pack(side="left")
        self.periodo1_e = ttk.Entry(row2, width=22)
        self.periodo1_e.pack(side="left", padx=(4, 16))
        tk.Label(row2, text="PeriodO (period 2):", bg=COLOR_PANEL).pack(side="left")
        self.periodo2_e = ttk.Entry(row2, width=22)
        self.periodo2_e.pack(side="left", padx=4)

    def get(self):
        return {"min": self.min_e.get().strip(),
                "periodo1": self.periodo1_e.get().strip(),
                "periodo2": self.periodo2_e.get().strip(),
                "litteral": self.lit_e.get().strip()}

    def set(self, d):
        d = d or {}
        for e, key in ((self.min_e, "min"), (self.periodo1_e, "periodo1"),
                       (self.periodo2_e, "periodo2"), (self.lit_e, "litteral")):
            e.delete(0, tk.END)
            e.insert(0, d.get(key, ""))

    def validate(self):
        return is_valid_date(self.min_e.get())


# --------------------------------------------------------------------------
# GeoNames Picker Dialog
# --------------------------------------------------------------------------

class GeoNamesPicker(tk.Toplevel):
    """Search dialog against the GeoNames web service.

    Calls `callback(result_dict)` with the full GeoNames result
    (name, geonameId, lat, lng, countryName, ...) when the user
    double-clicks a row or clicks "Use selection".
    """
    def __init__(self, master, callback, initial_query=""):
        super().__init__(master)
        self.callback = callback
        self.title("GeoNames - Recherche de lieu")
        self.geometry("720x460")
        self.configure(bg=COLOR_BG)
        self.transient(master)
        self.grab_set()

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="Nom du lieu :", style="TLabel").pack(side="left")
        self.entry = ttk.Entry(top, width=42)
        self.entry.pack(side="left", padx=(6, 8))
        if initial_query:
            self.entry.insert(0, initial_query)
        self.entry.bind("<Return>", lambda e: self._search())
        ttk.Button(top, text="Rechercher", style="Primary.TButton",
                   command=self._search).pack(side="left")
        self.status = ttk.Label(self, text="Tapez un nom puis appuyez sur Entrée",
                                 style="Subtitle.TLabel")
        self.status.pack(anchor="w", padx=12)

        columns = ("name", "admin", "country", "id", "ll")
        headings = {"name": "Nom", "admin": "Région / Admin", "country": "Pays",
                    "id": "Geonames ID", "ll": "Long, Lat"}
        widths = {"name": 210, "admin": 170, "country": 120, "id": 90, "ll": 110}
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                  selectmode="browse")
        for c in columns:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._choose())

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=10, pady=8)
        ttk.Button(footer, text="Fermer", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Utiliser la sélection", style="Accent.TButton",
                   command=self._choose).pack(side="right", padx=6)

        self.results = []
        self.entry.focus_set()

    def _search(self):
        query = self.entry.get().strip()
        if not query:
            messagebox.showinfo("GeoNames", "Tapez d'abord un nom de lieu à rechercher.",
                                parent=self)
            return
        self.status.config(text="Recherche en cours...")
        self.update_idletasks()
        try:
            self.results = geonames_search(query)
        except RuntimeError as exc:
            self.status.config(text=str(exc))
            messagebox.showerror("GeoNames - Erreur", str(exc), parent=self)
            return
        self.tree.delete(*self.tree.get_children())
        for g in self.results:
            admin = ", ".join(x for x in (g.get("adminName1"),
                                           g.get("adminName2")) if x)
            self.tree.insert("", "end", values=(
                g.get("name", ""), admin, g.get("countryName", ""),
                g.get("geonameId", ""),
                f'{g.get("lng", "")}, {g.get("lat", "")}'))
        self.status.config(text=f"{len(self.results)} résultat(s) — "
                                "double-cliquez une ligne pour choisir.")

    def _choose(self):
        sel = self.tree.selection()
        if not sel or not self.results:
            return
        g = self.results[self.tree.index(sel[0])]
        self.callback(g)
        self.destroy()


# --------------------------------------------------------------------------
# Location Block (with GeoNames lookup)
# --------------------------------------------------------------------------

class LocationBlock:
    def __init__(self, parent, title="Location"):
        self.frame = ttk.LabelFrame(parent, text=title, style="Sub.TLabelframe")
        self.frame.pack(fill="x", padx=6, pady=4)

        row1 = tk.Frame(self.frame, bg=COLOR_PANEL)
        row1.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(row1, text="Location name:", bg=COLOR_PANEL).pack(side="left")
        self.name_e = ttk.Entry(row1, width=26)
        self.name_e.pack(side="left", padx=4, fill="x", expand=True)
        # GeoNames lookup button: fills every location field from GeoNames
        ttk.Button(row1, text="🔍 GeoNames", style="Flat.TButton",
                   command=self._pick_from_geonames).pack(side="left", padx=4)

        row2 = tk.Frame(self.frame, bg=COLOR_PANEL)
        row2.pack(fill="x", padx=6, pady=2)
        tk.Label(row2, text="Geonames ID:", bg=COLOR_PANEL).pack(side="left")
        self.geonames_e = ttk.Entry(row2, width=12)
        self.geonames_e.pack(side="left", padx=(4, 16))
        tk.Label(row2, text="Longitude, Latitude:", bg=COLOR_PANEL).pack(side="left")
        self.longlat_e = ttk.Entry(row2, width=20)
        self.longlat_e.pack(side="left", padx=4)

        row3 = tk.Frame(self.frame, bg=COLOR_PANEL)
        row3.pack(fill="x", padx=6, pady=(2, 6))
        tk.Label(row3, text="Name (FR):", bg=COLOR_PANEL).pack(side="left")
        self.fr_e = ttk.Entry(row3, width=18)
        self.fr_e.pack(side="left", padx=(4, 16))
        tk.Label(row3, text="Name (EN):", bg=COLOR_PANEL).pack(side="left")
        self.en_e = ttk.Entry(row3, width=18)
        self.en_e.pack(side="left", padx=4)

    def _pick_from_geonames(self):
        def apply(g):
            self.name_e.delete(0, tk.END)
            self.name_e.insert(0, g.get("name", ""))
            self.geonames_e.delete(0, tk.END)
            self.geonames_e.insert(0, str(g.get("geonameId", "")))
            self.longlat_e.delete(0, tk.END)
            self.longlat_e.insert(0, f'{g.get("lng", "")}, {g.get("lat", "")}')
            # Try to fill localized FR/EN names from the GeoNames details API.
            names = geonames_localized_names(g.get("geonameId"))
            if names:
                fr, en = names
                if fr:
                    self.fr_e.delete(0, tk.END)
                    self.fr_e.insert(0, fr)
                if en:
                    self.en_e.delete(0, tk.END)
                    self.en_e.insert(0, en)
        GeoNamesPicker(self.frame, apply,
                       initial_query=self.name_e.get().strip())

    def get(self):
        return {"name": self.name_e.get().strip(),
                "geonames": self.geonames_e.get().strip(),
                "longlat": self.longlat_e.get().strip(),
                "french": self.fr_e.get().strip(),
                "english": self.en_e.get().strip()}

    def set(self, d):
        d = d or {}
        for e, key in ((self.name_e, "name"), (self.geonames_e, "geonames"),
                       (self.longlat_e, "longlat"), (self.fr_e, "french"),
                       (self.en_e, "english")):
            e.delete(0, tk.END)
            e.insert(0, d.get(key, ""))


# --------------------------------------------------------------------------
# Event Block (actor + date + location)
# --------------------------------------------------------------------------

class EventBlock:
    def __init__(self, parent, title):
        outer = section(parent, title)
        self.actor = ActorBlock(outer, "Actor")
        self.date = DateBlock(outer, "Date")
        self.location = LocationBlock(outer, "Location")

    def get(self):
        return {"actor": self.actor.get(), "date": self.date.get(),
                "location": self.location.get()}

    def set(self, d):
        d = d or {}
        self.actor.set(d.get("actor"))
        self.date.set(d.get("date"))
        self.location.set(d.get("location"))

    def validate(self):
        return self.date.validate()


# --------------------------------------------------------------------------
# Dynamic List Field (po_reference, po_subject...)
# --------------------------------------------------------------------------

class ListField:
    def __init__(self, parent, label, max_items=MAX_LIST_ITEMS, width=60,
                 add_label="+ Add"):
        field_label(parent, label)
        self.container = ttk.Frame(parent, style="Panel.TFrame")
        self.container.pack(fill="x", padx=8)
        self.rows = []
        self.max_items = max_items
        self.width = width
        self.add_btn = ttk.Button(parent, text=add_label, style="Flat.TButton",
                                   command=self.add_row)
        self.add_btn.pack(anchor="w", padx=8, pady=(2, 8))
        self.add_row()

    def add_row(self, value=""):
        if len(self.rows) >= self.max_items:
            return
        row = ttk.Frame(self.container, style="Panel.TFrame")
        row.pack(fill="x", pady=1)
        e = ttk.Entry(row, width=self.width)
        e.pack(side="left", fill="x", expand=True)
        if value:
            e.insert(0, value)
        btn = ttk.Button(row, text="✕", width=3, style="Small.TButton",
                          command=lambda: self.remove_row(row, e))
        btn.pack(side="left", padx=2)
        self.rows.append((row, e))

    def remove_row(self, row, e):
        row.destroy()
        self.rows = [(r, en) for (r, en) in self.rows if en is not e]
        if not self.rows:
            self.add_row()

    def get(self):
        return [e.get().strip() for (_, e) in self.rows if e.get().strip()]

    def set(self, values):
        for r, _ in self.rows:
            r.destroy()
        self.rows = []
        values = values or []
        if not values:
            self.add_row()
        else:
            for v in values:
                self.add_row(v)


# --------------------------------------------------------------------------
# Multi Actor Field (Deposit Creators)
# --------------------------------------------------------------------------

class MultiActorField:
    def __init__(self, parent, title, max_items=MAX_CREATORS):
        self.parent = parent
        self.max_items = max_items
        self.container = ttk.Frame(parent, style="Panel.TFrame")
        self.container.pack(fill="x", padx=2)
        self.blocks = []
        self.add_btn = ttk.Button(parent, text=f"+ Add ({title.lower()})",
                                   style="Flat.TButton", command=self.add_row)
        self.add_btn.pack(anchor="w", padx=8, pady=(2, 8))
        self.title = title
        self.add_row()

    def add_row(self, data=None):
        if len(self.blocks) >= self.max_items:
            return
        idx = len(self.blocks)
        block = ActorBlock(self.container, f"{self.title} #{idx + 1}",
                            removable_cmd=lambda: self.remove_row(block))
        if data:
            block.set(data)
        self.blocks.append(block)

    def remove_row(self, block):
        block.destroy()
        self.blocks = [b for b in self.blocks if b is not block]
        if not self.blocks:
            self.add_row()
        self._renumber()

    def _renumber(self):
        for i, b in enumerate(self.blocks):
            b.frame.config(text=f"{self.title} #{i + 1}")

    def get(self):
        return [b.get() for b in self.blocks if not b.is_empty()]

    def set(self, values):
        for b in self.blocks:
            b.destroy()
        self.blocks = []
        values = values or []
        if not values:
            self.add_row()
        else:
            for v in values:
                self.add_row(v)


# --------------------------------------------------------------------------
# Default Data Models
# --------------------------------------------------------------------------

def empty_actor():
    return {"type_code": "person", "type_label": "Person", "literal": "", "uri": ""}

def empty_date():
    return {"min": "", "periodo1": "", "periodo2": "", "litteral": ""}

def empty_location():
    return {"name": "", "geonames": "", "longlat": "", "french": "", "english": ""}

def empty_event():
    return {"actor": empty_actor(), "date": empty_date(), "location": empty_location()}

def empty_sample():
    return {
        "do": {
            "name": "", "nature_code": "acquisition", "nature_label": "Acquisition",
            "licence": "", "creator": empty_actor(), "contributor": empty_actor(),
            "principal": "yes", "description": "", "thumbnail": "",
            "collection": "", "construitID": "",
        },
        "po": {
            "name": "", "type_code": "artefact", "type_label": "Artefact",
            "materials": "", "description": "",
            "references": [], "subjects": [],
            "creation": empty_event(), "discovery": empty_event(),
            "conservation": empty_event(),
            "inventory": {"name": "", "id": "", "uri": ""},
        },
        "_raw_sourceGroup": None,
        "_raw_computedInterpretedData": None,
    }

def empty_deposit():
    return {
        "title": "", "description": "",
        "project": {
            "name": "AUTOMATA", "context": "", "objectives": "", "fundings": "",
            "date": {"min": "", "max": "", "litteral": ""},
        },
        "management": {
            "rights": "CC BY SA", "version": "1", "compatibility": "10",
            "depositor": {"type_code": "organization", "type_label": "Organization",
                          "literal": "", "uri": ""},
            "responsible": {"type_code": "organization", "type_label": "Organization",
                             "literal": "", "uri": ""},
        },
        "scientific_director": empty_actor(),
        "creators": [],
        "structure": {"nb_files": "", "size": "", "content": ""},
    }


# --------------------------------------------------------------------------
# Sample Edit Dialog (Physical Object + Events)
# --------------------------------------------------------------------------

class SampleDialog(tk.Toplevel):
    def __init__(self, master, on_save, deposit_info, sample=None, template=None, index=None, total=MAX_SAMPLES):
        super().__init__(master)
        self.on_save = on_save
        self.deposit_info = deposit_info
        self.result = None
        self.raw_sourceGroup = None
        self.raw_computedInterpretedData = None

        title_suffix = f" ({index}/{total})" if index else ""
        self.title(f"Sample{title_suffix}")
        self.geometry("880x720")
        self.configure(bg=COLOR_BG)
        self.transient(master)
        self.grab_set()

        data = sample if sample is not None else (template if template else empty_sample())
        if sample is not None:
            self.raw_sourceGroup = sample.get("_raw_sourceGroup")
            self.raw_computedInterpretedData = sample.get("_raw_computedInterpretedData")

        header = ttk.Frame(self)
        header.pack(fill="x", padx=14, pady=(12, 0))
        ttk.Label(header, text=f"Sample details{title_suffix}", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Fields marked with * are required to identify the object.",
                   style="Subtitle.TLabel").pack(anchor="w")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_po = ScrollableFrame(self.notebook)
        self.tab_events = ScrollableFrame(self.notebook)

        self.notebook.add(self.tab_po, text="Physical Object")
        self.notebook.add(self.tab_events, text="Events")

        self._build_physical_tab(self.tab_po.inner, data["po"])
        self._build_events_tab(self.tab_events.inner, data["po"])

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(footer, text="Save Sample", style="Accent.TButton",
                   command=self._save).pack(side="right", padx=4)
        if sample is not None:
            ttk.Label(footer, text="Editing an existing sample",
                       style="Subtitle.TLabel").pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # -- Physical Object + Inventory Tab ---------------------------------------
    def _build_physical_tab(self, parent, po):
        f = section(parent, "Physical Object Identity")
        self.po_name_e = add_entry(f, "Sample name / code", po["name"],
                                    required=True,
                                    hint="Short object identifier (e.g., R37_1)")
        self.po_type_cb = add_combo(f, "Type", PO_TYPE_OPTIONS, po["type_code"])
        self.po_mat_e = add_entry(f, "Material(s)", po["materials"])
        self.po_desc_t = add_text(f, "Description", po["description"], height=3,
                                   maxlen=DESC_MAXLEN)

        f2 = section(parent, "References and Keywords")
        self.po_refs = ListField(f2, "References (bibliography, DOI, ARK...)",
                                  add_label="+ Add a reference")
        self.po_refs.set(po["references"])
        self.po_subjects = ListField(f2, "Subjects / Keywords", add_label="+ Add a subject")
        self.po_subjects.set(po["subjects"])

        # Included Inventory
        inv = po["inventory"]
        f3 = section(parent, "Inventory")
        self.inv_name_e = add_entry(f3, "Inventory name", inv["name"])
        self.inv_id_e = add_entry(f3, "Inventory number", inv["id"])
        self.inv_uri_e = add_entry(f3, "Inventory URI", inv["uri"])

    # -- Events Tab (Discovery & Conservation) --------------------------------
    def _build_events_tab(self, parent, po):
        self.discovery = EventBlock(parent, "Discovery of the object")
        self.discovery.set(po["discovery"])

        self.conservation = EventBlock(parent, "Conservation of the object")
        self.conservation.set(po["conservation"])

    # -- Validation and Saving -------------------------------------------------
    def _save(self):
        po_name = self.po_name_e.get().strip()
        if not po_name:
            messagebox.showerror("Required field",
                                  "The sample name / code (Physical Object) is mandatory.")
            self.notebook.select(self.tab_po)
            return

        for block, tab in ((self.discovery, self.tab_events), (self.conservation, self.tab_events)):
            if not block.validate():
                messagebox.showerror("Invalid date",
                                     "The expected date format is YYYY-MM-DD (e.g., 2024-09-01).")
                self.notebook.select(tab)
                return

        # Auto-filling Digital Object
        po_type_code = self.po_type_cb.get().strip() or "artefact"
        d_title = self.deposit_info.get("title", "").strip()

        separator = "_" if d_title and not d_title.endswith("_") else ""
        do_name = f"{d_title}{separator}{po_name}"

        do_creators = self.deposit_info.get("creators", [])
        do_creator = do_creators[0] if do_creators else empty_actor()

        sample = {
            "do": {
                "name": do_name,
                "nature_code": "acquisition",
                "nature_label": "Acquisition",
                "licence": self.deposit_info.get("rights", "CC BY SA"),
                "creator": do_creator,
                "contributor": empty_actor(),
                "principal": "yes",
                "description": "",
                "thumbnail": "",
                "collection": self.deposit_info.get("project_name", ""),
                "construitID": "",
            },
            "po": {
                "name": po_name,
                "type_code": po_type_code,
                "type_label": po_type_code.capitalize(),
                "materials": self.po_mat_e.get().strip(),
                "description": text_value(self.po_desc_t, DESC_MAXLEN),
                "references": self.po_refs.get(),
                "subjects": self.po_subjects.get(),
                "creation": empty_event(),  # Empty by default
                "discovery": self.discovery.get(),
                "conservation": self.conservation.get(),
                "inventory": {
                    "name": self.inv_name_e.get().strip(),
                    "id": self.inv_id_e.get().strip(),
                    "uri": self.inv_uri_e.get().strip(),
                },
            },
            "_raw_sourceGroup": self.raw_sourceGroup,
            "_raw_computedInterpretedData": self.raw_computedInterpretedData,
        }
        self.result = sample
        self.on_save(sample)
        self.destroy()


# --------------------------------------------------------------------------
# Main Application
# --------------------------------------------------------------------------

class BatchMetadataApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x820")
        self.root.minsize(980, 640)
        apply_style(self.root)

        self.deposit = empty_deposit()
        self.samples = []
        self.current_file_path = None
        self.session_path = None
        self.default_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(self.default_dir):
            self.default_dir = os.path.expanduser("~")

        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

        self._refresh_status()

    # ---------------------------------------------------------------- UI ----
    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=COLOR_PRIMARY_DARK, height=54)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        title_box = tk.Frame(bar, bg=COLOR_PRIMARY_DARK)
        title_box.pack(side="left", padx=16)
        tk.Label(title_box, text="SoftMetadata", bg=COLOR_PRIMARY_DARK, fg="white",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(6, 0))
        tk.Label(title_box, text="ALTAG3D / AUTOMATA Metadata", bg=COLOR_PRIMARY_DARK,
                 fg="#B9D4EE", font=("Segoe UI", 8)).pack(anchor="w")

        btns = tk.Frame(bar, bg=COLOR_PRIMARY_DARK)
        btns.pack(side="right", padx=12, pady=8)

        def toolbtn(text, cmd):
            b = tk.Button(btns, text=text, command=cmd, bg="#0D63AD", fg="white",
                          activebackground="#0A4E87", activeforeground="white",
                          relief="flat", padx=10, pady=6, font=("Segoe UI", 9, "bold"),
                          bd=0, cursor="hand2")
            b.pack(side="left", padx=3)
            return b

        toolbtn("New batch", self.new_batch)
        toolbtn("Load XML", self.load_xml)
        toolbtn("Session: Load", self.load_session)
        toolbtn("Session: Save", self.save_session)
        toolbtn("Export XML", self.export_xml)

    def _build_body(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        self.tab_deposit = ScrollableFrame(self.notebook)
        self.tab_samples = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_deposit, text="1. Deposit Information")
        self.notebook.add(self.tab_samples, text="2. Physical Objects (Samples)")

        self._build_deposit_tab(self.tab_deposit.inner)
        self._build_samples_tab(self.tab_samples)

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg="#E8ECF1", height=28)
        bar.pack(fill="x", side="bottom")
        self.status_lbl = tk.Label(bar, text="", bg="#E8ECF1", fg=COLOR_MUTED,
                                    font=("Segoe UI", 8), anchor="w")
        self.status_lbl.pack(side="left", padx=10)

    def _refresh_status(self):
        path = self.current_file_path or "(unsaved)"
        self.status_lbl.config(
            text=f"Target XML file: {path}    |    "
                 f"Samples: {len(self.samples)}/{MAX_SAMPLES}")

    # ---------------------------------------------------- Tab 1: Deposit ----
    def _build_deposit_tab(self, parent):
        d = self.deposit

        f1 = section(parent, "1. General Deposit Information")
        self.d_title_e = add_entry(f1, "Title (YYYYMMDD_BatchName)", d["title"],
                                    required=True,
                                    hint="This title is also used as the XML file name.")
        self.d_desc_t = add_text(f1, "Deposit Description", d["description"], height=3,
                                  maxlen=DESC_MAXLEN)

        f2 = section(parent, "2. Project")
        self.dp_name_e = add_entry(f2, "Project Name", d["project"]["name"])
        self.dp_context_e = add_entry(f2, "Project Context", d["project"]["context"])
        self.dp_objectives_e = add_entry(f2, "Scientific and Technical Objectives",
                                          d["project"]["objectives"])
        self.dp_fundings_e = add_entry(f2, "Fundings", d["project"]["fundings"])

        fd = ttk.LabelFrame(f2, text="Project Dates (YYYY-MM-DD)", style="Sub.TLabelframe")
        fd.pack(fill="x", padx=8, pady=(4, 10))
        row = tk.Frame(fd, bg=COLOR_PANEL)
        row.pack(fill="x", padx=6, pady=6)
        tk.Label(row, text="Min:", bg=COLOR_PANEL).grid(row=0, column=0)
        self.dp_min_e = ttk.Entry(row, width=12)
        self.dp_min_e.grid(row=0, column=1, padx=(4, 16))
        tk.Label(row, text="Max:", bg=COLOR_PANEL).grid(row=0, column=2)
        self.dp_max_e = ttk.Entry(row, width=12)
        self.dp_max_e.grid(row=0, column=3, padx=(4, 16))
        tk.Label(row, text="Literal:", bg=COLOR_PANEL).grid(row=0, column=4)
        self.dp_lit_e = ttk.Entry(row, width=12)
        self.dp_lit_e.grid(row=0, column=5, padx=4)
        self.dp_min_e.insert(0, d["project"]["date"]["min"])
        self.dp_max_e.insert(0, d["project"]["date"]["max"])
        self.dp_lit_e.insert(0, d["project"]["date"]["litteral"])

        f3 = section(parent, "3. Deposit Management")
        row3 = tk.Frame(f3, bg=COLOR_PANEL)
        row3.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(row3, text="Rights:", bg=COLOR_PANEL).grid(row=0, column=0)
        self.dm_rights_e = ttk.Entry(row3, width=14)
        self.dm_rights_e.insert(0, d["management"]["rights"])
        self.dm_rights_e.grid(row=0, column=1, padx=(4, 16))
        tk.Label(row3, text="Version:", bg=COLOR_PANEL).grid(row=0, column=2)
        self.dm_version_e = ttk.Entry(row3, width=6)
        self.dm_version_e.insert(0, d["management"]["version"])
        self.dm_version_e.grid(row=0, column=3, padx=(4, 16))
        tk.Label(row3, text="Compatibility:", bg=COLOR_PANEL).grid(row=0, column=4)
        self.dm_compat_e = ttk.Entry(row3, width=6)
        self.dm_compat_e.insert(0, d["management"]["compatibility"])
        self.dm_compat_e.grid(row=0, column=5, padx=4)

        self.dm_depositor = ActorBlock(f3, "Depositor Service")
        self.dm_depositor.set(d["management"]["depositor"])
        self.dm_responsible = ActorBlock(f3, "Responsible Entity")
        self.dm_responsible.set(d["management"]["responsible"])

        f4 = section(parent, "4. Deposit Actors")
        self.d_sd = ActorBlock(f4, "Scientific Director")
        self.d_sd.set(d["scientific_director"])

        ttk.Label(f4, text=f"Creators (up to {MAX_CREATORS})",
                   style="Panel.TLabel", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=8, pady=(6, 0))
        self.d_creators = MultiActorField(f4, "Creator", max_items=MAX_CREATORS)
        self.d_creators.set(d["creators"])

    def _collect_deposit(self):
        d = self.deposit
        d["title"] = self.d_title_e.get().strip()
        d["description"] = text_value(self.d_desc_t, DESC_MAXLEN)
        d["project"]["name"] = self.dp_name_e.get().strip()
        d["project"]["context"] = self.dp_context_e.get().strip()
        d["project"]["objectives"] = self.dp_objectives_e.get().strip()
        d["project"]["fundings"] = self.dp_fundings_e.get().strip()
        d["project"]["date"] = {"min": self.dp_min_e.get().strip(),
                                 "max": self.dp_max_e.get().strip(),
                                 "litteral": self.dp_lit_e.get().strip()}
        d["management"]["rights"] = self.dm_rights_e.get().strip()
        d["management"]["version"] = self.dm_version_e.get().strip()
        d["management"]["compatibility"] = self.dm_compat_e.get().strip()
        d["management"]["depositor"] = self.dm_depositor.get()
        d["management"]["responsible"] = self.dm_responsible.get()
        d["scientific_director"] = self.d_sd.get()
        d["creators"] = self.d_creators.get()
        return d

    def _apply_deposit_to_ui(self):
        d = self.deposit
        self.d_title_e.delete(0, tk.END)
        self.d_title_e.insert(0, d["title"])
        set_text_value(self.d_desc_t, d["description"])
        self.dp_name_e.delete(0, tk.END)
        self.dp_name_e.insert(0, d["project"]["name"])
        self.dp_context_e.delete(0, tk.END)
        self.dp_context_e.insert(0, d["project"]["context"])
        self.dp_objectives_e.delete(0, tk.END)
        self.dp_objectives_e.insert(0, d["project"]["objectives"])
        self.dp_fundings_e.delete(0, tk.END)
        self.dp_fundings_e.insert(0, d["project"]["fundings"])
        self.dp_min_e.delete(0, tk.END)
        self.dp_min_e.insert(0, d["project"]["date"]["min"])
        self.dp_max_e.delete(0, tk.END)
        self.dp_max_e.insert(0, d["project"]["date"]["max"])
        self.dp_lit_e.delete(0, tk.END)
        self.dp_lit_e.insert(0, d["project"]["date"]["litteral"])
        self.dm_rights_e.delete(0, tk.END)
        self.dm_rights_e.insert(0, d["management"]["rights"])
        self.dm_version_e.delete(0, tk.END)
        self.dm_version_e.insert(0, d["management"]["version"])
        self.dm_compat_e.delete(0, tk.END)
        self.dm_compat_e.insert(0, d["management"]["compatibility"])
        self.dm_depositor.set(d["management"]["depositor"])
        self.dm_responsible.set(d["management"]["responsible"])
        self.d_sd.set(d["scientific_director"])
        self.d_creators.set(d["creators"])

    # ------------------------------------------------- Tab 2: Samples ----
    def _build_samples_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(top, text="Physical Objects in the Batch", style="Title.TLabel").pack(side="left")
        self.samples_counter_lbl = ttk.Label(top, text="", style="Counter.TLabel")
        self.samples_counter_lbl.pack(side="right")

        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(toolbar, text="+ Add a sample", style="Accent.TButton",
                   command=self.add_sample).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Edit", style="Flat.TButton",
                   command=self.edit_sample).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Duplicate", style="Flat.TButton",
                   command=self.duplicate_sample).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Move Up", style="Flat.TButton",
                   command=lambda: self.move_sample(-1)).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Move Down", style="Flat.TButton",
                   command=lambda: self.move_sample(1)).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Delete", style="Danger.TButton",
                   command=self.delete_sample).pack(side="right")

        table_frame = ttk.Frame(parent)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("num", "name", "type", "materials", "nature")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {"num": "#", "name": "Name (po_name)", "type": "Type",
                    "materials": "Material(s)", "nature": "Digital Object Nature"}
        widths = {"num": 40, "name": 220, "type": 110, "materials": 180, "nature": 160}
        for c in columns:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", lambda e: self.edit_sample())

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, s in enumerate(self.samples):
            self.tree.insert("", "end", iid=str(i), values=(
                i + 1, s["po"]["name"], s["po"]["type_code"],
                s["po"]["materials"], s["do"]["nature_code"]))
        self.samples_counter_lbl.config(
            text=f"{len(self.samples)} / {MAX_SAMPLES} samples")
        self._refresh_status()

    def _selected_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])

    # -- Actions -----------------------------------------------------------------
    def _get_deposit_info(self):
        self._collect_deposit()
        return {
            "title": self.deposit["title"],
            "rights": self.deposit["management"]["rights"],
            "project_name": self.deposit["project"]["name"],
            "creators": self.deposit["creators"]
        }

    def add_sample(self):
        if len(self.samples) >= MAX_SAMPLES:
            messagebox.showwarning("Limit reached",
                f"This batch already contains the maximum of {MAX_SAMPLES} samples.")
            return

        template = None
        if self.samples:
            template = copy.deepcopy(self.samples[-1])
            template["po"]["name"] = ""
            template["po"]["inventory"] = {"name": "", "id": "", "uri": ""}
            template["_raw_sourceGroup"] = None
            template["_raw_computedInterpretedData"] = None

        def on_save(sample):
            self.samples.append(sample)
            self._refresh_tree()

        SampleDialog(self.root, on_save, deposit_info=self._get_deposit_info(),
                     template=template, index=len(self.samples) + 1)

    def edit_sample(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Selection required", "Select a sample to edit.")
            return

        def on_save(sample):
            self.samples[idx] = sample
            self._refresh_tree()

        SampleDialog(self.root, on_save, deposit_info=self._get_deposit_info(),
                     sample=self.samples[idx], index=idx + 1)

    def duplicate_sample(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Selection required", "Select a sample to duplicate.")
            return
        if len(self.samples) >= MAX_SAMPLES:
            messagebox.showwarning("Limit reached",
                f"This batch already contains the maximum of {MAX_SAMPLES} samples.")
            return
        clone = copy.deepcopy(self.samples[idx])
        clone["po"]["name"] = clone["po"]["name"] + "_copy"
        clone["po"]["inventory"] = {"name": "", "id": "", "uri": ""}

        def on_save(sample):
            self.samples.append(sample)
            self._refresh_tree()

        SampleDialog(self.root, on_save, deposit_info=self._get_deposit_info(),
                     sample=clone, index=len(self.samples) + 1)

    def delete_sample(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Selection required", "Select a sample to delete.")
            return
        name = self.samples[idx]["po"]["name"] or f"#{idx + 1}"
        if messagebox.askyesno("Confirm deletion", f"Delete the sample '{name}'?"):
            del self.samples[idx]
            self._refresh_tree()

    def move_sample(self, direction):
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + direction
        if 0 <= new_idx < len(self.samples):
            self.samples[idx], self.samples[new_idx] = self.samples[new_idx], self.samples[idx]
            self._refresh_tree()
            self.tree.selection_set(str(new_idx))

    # ----------------------------------------------------------- New Batch ----
    def new_batch(self):
        if not messagebox.askyesno("New batch",
                "This will reset the deposit and ALL entered samples (unsaved). Continue?"):
            return
        self.deposit = empty_deposit()
        self.samples = []
        self.current_file_path = None
        self._apply_deposit_to_ui()
        self._refresh_tree()

    # --------------------------------------------------------------- Export XML ----
    def _build_actor_el(self, parent, tag, actor, with_id=False):
        el = sub(parent, tag, with_id=with_id)
        sub(el, "actor_type", actor.get("type_label", "Person")).set(
            "code", actor.get("type_code", "person"))
        sub(el, "actor_litteral", actor.get("literal", ""))
        sub(el, "actor_uri", actor.get("uri", ""))
        return el

    def _build_date_el(self, parent, tag, date, with_id=False):
        el = sub(parent, tag, with_id=with_id)
        sub(el, "date_minDate", date.get("min", ""))
        p1 = sub(el, "date_periodo", date.get("periodo1") or None)
        p2 = sub(el, "date_periodo", date.get("periodo2") or None)
        sub(el, "date_litteralDatation", date.get("litteral", ""))
        return el

    def _build_location_el(self, parent, tag, loc, with_id=False):
        el = sub(parent, tag, with_id=with_id)
        sub(el, "loc_name", loc.get("name", ""))
        sub(el, "loc_geonames", loc.get("geonames", ""))
        sub(el, "log_LongLat", loc.get("longlat", ""))
        sub(el, "loc_French", loc.get("french", ""))
        sub(el, "loc_English", loc.get("english", ""))
        return el

    def _build_event_el(self, parent, tag, event, prefix):
        el = sub(parent, tag, with_id=True)
        self._build_actor_el(el, f"{prefix}_actor", event["actor"])
        self._build_date_el(el, f"{prefix}_date", event["date"], with_id=True)
        self._build_location_el(el, f"{prefix}_location", event["location"], with_id=True)
        return el

    def build_xml_tree(self):
        ET.register_namespace("", NS)
        ET.register_namespace("xsi", XSI_NS)

        self._collect_deposit()
        d = self.deposit

        root = ET.Element(qn("mdacst3D"), {
            "id": new_id(), "version": "2",
            f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION,
        })

        dep_gen = sub(root, "depositGeneral", with_id=True)
        sub(dep_gen, "d_title", d["title"])
        sub(dep_gen, "d_description", d["description"])

        dp = sub(dep_gen, "depositProject", with_id=True)
        sub(dp, "dp_nameProject", d["project"]["name"])
        sub(dp, "dp_contextProject", d["project"]["context"])
        sub(dp, "dp_sciTechObjectives", d["project"]["objectives"])
        sub(dp, "dp_fundings", d["project"]["fundings"])
        dp_date = sub(dp, "dp_date", with_id=True)
        sub(dp_date, "date_minDate", d["project"]["date"]["min"])
        sub(dp_date, "date_maxDate", d["project"]["date"]["max"])
        sub(dp_date, "date_litteralDatation", d["project"]["date"]["litteral"])

        dm = sub(dep_gen, "depositManagement", with_id=True)
        sub(dm, "dm_rights", d["management"]["rights"])
        sub(dm, "dm_version", d["management"]["version"])
        self._build_actor_el(dm, "dm_depositorService", d["management"]["depositor"])
        sub(dm, "dm_compatibility", d["management"]["compatibility"])
        self._build_actor_el(dm, "dm_responsibleEntity", d["management"]["responsible"],
                              with_id=True)

        self._build_actor_el(dep_gen, "d_scientificDirector", d["scientific_director"],
                              with_id=True)
        for creator in d["creators"]:
            self._build_actor_el(dep_gen, "d_creator", creator, with_id=True)

        ds = sub(dep_gen, "depositStructure", with_id=True)
        sub(ds, "ds_nbOfFiles", d["structure"]["nb_files"])
        sub(ds, "ds_size", d["structure"]["size"])
        sub(ds, "ds_content", d["structure"]["content"])

        for sample in self.samples:
            self._build_digital_object_el(root, sample)

        return ET.ElementTree(root)

    def _build_digital_object_el(self, root, sample):
        do = sample["do"]
        po = sample["po"]

        do_el = sub(root, "digitalObject", with_id=True)
        sub(do_el, "object_name", do["name"])
        sub(do_el, "object_nature", do["nature_label"]).set("code", do["nature_code"])
        sub(do_el, "object_licence", do["licence"])
        if do["creator"]["literal"] or do["creator"]["uri"]:
            self._build_actor_el(do_el, "object_creator", do["creator"], with_id=True)
        if do["contributor"]["literal"] or do["contributor"]["uri"]:
            self._build_actor_el(do_el, "object_contributor", do["contributor"], with_id=True)
        sub(do_el, "object_principalElement", do["principal"]).set("code", do["principal"])
        sub(do_el, "object_description", do["description"])
        sub(do_el, "object_thumbnail", do["thumbnail"])
        sub(do_el, "object_collection", do["collection"])
        sub(do_el, "object_contruitID", do["construitID"])

        po_el = sub(do_el, "physicalObject", with_id=True)
        sub(po_el, "po_name", po["name"])
        sub(po_el, "po_type", po["type_label"]).set("code", po["type_code"])
        sub(po_el, "po_materials", po["materials"])
        sub(po_el, "po_description", po["description"])
        for ref in po["references"]:
            sub(po_el, "po_reference", ref)
        for subj in po["subjects"]:
            sub(po_el, "po_subject", subj)

        self._build_event_el(po_el, "po_creation", po["creation"], "po_creation")
        self._build_event_el(po_el, "po_discovery", po["discovery"], "po_discovery")
        self._build_event_el(po_el, "po_conservation", po["conservation"], "po_conservation")

        inv = sub(po_el, "po_inventory", with_id=True)
        sub(inv, "inventory_name", po["inventory"]["name"])
        sub(inv, "inventory_id", po["inventory"]["id"])
        sub(inv, "inventory_uri", po["inventory"]["uri"])

        if sample.get("_raw_sourceGroup") is not None:
            do_el.append(sample["_raw_sourceGroup"])
        else:
            sub(do_el, "sourceGroup", with_id=True)

        if sample.get("_raw_computedInterpretedData") is not None:
            do_el.append(sample["_raw_computedInterpretedData"])
        else:
            sub(do_el, "computedInterpretedData", with_id=True)

    def export_xml(self):
        self._collect_deposit()
        if not self.deposit["title"]:
            messagebox.showerror("Missing title",
                "Please provide the deposit title (tab 1) before exporting.")
            self.notebook.select(self.tab_deposit)
            return
        if not self.samples:
            if not messagebox.askyesno("No sample",
                    "No physical objects have been added. Export the file anyway (deposit only)?"):
                return

        clean_name = re.sub(r'[\\/*?:"<>|]', "", self.deposit["title"]).replace(" ", "_")
        default_name = f"{clean_name or 'metadata'}.xml"
        path = filedialog.asksaveasfilename(
            initialdir=self.default_dir, initialfile=default_name,
            defaultextension=".xml", filetypes=[("XML File", "*.xml")],
            title="Export metadata XML file")
        if not path:
            return

        try:
            tree = self.build_xml_tree()
            ET.indent(tree, space=" ", level=0)
            tree.write(path, encoding="UTF-8", xml_declaration=True)
            self.current_file_path = path
            self.default_dir = os.path.dirname(path)
            self._refresh_status()
            messagebox.showinfo("Export successful", f"XML file exported:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export error", f"Failed to export XML:\n{exc}")

    # ---------------------------------------------------------- XML Loading ----
    def load_xml(self):
        path = filedialog.askopenfilename(
            initialdir=self.default_dir, title="Load metadata XML file",
            filetypes=[("XML File", "*.xml")])
        if not path:
            return
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError as exc:
            messagebox.showerror("Invalid file", f"This XML file is malformed:\n{exc}")
            return
        except Exception as exc:
            messagebox.showerror("Error", f"Unable to read the file:\n{exc}")
            return

        if local_name(root.tag) != "mdacst3D":
            messagebox.showerror("Invalid file",
                                  "This file does not appear to be a valid mdacst3D file.")
            return

        try:
            deposit, samples = self._parse_xml(root)
        except Exception as exc:
            messagebox.showerror("Parsing error",
                                  f"An error occurred while parsing the file:\n{exc}")
            return

        self.deposit = deposit
        self.samples = samples
        self.current_file_path = path
        self.default_dir = os.path.dirname(path)
        self._apply_deposit_to_ui()
        self._refresh_tree()
        messagebox.showinfo("Loading successful",
            f"File loaded: {os.path.basename(path)}\n"
            f"{len(samples)} physical object(s) found.\n\n"
            "Any pre-existing data (photogrammetry, XRF, Raman, HSI) is preserved "
            "and will be rewritten identically upon next export.")

    def _parse_actor(self, el):
        a = empty_actor()
        if el is None:
            return a
        t = find_ln(el, "actor_type")
        if t is not None:
            a["type_code"] = t.get("code", "person")
            a["type_label"] = text_of(t, a["type_code"].capitalize())
        a["literal"] = text_of(find_ln(el, "actor_litteral"))
        a["uri"] = text_of(find_ln(el, "actor_uri"))
        return a

    def _parse_date(self, el):
        dt = empty_date()
        if el is None:
            return dt
        dt["min"] = text_of(find_ln(el, "date_minDate"))
        periodos = findall_ln(el, "date_periodo")
        if len(periodos) > 0:
            dt["periodo1"] = text_of(periodos[0])
        if len(periodos) > 1:
            dt["periodo2"] = text_of(periodos[1])
        dt["litteral"] = text_of(find_ln(el, "date_litteralDatation"))
        return dt

    def _parse_location(self, el):
        loc = empty_location()
        if el is None:
            return loc
        loc["name"] = text_of(find_ln(el, "loc_name"))
        loc["geonames"] = text_of(find_ln(el, "loc_geonames"))
        loc["longlat"] = text_of(find_ln(el, "log_LongLat"))
        loc["french"] = text_of(find_ln(el, "loc_French"))
        loc["english"] = text_of(find_ln(el, "loc_English"))
        return loc

    def _parse_event(self, el, prefix):
        ev = empty_event()
        if el is None:
            return ev
        ev["actor"] = self._parse_actor(find_ln(el, f"{prefix}_actor"))
        ev["date"] = self._parse_date(find_ln(el, f"{prefix}_date"))
        ev["location"] = self._parse_location(find_ln(el, f"{prefix}_location"))
        return ev

    def _parse_xml(self, root):
        deposit = empty_deposit()
        dep_gen = find_ln(root, "depositGeneral")
        if dep_gen is not None:
            deposit["title"] = text_of(find_ln(dep_gen, "d_title"))
            deposit["description"] = text_of(find_ln(dep_gen, "d_description"))

            dp = find_ln(dep_gen, "depositProject")
            if dp is not None:
                deposit["project"]["name"] = text_of(find_ln(dp, "dp_nameProject"))
                deposit["project"]["context"] = text_of(find_ln(dp, "dp_contextProject"))
                deposit["project"]["objectives"] = text_of(find_ln(dp, "dp_sciTechObjectives"))
                deposit["project"]["fundings"] = text_of(find_ln(dp, "dp_fundings"))
                dp_date = find_ln(dp, "dp_date")
                if dp_date is not None:
                    deposit["project"]["date"] = {
                        "min": text_of(find_ln(dp_date, "date_minDate")),
                        "max": text_of(find_ln(dp_date, "date_maxDate")),
                        "litteral": text_of(find_ln(dp_date, "date_litteralDatation")),
                    }

            dm = find_ln(dep_gen, "depositManagement")
            if dm is not None:
                deposit["management"]["rights"] = text_of(find_ln(dm, "dm_rights"))
                deposit["management"]["version"] = text_of(find_ln(dm, "dm_version"))
                deposit["management"]["compatibility"] = text_of(find_ln(dm, "dm_compatibility"))
                deposit["management"]["depositor"] = self._parse_actor(
                    find_ln(dm, "dm_depositorService"))
                deposit["management"]["responsible"] = self._parse_actor(
                    find_ln(dm, "dm_responsibleEntity"))

            sd = find_ln(dep_gen, "d_scientificDirector")
            deposit["scientific_director"] = self._parse_actor(sd)

            deposit["creators"] = [self._parse_actor(c)
                                    for c in findall_ln(dep_gen, "d_creator")]

            ds = find_ln(dep_gen, "depositStructure")
            if ds is not None:
                deposit["structure"] = {
                    "nb_files": text_of(find_ln(ds, "ds_nbOfFiles")),
                    "size": text_of(find_ln(ds, "ds_size")),
                    "content": text_of(find_ln(ds, "ds_content")),
                }

        samples = []
        for do_el in findall_ln(root, "digitalObject"):
            po_el = find_ln(do_el, "physicalObject")
            if po_el is None:
                continue
            sample = empty_sample()

            sample["do"]["name"] = text_of(find_ln(do_el, "object_name"))
            nat = find_ln(do_el, "object_nature")
            if nat is not None:
                sample["do"]["nature_code"] = nat.get("code", "acquisition")
                sample["do"]["nature_label"] = text_of(nat, sample["do"]["nature_code"].capitalize())
            sample["do"]["licence"] = text_of(find_ln(do_el, "object_licence"))
            sample["do"]["creator"] = self._parse_actor(find_ln(do_el, "object_creator"))
            sample["do"]["contributor"] = self._parse_actor(find_ln(do_el, "object_contributor"))
            principal = find_ln(do_el, "object_principalElement")
            if principal is not None:
                sample["do"]["principal"] = principal.get("code", "yes")
            sample["do"]["description"] = text_of(find_ln(do_el, "object_description"))
            sample["do"]["thumbnail"] = text_of(find_ln(do_el, "object_thumbnail"))
            sample["do"]["collection"] = text_of(find_ln(do_el, "object_collection"))
            sample["do"]["construitID"] = text_of(find_ln(do_el, "object_contruitID"))

            sample["po"]["name"] = text_of(find_ln(po_el, "po_name"))
            ptype = find_ln(po_el, "po_type")
            if ptype is not None:
                sample["po"]["type_code"] = ptype.get("code", "artefact")
                sample["po"]["type_label"] = text_of(ptype, sample["po"]["type_code"].capitalize())
            sample["po"]["materials"] = text_of(find_ln(po_el, "po_materials"))
            sample["po"]["description"] = text_of(find_ln(po_el, "po_description"))
            sample["po"]["references"] = [text_of(r) for r in findall_ln(po_el, "po_reference")
                                           if text_of(r)]
            sample["po"]["subjects"] = [text_of(s) for s in findall_ln(po_el, "po_subject")
                                         if text_of(s)]

            sample["po"]["creation"] = self._parse_event(find_ln(po_el, "po_creation"),
                                                           "po_creation")
            sample["po"]["discovery"] = self._parse_event(find_ln(po_el, "po_discovery"),
                                                            "po_discovery")
            sample["po"]["conservation"] = self._parse_event(find_ln(po_el, "po_conservation"),
                                                               "po_conservation")

            inv = find_ln(po_el, "po_inventory")
            if inv is not None:
                sample["po"]["inventory"] = {
                    "name": text_of(find_ln(inv, "inventory_name")),
                    "id": text_of(find_ln(inv, "inventory_id")),
                    "uri": text_of(find_ln(inv, "inventory_uri")),
                }

            sample["_raw_sourceGroup"] = find_ln(do_el, "sourceGroup")
            sample["_raw_computedInterpretedData"] = find_ln(do_el, "computedInterpretedData")

            samples.append(sample)

        return deposit, samples

    # --------------------------------------------------------- Session (JSON) ----
    def _sample_to_jsonable(self, sample):
        return {"do": sample["do"], "po": sample["po"]}

    def save_session(self):
        self._collect_deposit()
        default_name = (re.sub(r'[\\/*?:"<>|]', "", self.deposit["title"]) or "session")
        path = filedialog.asksaveasfilename(
            initialdir=self.default_dir, initialfile=f"{default_name}_session.json",
            defaultextension=".json", filetypes=[("JSON Session", "*.json")],
            title="Save editing session")
        if not path:
            return
        data = {
            "app": APP_TITLE, "version": APP_VERSION,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "deposit": self.deposit,
            "samples": [self._sample_to_jsonable(s) for s in self.samples],
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            self.session_path = path
            self.default_dir = os.path.dirname(path)
            messagebox.showinfo("Session saved", f"Session saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save session:\n{exc}")

    def load_session(self):
        path = filedialog.askopenfilename(
            initialdir=self.default_dir, title="Load an editing session",
            filetypes=[("JSON Session", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.deposit = data["deposit"]
            self.samples = []
            for s in data.get("samples", []):
                sample = empty_sample()
                sample["do"] = s["do"]
                sample["po"] = s["po"]
                self.samples.append(sample)
            self.session_path = path
            self.default_dir = os.path.dirname(path)
            self._apply_deposit_to_ui()
            self._refresh_tree()
            messagebox.showinfo("Session loaded",
                                 f"Session loaded: {os.path.basename(path)}\n"
                                 f"{len(self.samples)} sample(s).")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load session:\n{exc}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    global GEONAMES_USER
    if GEONAMES_USER in ("", "VOTRE_USERNAME_GEONAMES"):
        from tkinter import simpledialog
        _probe = tk.Tk()
        _probe.withdraw()
        _user = simpledialog.askstring(
            "GeoNames - Configuration",
            "Le service GeoNames exige un compte gratuit.\n\n"
            "1. Créez un compte sur https://www.geonames.org/login\n"
            "2. Activez-le pour l'API sur votre page de profil\n"
            "   (lien 'Click here to enable')\n\n"
            "Entrez votre nom d'utilisateur GeoNames :",
            parent=_probe)
        _probe.destroy()
        if _user:
            GEONAMES_USER = _user.strip()
    root = tk.Tk()
    app = BatchMetadataApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()