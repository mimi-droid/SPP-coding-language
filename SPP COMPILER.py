#!/usr/bin/env python3
"""
SPP Compiler 0.3
A small SPP-to-C++ compiler. Generated programs are native executables;
they do not need Python or an SPP interpreter at runtime.

0.3.0 adds: a real typed expression parser, printing variables and
{interpolation}, constants, functions, lists, for/forever loops, else-if,
try/catch, multi-word input, math/text/time/file/system built-ins, imports,
the ST repeating-print shorthand, block scoping and friendlier errors.
"""
from __future__ import annotations
import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = "0.3.0"


class SPPError(Exception):
    def __init__(self, message, line, file=None):
        super().__init__(message)
        self.line = line
        self.file = file


#@@LEGACY_HELPERS@@

#@@LEGACY_GUI@@

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
NUM, TXT, BOOL = "number", "text", "bool"
LNUM, LTXT, LANY = "list.number", "list.text", "list.any"
VOID, ANY = "void", "any"
LISTS = (LNUM, LTXT, LANY)
CTYPES = {
    NUM: "double", TXT: "std::string", BOOL: "bool",
    LNUM: "std::vector<double>", LTXT: "std::vector<std::string>", VOID: "void",
}
ELEM = {LNUM: NUM, LTXT: TXT}
TYPE_NAMES = {"number": NUM, "text": TXT, "bool": BOOL, "list.number": LNUM, "list.text": LTXT}
RESERVED = {"true", "false", "and", "or", "not"}
MODULES = {"text", "time", "system", "file", "folder"}
STD_IMPORTS = {"math", "text", "time", "file", "folder", "system", "random", "list"}
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# ---------------------------------------------------------------------------
# Built-in functions: name -> (signatures, return type, C++ name or {arity: name})
# ---------------------------------------------------------------------------
BUILTINS = {}
for _n, _c in (("sqrt", "spp::sqrt"), ("abs", "std::fabs"), ("floor", "std::floor"),
               ("ceil", "std::ceil"), ("sin", "std::sin"), ("cos", "std::cos"),
               ("tan", "std::tan"), ("ln", "spp::ln"), ("log10", "spp::log10"),
               ("exp", "std::exp")):
    BUILTINS[_n] = ([(NUM,)], NUM, _c)
BUILTINS["round"] = ([(NUM,), (NUM, NUM)], NUM, {1: "std::round", 2: "spp::round_to"})
BUILTINS["min"] = ([(NUM, NUM)], NUM, "spp::min")
BUILTINS["max"] = ([(NUM, NUM)], NUM, "spp::max")
BUILTINS["pow"] = ([(NUM, NUM)], NUM, "std::pow")
BUILTINS["clamp"] = ([(NUM, NUM, NUM)], NUM, "spp::clamp")
BUILTINS["random"] = ([(NUM, NUM)], NUM, "spp::random")
BUILTINS["str"] = ([(ANY,)], TXT, "spp::str")
BUILTINS["num"] = ([(TXT,)], NUM, "spp::tonum")
BUILTINS["isnum"] = ([(TXT,)], BOOL, "spp::isnum")
BUILTINS["text.length"] = ([(TXT,)], NUM, "spp::t_length")
BUILTINS["text.upper"] = ([(TXT,)], TXT, "spp::upper")
BUILTINS["text.lower"] = ([(TXT,)], TXT, "spp::lower")
BUILTINS["text.trim"] = ([(TXT,)], TXT, "spp::trim")
BUILTINS["text.contains"] = ([(TXT, TXT)], BOOL, "spp::t_contains")
BUILTINS["text.replace"] = ([(TXT, TXT, TXT)], TXT, "spp::t_replace")
BUILTINS["text.find"] = ([(TXT, TXT)], NUM, "spp::t_find")
BUILTINS["text.starts"] = ([(TXT, TXT)], BOOL, "spp::t_starts")
BUILTINS["text.ends"] = ([(TXT, TXT)], BOOL, "spp::t_ends")
BUILTINS["text.sub"] = ([(TXT, NUM, NUM)], TXT, "spp::t_sub")
BUILTINS["text.repeat"] = ([(TXT, NUM)], TXT, "spp::t_repeat")
BUILTINS["text.char"] = ([(TXT, NUM)], TXT, "spp::t_char")
BUILTINS["time.now"] = ([()], TXT, "spp::time_now")
BUILTINS["time.date"] = ([()], TXT, "spp::time_date")
BUILTINS["time.seconds"] = ([()], NUM, "spp::time_seconds")
BUILTINS["time.ms"] = ([()], NUM, "spp::time_ms")
BUILTINS["time.sleep"] = ([(NUM,)], VOID, "spp::sleep")
BUILTINS["system.os"] = ([()], TXT, "spp::sys_os")
BUILTINS["system.username"] = ([()], TXT, "spp::sys_username")
BUILTINS["file.create"] = ([(TXT,)], BOOL, "spp::file_create")
BUILTINS["file.write"] = ([(TXT, TXT)], BOOL, "spp::file_write")
BUILTINS["file.append"] = ([(TXT, TXT)], BOOL, "spp::file_append")
BUILTINS["file.read"] = ([(TXT,)], TXT, "spp::file_read")
BUILTINS["file.lines"] = ([(TXT,)], LTXT, "spp::file_lines")
BUILTINS["file.exists"] = ([(TXT,)], BOOL, "spp::file_exists")
BUILTINS["file.delete"] = ([(TXT,)], BOOL, "spp::file_delete")
BUILTINS["folder.create"] = ([(TXT,)], BOOL, "spp::folder_create")
BUILTINS["folder.exists"] = ([(TXT,)], BOOL, "spp::folder_exists")
BUILTINS["folder.delete"] = ([(TXT,)], BOOL, "spp::folder_delete")
BUILTIN_CONSTS = {"pi": ("3.14159265358979323846", NUM)}

# ---------------------------------------------------------------------------
# C++ runtime prelude
# ---------------------------------------------------------------------------
PRELUDE = r"""#include <iostream>
#include <string>
#include <vector>
#include <cmath>
#include <cstdlib>
#include <cstdio>
#include <cctype>
#include <ctime>
#include <chrono>
#include <thread>
#include <random>
#include <algorithm>
#include <sstream>
#include <iomanip>
#include <fstream>
#include <filesystem>
#include <stdexcept>
#include <system_error>
#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace spp {

namespace fs = std::filesystem;

struct Error : std::runtime_error { using std::runtime_error::runtime_error; };

inline void init() {
#ifdef _WIN32
    SetConsoleOutputCP(65001);
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD mode = 0;
    if (h != INVALID_HANDLE_VALUE && GetConsoleMode(h, &mode)) SetConsoleMode(h, mode | 0x0004);
#endif
}

// ---- converting values to text ----
inline std::string str(const std::string& s) { return s; }
inline std::string str(const char* s) { return std::string(s); }
inline std::string str(bool b) { return b ? "true" : "false"; }
inline std::string str(double v) {
    if (std::isnan(v)) return "nan";
    if (std::isinf(v)) return v < 0 ? "-inf" : "inf";
    if (v == 0) return "0";
    if (v == std::floor(v) && std::fabs(v) < 1e15) {
        char b[40];
        std::snprintf(b, sizeof b, "%.0f", v);
        return std::string(b);
    }
    std::ostringstream o;
    o << std::setprecision(10) << v;
    return o.str();
}
template <class T> inline std::string str(const std::vector<T>& v) {
    std::string r = "[";
    for (size_t i = 0; i < v.size(); ++i) { if (i) r += ", "; r += str(v[i]); }
    return r + "]";
}

// ---- math ----
inline double div(double a, double b) { if (b == 0) throw Error("Division by zero"); return a / b; }
inline double mod(double a, double b) { if (b == 0) throw Error("Modulo by zero"); return std::fmod(a, b); }
inline double sqrt(double v) { if (v < 0) throw Error("sqrt() of a negative number"); return std::sqrt(v); }
inline double ln(double v) { if (v <= 0) throw Error("ln() needs a positive number"); return std::log(v); }
inline double log10(double v) { if (v <= 0) throw Error("log10() needs a positive number"); return std::log10(v); }
inline double min(double a, double b) { return a < b ? a : b; }
inline double max(double a, double b) { return a > b ? a : b; }
inline double clamp(double v, double lo, double hi) { if (lo > hi) std::swap(lo, hi); return v < lo ? lo : (v > hi ? hi : v); }
inline double round_to(double v, double d) { double m = std::pow(10.0, d); return std::round(v * m) / m; }
inline std::mt19937_64& rng() { static std::mt19937_64 r{std::random_device{}()}; return r; }
inline double random(double a, double b) {
    long long lo = (long long)std::ceil(min(a, b)), hi = (long long)std::floor(max(a, b));
    if (lo > hi) throw Error("random(): there is no whole number in that range");
    std::uniform_int_distribution<long long> d(lo, hi);
    return (double)d(rng());
}
inline void seed(double s) { rng().seed((unsigned long long)(long long)s); }
inline void sleep(double s) { if (s > 0) std::this_thread::sleep_for(std::chrono::duration<double>(s)); }
inline void clear() { std::cout << "\033[2J\033[H" << std::flush; }

// ---- text (lengths, positions and slices count UTF-8 characters) ----
inline std::vector<size_t> starts(const std::string& s) {
    std::vector<size_t> r;
    for (size_t i = 0; i < s.size(); ++i) if (((unsigned char)s[i] & 0xC0) != 0x80) r.push_back(i);
    return r;
}
inline double t_length(const std::string& s) { return (double)starts(s).size(); }
inline std::string upper(std::string s) { for (auto& c : s) c = (char)std::toupper((unsigned char)c); return s; }
inline std::string lower(std::string s) { for (auto& c : s) c = (char)std::tolower((unsigned char)c); return s; }
inline std::string trim(const std::string& s) {
    const char* ws = " \t\r\n\f\v";
    size_t a = s.find_first_not_of(ws);
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(ws);
    return s.substr(a, b - a + 1);
}
inline bool t_contains(const std::string& s, const std::string& x) { return s.find(x) != std::string::npos; }
inline std::string t_replace(std::string s, const std::string& a, const std::string& b) {
    if (a.empty()) return s;
    size_t p = 0;
    while ((p = s.find(a, p)) != std::string::npos) { s.replace(p, a.size(), b); p += b.size(); }
    return s;
}
inline double t_find(const std::string& s, const std::string& x) {
    size_t p = s.find(x);
    if (p == std::string::npos) return -1;
    double n = 0;
    for (size_t i = 0; i < p; ++i) if (((unsigned char)s[i] & 0xC0) != 0x80) n += 1;
    return n;
}
inline bool t_starts(const std::string& s, const std::string& x) { return s.size() >= x.size() && s.compare(0, x.size(), x) == 0; }
inline bool t_ends(const std::string& s, const std::string& x) { return s.size() >= x.size() && s.compare(s.size() - x.size(), x.size(), x) == 0; }
inline std::string t_sub(const std::string& s, double st, double n) {
    auto p = starts(s);
    long long a = (long long)st, c = (long long)n;
    if (a < 0) { c += a; a = 0; }
    if (c <= 0 || (size_t)a >= p.size()) return "";
    size_t e = std::min<size_t>(p.size(), (size_t)(a + c));
    size_t b0 = p[(size_t)a], b1 = e >= p.size() ? s.size() : p[e];
    return s.substr(b0, b1 - b0);
}
inline std::string t_repeat(const std::string& s, double n) {
    std::string r;
    for (long long i = 0; i < (long long)n; ++i) r += s;
    return r;
}
inline std::string t_char(const std::string& s, double i) {
    auto p = starts(s);
    if (!(i >= 0) || i >= (double)p.size() || i != std::floor(i)) throw Error("Text position out of range: " + str(i));
    size_t k = (size_t)i;
    size_t e = k + 1 < p.size() ? p[k + 1] : s.size();
    return s.substr(p[k], e - p[k]);
}
inline std::vector<std::string> chars(const std::string& s) {
    std::vector<std::string> r;
    for (size_t i = 0; i < t_length(s); ++i) r.push_back(t_char(s, (double)i));
    return r;
}
inline bool try_num(const std::string& s0, double& out) {
    std::string s = trim(s0);
    if (s.empty()) return false;
    for (char c : s) if (!(std::isdigit((unsigned char)c) || c == '+' || c == '-' || c == '.' || c == 'e' || c == 'E')) return false;
    char* end = nullptr;
    double v = std::strtod(s.c_str(), &end);
    if (end == s.c_str() || *end != '\0') return false;
    out = v;
    return true;
}
inline bool isnum(const std::string& s) { double v; return try_num(s, v); }
inline double tonum(const std::string& s) {
    double v;
    if (!try_num(s, v)) throw Error("Cannot turn \"" + s + "\" into a number");
    return v;
}

// ---- lists ----
template <class T> inline T& at(std::vector<T>& v, double i) {
    if (!(i >= 0) || i >= (double)v.size() || i != std::floor(i))
        throw Error("List position " + str(i) + " is out of range (the list has " + str((double)v.size()) + " items)");
    return v[(size_t)i];
}
template <class T> inline const T& at(const std::vector<T>& v, double i) {
    if (!(i >= 0) || i >= (double)v.size() || i != std::floor(i))
        throw Error("List position " + str(i) + " is out of range (the list has " + str((double)v.size()) + " items)");
    return v[(size_t)i];
}
template <class T> inline double len(const std::vector<T>& v) { return (double)v.size(); }
template <class T> inline void add(std::vector<T>& v, const typename std::vector<T>::value_type& x) { v.push_back(x); }
template <class T> inline bool has(const std::vector<T>& v, const typename std::vector<T>::value_type& x) { return std::find(v.begin(), v.end(), x) != v.end(); }
template <class T> inline double index_of(const std::vector<T>& v, const typename std::vector<T>::value_type& x) {
    auto it = std::find(v.begin(), v.end(), x);
    return it == v.end() ? -1.0 : (double)(it - v.begin());
}
template <class T> inline void remove_value(std::vector<T>& v, const typename std::vector<T>::value_type& x) {
    auto it = std::find(v.begin(), v.end(), x);
    if (it != v.end()) v.erase(it);
}
template <class T> inline void remove_at(std::vector<T>& v, double i) { at(v, i); v.erase(v.begin() + (long long)i); }
template <class T> inline void insert_at(std::vector<T>& v, double i, const typename std::vector<T>::value_type& x) {
    if (!(i >= 0) || i > (double)v.size() || i != std::floor(i)) throw Error("List position " + str(i) + " is out of range for insert");
    v.insert(v.begin() + (long long)i, x);
}
template <class T> inline void clear_list(std::vector<T>& v) { v.clear(); }
template <class T> inline void sort_list(std::vector<T>& v) { std::sort(v.begin(), v.end()); }
template <class T> inline void reverse_list(std::vector<T>& v) { std::reverse(v.begin(), v.end()); }
template <class T> inline std::string join(const std::vector<T>& v, const std::string& sep) {
    std::string r;
    for (size_t i = 0; i < v.size(); ++i) { if (i) r += sep; r += str(v[i]); }
    return r;
}

// ---- input (always line based; numbers and bools are re-asked until valid) ----
inline std::string ask_text(const std::string& prompt) {
    std::cout << prompt << std::flush;
    std::string s;
    if (!std::getline(std::cin, s)) { std::cout << std::endl; std::exit(0); }
    if (!s.empty() && s.back() == '\r') s.pop_back();
    return s;
}
inline double ask_number(const std::string& prompt) {
    for (;;) {
        double v;
        if (try_num(ask_text(prompt), v)) return v;
        std::cout << "Please enter a number." << std::endl;
    }
}
inline bool ask_bool(const std::string& prompt) {
    for (;;) {
        std::string s = lower(trim(ask_text(prompt)));
        if (s == "1" || s == "true" || s == "yes" || s == "y") return true;
        if (s == "0" || s == "false" || s == "no" || s == "n") return false;
        std::cout << "Please enter 1 or 0 (or yes / no)." << std::endl;
    }
}

// ---- time and system ----
inline std::string time_fmt(const char* f) {
    std::time_t t = std::time(nullptr);
    char buf[64];
    std::strftime(buf, sizeof buf, f, std::localtime(&t));
    return std::string(buf);
}
inline std::string time_now() { return time_fmt("%H:%M:%S"); }
inline std::string time_date() { return time_fmt("%Y-%m-%d"); }
inline double time_seconds() { return (double)std::time(nullptr); }
inline double time_ms() {
    return (double)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
}
inline std::string sys_os() {
#if defined(_WIN32)
    return "windows";
#elif defined(__APPLE__)
    return "macos";
#else
    return "linux";
#endif
}
inline std::string sys_username() {
    const char* u = std::getenv("USERNAME");
    if (!u) u = std::getenv("USER");
    return u ? std::string(u) : std::string("unknown");
}

// ---- files and folders ----
inline std::string file_read(const std::string& p) {
    std::ifstream f(fs::u8path(p), std::ios::binary);
    if (!f) throw Error("Cannot open file: " + p);
    std::ostringstream o; o << f.rdbuf();
    return o.str();
}
inline bool file_write(const std::string& p, const std::string& t) {
    std::ofstream f(fs::u8path(p), std::ios::binary | std::ios::trunc);
    if (!f) throw Error("Cannot write file: " + p);
    f << t; return true;
}
inline bool file_append(const std::string& p, const std::string& t) {
    std::ofstream f(fs::u8path(p), std::ios::binary | std::ios::app);
    if (!f) throw Error("Cannot write file: " + p);
    f << t; return true;
}
inline bool file_create(const std::string& p) { return file_append(p, ""); }
inline bool file_exists(const std::string& p) { std::error_code e; return fs::is_regular_file(fs::u8path(p), e); }
inline bool file_delete(const std::string& p) { std::error_code e; return fs::remove(fs::u8path(p), e) && !e; }
inline std::vector<std::string> file_lines(const std::string& p) {
    std::istringstream in(file_read(p));
    std::vector<std::string> r; std::string l;
    while (std::getline(in, l)) { if (!l.empty() && l.back() == '\r') l.pop_back(); r.push_back(l); }
    return r;
}
inline bool folder_create(const std::string& p) { std::error_code e; fs::create_directories(fs::u8path(p), e); return !e && fs::is_directory(fs::u8path(p), e); }
inline bool folder_exists(const std::string& p) { std::error_code e; return fs::is_directory(fs::u8path(p), e); }
inline bool folder_delete(const std::string& p) { std::error_code e; return fs::is_directory(fs::u8path(p), e) && fs::remove(fs::u8path(p), e) && !e; }

}  // namespace spp
"""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def strip_comment(line: str) -> str:
    in_str = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "#":
                return line[:i]
        i += 1
    return line


def scan_string(s: str, i: int) -> int:
    """s[i] is an opening quote; return the index just after the closing quote, or -1."""
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == '"':
            return j + 1
        j += 1
    return -1


TOKEN_RE = re.compile(r'''
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<fstr>f"(?:[^"\\]|\\.)*")
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>==|!=|<=|>=|&&|\|\||[-+*/%^()<>!,.\[\]])
''', re.X)


def expand_imports(source: str, filename: str, seen=None):
    """Turn source text into a list of (file, line_number, text), inlining imports."""
    if seen is None:
        seen = set()
    base = Path(filename).parent if filename and not filename.startswith("<") else Path(".")
    try:
        seen.add(str(Path(filename).resolve()))
    except OSError:
        pass
    result = []
    for ln, raw in enumerate(source.splitlines(), 1):
        m = re.fullmatch(r'import\s*"([^"]+)"', strip_comment(raw).strip())
        if not m:
            result.append((filename, ln, raw))
            continue
        name = m.group(1)
        if name in STD_IMPORTS:
            continue
        cand = base / name
        if not cand.exists() and not name.endswith(".spp"):
            cand = base / (name + ".spp")
        if not cand.exists():
            raise SPPError(f'Cannot find module "{name}" (looked for {cand}).', ln, filename)
        key = str(cand.resolve())
        if key in seen:
            continue
        try:
            text = cand.read_text(encoding="utf-8")
        except OSError as e:
            raise SPPError(f'Cannot read module "{name}": {e}', ln, filename)
        result.extend(expand_imports(text, str(cand), seen))
    return result


class Var:
    __slots__ = ("name", "cpp", "type", "const")

    def __init__(self, name, type_, const=False):
        self.name = name
        self.cpp = "v_" + name
        self.type = type_
        self.const = const


class Fn:
    def __init__(self, name, params, ret, declared):
        self.name = name
        self.params = params
        self.ret = ret
        self.declared = declared
        self.rec_num = False
        self.saw_bare = False


# ---------------------------------------------------------------------------
# Expression parser (typed, produces C++ text)
# ---------------------------------------------------------------------------
class ExprParser:
    def __init__(self, comp, src):
        self.c = comp
        self.src = src
        self.toks = self.tokenize(src)
        self.i = 0

    def tokenize(self, src):
        toks = []
        pos = 0
        while pos < len(src):
            m = TOKEN_RE.match(src, pos)
            if not m:
                ch = src[pos]
                if ch == "=":
                    self.c.err("A single '=' can't be used inside an expression; use '==' to compare.")
                if ch == '"':
                    self.c.err("Text is missing its closing quote.")
                self.c.err(f"Unsupported character {ch!r} in expression: {src}")
            pos = m.end()
            if m.lastgroup == "ws":
                continue
            toks.append((m.lastgroup, m.group()))
        return toks

    # -- token helpers --
    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def is_op(self, *ops):
        k, v = self.peek()
        return k == "op" and v in ops

    def is_word(self, *words):
        k, v = self.peek()
        return k == "id" and v in words

    def expect_op(self, op):
        if not self.is_op(op):
            self.c.err(f"Expected '{op}' in expression: {self.src}")
        self.i += 1

    # -- entry points --
    def parse(self):
        if not self.toks:
            self.c.err("Expected an expression.")
        v = self.parse_or()
        if self.i < len(self.toks):
            self.c.err(f"Unexpected '{self.toks[self.i][1]}' in expression: {self.src}")
        return v

    def parse_all_args(self):
        if not self.toks:
            return []
        out = [self.parse_or()]
        while self.is_op(","):
            self.next()
            out.append(self.parse_or())
        if self.i < len(self.toks):
            self.c.err(f"Unexpected '{self.toks[self.i][1]}' in arguments: {self.src}")
        return out

    def parse_args_rest(self):
        """The '(' was already consumed; read arguments up to and including ')'."""
        if self.is_op(")"):
            self.next()
            return []
        out = [self.parse_or()]
        while self.is_op(","):
            self.next()
            out.append(self.parse_or())
        self.expect_op(")")
        return out

    # -- grammar --
    def parse_or(self):
        left = self.parse_and()
        while self.is_word("or") or self.is_op("||"):
            self.next()
            right = self.parse_and()
            left = (f"({self.c.truthy(left)} || {self.c.truthy(right)})", BOOL)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.is_word("and") or self.is_op("&&"):
            self.next()
            right = self.parse_not()
            left = (f"({self.c.truthy(left)} && {self.c.truthy(right)})", BOOL)
        return left

    def parse_not(self):
        if self.is_word("not") or self.is_op("!"):
            self.next()
            v = self.parse_not()
            return (f"(!{self.c.truthy(v)})", BOOL)
        return self.parse_cmp()

    def parse_cmp(self):
        left = self.parse_add()
        if self.is_op("==", "!=", "<", ">", "<=", ">="):
            op = self.next()[1]
            right = self.parse_add()
            lt, rt = left[1], right[1]
            if lt in LISTS or rt in LISTS or lt == VOID or rt == VOID:
                self.c.err("Lists can't be compared with each other.")
            if not (lt == rt or {lt, rt} <= {NUM, BOOL}):
                self.c.err(f"Can't compare {lt} with {rt}.")
            if lt == BOOL and rt == BOOL and op not in ("==", "!="):
                self.c.err("true/false values can only be compared with == or !=.")
            res = (f"({left[0]} {op} {right[0]})", BOOL)
            if self.is_op("==", "!=", "<", ">", "<=", ">="):
                self.c.err("Comparisons can't be chained; join them with 'and' (for example: a < b and b < c).")
            return res
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.is_op("+", "-"):
            op = self.next()[1]
            right = self.parse_mul()
            left = self.c.binop(op, left, right)
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.is_op("*", "/", "%"):
            op = self.next()[1]
            right = self.parse_unary()
            left = self.c.binop(op, left, right)
        return left

    def parse_unary(self):
        if self.is_op("-"):
            self.next()
            v = self.parse_unary()
            if v[1] != NUM:
                self.c.err(f"Can't negate a {v[1]}.")
            return (f"(-{v[0]})", NUM)
        if self.is_op("+"):
            self.next()
            return self.parse_unary()
        return self.parse_pow()

    def parse_pow(self):
        base = self.parse_postfix()
        if self.is_op("^"):
            self.next()
            exp = self.parse_unary()
            return self.c.binop("^", base, exp)
        return base

    def parse_postfix(self):
        v = self.parse_primary()
        while True:
            if self.is_op("["):
                self.next()
                idx = self.parse_or()
                self.expect_op("]")
                if idx[1] != NUM:
                    self.c.err(f"A position must be a number, not {idx[1]}.")
                if v[1] in (LNUM, LTXT):
                    v = (f"spp::at({v[0]}, {idx[0]})", ELEM[v[1]])
                elif v[1] == TXT:
                    v = (f"spp::t_char({v[0]}, {idx[0]})", TXT)
                else:
                    self.c.err(f"Only lists and text can be indexed with [ ], not {v[1]}.")
            elif self.is_op("."):
                self.next()
                k, name = self.next()
                if k != "id":
                    self.c.err("Expected a name after '.'.")
                v = self.method(v, name)
            else:
                break
        return v

    def method(self, v, name):
        t = v[1]
        args = None
        if self.is_op("("):
            self.next()
            args = self.parse_args_rest()
        if t in (LNUM, LTXT):
            et = ELEM[t]
            a = args or []
            if name == "length":
                self.need_args(name, a, 0)
                return (f"spp::len({v[0]})", NUM)
            if name in ("contains", "index"):
                self.need_args(name, a, 1)
                x = self.c.coerce(a[0], et, f".{name}() argument")
                fn = "has" if name == "contains" else "index_of"
                return (f"spp::{fn}({v[0]}, {x})", BOOL if name == "contains" else NUM)
            if name == "join":
                self.need_args(name, a, 1)
                x = self.c.coerce(a[0], TXT, ".join() argument")
                return (f"spp::join({v[0]}, {x})", TXT)
            self.c.err(f"Lists have no .{name} here. Expression methods: length, contains, index, join. "
                       f"Statement methods: add, remove, removeat, insert, clear, sort, reverse.")
        if t == TXT:
            a = args or []
            if name == "length":
                self.need_args(name, a, 0)
                return (f"spp::t_length({v[0]})", NUM)
            key = "text." + name
            if key in BUILTINS:
                return self.call_builtin(key, [v] + a)
            self.c.err(f"Text has no .{name}. Try length, upper, lower, trim, contains, replace, find, starts, ends, sub, repeat or char.")
        self.c.err(f"A {t} value has no .{name}.")

    def need_args(self, name, args, n):
        if len(args) != n:
            self.c.err(f".{name}() takes {n} argument(s) but got {len(args)}.")

    def numlit(self, val):
        return val if ("." in val or "e" in val.lower()) else val + ".0"

    def parse_primary(self):
        k, val = self.next()
        if k is None:
            self.c.err(f"The expression ended unexpectedly: {self.src}")
        if k == "num":
            return (self.numlit(val), NUM)
        if k == "str":
            return (self.c.interpolate(val[1:-1], enable=False), TXT)
        if k == "fstr":
            return (self.c.interpolate(val[2:-1], enable=True), TXT)
        if k == "op":
            if val == "(":
                v = self.parse_or()
                self.expect_op(")")
                return (f"({v[0]})", v[1])
            if val == "[":
                return self.list_literal()
            self.c.err(f"Unexpected '{val}' in expression: {self.src}")
        # identifier
        low = val.lower()
        if low in ("true", "false"):
            return (low, BOOL)
        if val in ("and", "or", "not"):
            self.c.err(f"Unexpected '{val}' in expression: {self.src}")
        var = self.c.lookup(val)
        if var is None and val in MODULES and self.is_op("."):
            self.next()
            k2, name2 = self.next()
            if k2 != "id":
                self.c.err(f"Expected a function name after '{val}.'.")
            key = f"{val}.{name2}"
            if key not in BUILTINS:
                avail = ", ".join(sorted(n.split(".", 1)[1] for n in BUILTINS if n.startswith(val + ".")))
                self.c.err(f"There is no {key}(). {val} functions: {avail}.")
            if not self.is_op("("):
                self.c.err(f"{key} must be called with parentheses, like {key}(...).")
            self.next()
            return self.call_builtin(key, self.parse_args_rest())
        if self.is_op("("):
            if var is not None:
                self.c.err(f"'{val}' is a variable, not a function.")
            self.next()
            args = self.parse_args_rest()
            if val in self.c.functions:
                return self.call_user(val, args)
            if val == "length":
                if len(args) != 1 or args[0][1] not in (TXT, LNUM, LTXT):
                    self.c.err("length() takes one text or list.")
                return (f"spp::{'t_length' if args[0][1] == TXT else 'len'}({args[0][0]})", NUM)
            if val in BUILTINS:
                return self.call_builtin(val, args)
            self.c.err(self.c.unknown_msg(val, "function"))
        if var is not None:
            return (var.cpp, var.type)
        if val in BUILTIN_CONSTS:
            return BUILTIN_CONSTS[val]
        self.c.err(self.c.unknown_msg(val, "variable"))

    def list_literal(self):
        items = []
        if self.is_op("]"):
            self.next()
            return ("{}", LANY)
        items.append(self.parse_or())
        while self.is_op(","):
            self.next()
            items.append(self.parse_or())
        self.expect_op("]")
        t = items[0][1]
        if t not in (NUM, TXT):
            self.c.err(f"Lists can hold numbers or text, not {t}.")
        for it in items:
            if it[1] != t:
                self.c.err(f"All items in a list must be the same type (found {t} and {it[1]}).")
        lt = LNUM if t == NUM else LTXT
        return (f"{CTYPES[lt]}{{{', '.join(i[0] for i in items)}}}", lt)

    def call_builtin(self, name, args):
        sigs, ret, cpp = BUILTINS[name]
        for sig in sigs:
            if len(sig) != len(args):
                continue
            ok = all(p == ANY and a[1] not in (VOID, LANY) or p == a[1] for p, a in zip(sig, args))
            if ok:
                fn = cpp[len(args)] if isinstance(cpp, dict) else cpp
                return (f"{fn}({', '.join(a[0] for a in args)})", ret)
        shown = " or ".join("(" + ", ".join(sig) + ")" for sig in sigs)
        got = "(" + ", ".join(a[1] for a in args) + ")"
        self.c.err(f"{name}() expects {shown} but got {got}.")

    def call_user(self, name, args):
        fn = self.c.functions[name]
        if len(args) != len(fn.params):
            self.c.err(f"{name}() takes {len(fn.params)} argument(s) but got {len(args)}.")
        cpp_args = []
        for n, ((pn, pt), a) in enumerate(zip(fn.params, args), 1):
            cpp_args.append(self.c.coerce(a, pt, f"argument {n} of {name}() ('{pn}')"))
        ret = fn.ret
        if ret is None:
            if self.c.cur_fn is fn:
                ret = NUM
                fn.rec_num = True
            else:
                ret = VOID
        return (f"f_{name}({', '.join(cpp_args)})", ret)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------
DECL_RE = re.compile(r'(v|number|text|bool|list\.number|list\.text|list|const)\s*"([^"]*)"\s*([+\-*/%]?)=(?!=)\s*(.+)')
ASK_RE = re.compile(r'ask(?:\.(number|bool|text))?\s*"([^"]*)"\s*(?:=\s*(.+))?')
ASSIGN_RE = re.compile(r'([A-Za-z_]\w*)\s*([+\-*/%]?)=(?!=)\s*(.+)')
ELEM_ASSIGN_RE = re.compile(r'([A-Za-z_]\w*)\s*\[(.+)\]\s*([+\-*/%]?)=(?!=)\s*(.+)')
LIST_STMT_RE = re.compile(r'([A-Za-z_]\w*)\.(add|remove|removeat|insert|clear|sort|reverse)\s*\((.*)\)')
CALL_STMT_RE = re.compile(r'[A-Za-z_][\w.]*\s*\(.*\)')


class Compiler:
    def __init__(self, lines, filename):
        self.lines = lines
        self.fname = filename
        self.globals = []
        self.funcs = []
        self.main = []
        self.scopes = [{}]
        self.blocks = []
        self.functions = {}
        self.cur_fn = None
        self.fn_lines = None
        self.depth = 2
        self.uid = 0
        self.cur_file = filename
        self.cur_line = 1

    # ---- infrastructure ----
    def err(self, msg):
        raise SPPError(msg, self.cur_line, self.cur_file)

    def emit(self, text):
        buf = self.fn_lines if self.cur_fn is not None else self.main
        buf.append("    " * self.depth + text)

    def new_id(self):
        self.uid += 1
        return self.uid

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def visible_names(self):
        names = set(self.functions) | set(BUILTINS) | set(BUILTIN_CONSTS)
        for scope in self.scopes:
            names |= set(scope)
        return sorted(n for n in names if "." not in n)

    def unknown_msg(self, name, what):
        msg = f"I don't know a {what} called '{name}'."
        close = difflib.get_close_matches(name, self.visible_names(), n=1)
        if close:
            msg += f" Did you mean '{close[0]}'?"
        elif what == "variable":
            msg += f' Create it first with v"{name}" = ...'
        return msg

    def expr(self, src):
        return ExprParser(self, src).parse()

    def expr_list(self, src):
        return ExprParser(self, src).parse_all_args()

    def truthy(self, val):
        cpp, t = val
        if t == BOOL:
            return cpp
        if t == NUM:
            return f"({cpp} != 0)"
        self.err(f"and / or / not need true/false or numbers, not {t}.")

    def cond(self, src):
        v = self.expr(src)
        if v[1] not in (BOOL, NUM):
            self.err(f"A condition must be true/false or a number, not {v[1]}.")
        return self.truthy(v)

    def coerce(self, val, target, what="value"):
        cpp, t = val
        if t == target:
            return cpp
        if t == LANY and target in (LNUM, LTXT):
            return CTYPES[target] + "{}"
        self.err(f"{what}: expected {target} but got {t}.")

    def binop(self, op, a, b):
        (ac, at), (bc, bt) = a, b
        if op == "+" and (at == TXT or bt == TXT):
            if at in LISTS or bt in LISTS or VOID in (at, bt):
                self.err("Lists can't be joined onto text with +. Use list.join(\", \").")
            left = ac if at == TXT else f"spp::str({ac})"
            right = bc if bt == TXT else f"spp::str({bc})"
            return (f"({left} + {right})", TXT)
        if at != NUM or bt != NUM:
            self.err(f"'{op}' needs two numbers, but got {at} and {bt}.")
        if op in ("+", "-", "*"):
            return (f"({ac} {op} {bc})", NUM)
        if op == "/":
            return (f"spp::div({ac}, {bc})", NUM)
        if op == "%":
            return (f"spp::mod({ac}, {bc})", NUM)
        if op == "^":
            return (f"std::pow({ac}, {bc})", NUM)
        self.err(f"Unknown operator '{op}'.")

    # ---- string handling ----
    def interpolate(self, body, enable=True):
        parts, lit = [], []
        has_expr = False
        i, n = 0, len(body)

        def flush():
            if lit:
                parts.append('"' + "".join(lit) + '"')
                lit.clear()

        while i < n:
            ch = body[i]
            if ch == "\\":
                if i + 1 >= n:
                    self.err("Text ends with a lone backslash.")
                nx = body[i + 1]
                if nx in 'nrt"\\':
                    lit.append(ch + nx)
                elif nx in "{}":
                    lit.append(nx)
                else:
                    self.err("Unknown escape '\\" + nx + "' in text. Use \\n, \\t, \\r, \\\", \\\\, \\{ or \\}.")
                i += 2
            elif ch == "{" and enable:
                j = body.find("}", i + 1)
                if j < 0:
                    self.err("Missing '}' in text. Write \\{ for a literal brace.")
                src = body[i + 1:j].replace('\\"', '"').strip()
                if not src:
                    self.err("Empty {} in text. Put an expression inside, or write \\{ for a literal brace.")
                flush()
                cpp, t = self.expr(src)
                if t == VOID:
                    self.err(f"'{src}' doesn't give a value to print.")
                parts.append(f"spp::str({cpp})")
                has_expr = True
                i = j + 1
            else:
                lit.append(ch)
                i += 1
        flush()
        if not parts:
            return "std::string()"
        if not has_expr:
            return f"std::string({parts[0]})"
        return "(std::string() + " + " + ".join(parts) + ")"

    # ---- variables ----
    def store(self, name, val, kind="v", op="", explicit=None):
        """Declare or assign a variable. val is (cpp, type)."""
        if not NAME_RE.fullmatch(name):
            self.err('Variable names must look like "name" and use letters, numbers, or underscores.')
        if name in RESERVED:
            self.err(f"'{name}' is a reserved word and can't be a variable name.")
        var = self.lookup(name)
        if op:
            if var is None:
                self.err(self.unknown_msg(name, "variable"))
            val = self.binop(op, (var.cpp, var.type), val)
        if val[1] == VOID:
            self.err("That call doesn't return a value.")
        if var is not None and kind != "const":
            if var.const:
                self.err(f"'{name}' is a constant and can't be changed.")
            if explicit and explicit != var.type:
                self.err(f"'{name}' already holds a {var.type}; it can't be redeclared as {explicit}.")
            cpp = self.coerce(val, var.type, f"'{name}' holds a {var.type}")
            self.emit(f"{var.cpp} = {cpp};")
            return
        if var is not None and kind == "const" and name in self.scopes[-1]:
            self.err(f"'{name}' is already defined.")
        typ = explicit or val[1]
        if typ == LANY:
            self.err(f'An empty list needs a type: list.number"{name}" = [] or list.text"{name}" = [].')
        cpp = self.coerce(val, typ, f"'{name}' is declared as {typ}")
        new = Var(name, typ, const=(kind == "const"))
        self.scopes[-1][name] = new
        if len(self.scopes) == 1 and self.cur_fn is None:
            self.globals.append(f"static {CTYPES[typ]} {new.cpp};")
            self.emit(f"{new.cpp} = {cpp};")
        else:
            self.emit(f"{'const ' if new.const else ''}{CTYPES[typ]} {new.cpp} = {cpp};")

    # ---- blocks ----
    def push_block(self, kind, inc=1):
        self.blocks.append({"kind": kind, "line": self.cur_line, "file": self.cur_file,
                            "inc": inc, "else": False})
        self.scopes.append({})

    def open_block(self, kind, header):
        self.emit(header)
        self.depth += 1
        self.push_block(kind)

    def in_loop(self):
        for b in reversed(self.blocks):
            if b["kind"] == "loop":
                return True
            if b["kind"] == "fn":
                return False
        return False

    def close_block(self):
        if not self.blocks:
            self.err("Unexpected '}'.")
        block = self.blocks.pop()
        self.scopes.pop()
        if block["kind"] == "fn":
            return self.close_fn()
        for _ in range(block["inc"]):
            self.depth -= 1
            self.emit("}")

    def else_block(self, cond_src=None):
        if not self.blocks or self.blocks[-1]["kind"] != "if":
            self.err("'else' must follow an 'if' block.")
        blk = self.blocks[-1]
        if blk["else"]:
            self.err("This 'if' already has an 'else'.")
        self.scopes.pop()
        self.scopes.append({})
        self.depth -= 1
        if cond_src is None:
            blk["else"] = True
            self.emit("} else {")
        else:
            self.emit(f"}} else if ({self.cond(cond_src)}) {{")
        self.depth += 1

    def catch_block(self):
        if not self.blocks or self.blocks[-1]["kind"] != "try":
            self.err("'catch' must follow a 'try' block.")
        blk = self.blocks[-1]
        blk["kind"] = "catch"
        self.scopes.pop()
        self.scopes.append({})
        self.depth -= 1
        self.emit("} catch (const std::exception& spp_ex) {")
        self.depth += 1
        err_var = Var("error", TXT)
        self.scopes[-1]["error"] = err_var
        self.emit(f"std::string {err_var.cpp} = spp_ex.what();")

    # ---- functions ----
    def open_fn(self, name, params_src, ret_src):
        if self.blocks:
            self.err("Functions must be defined at the top level of the program, not inside another block.")
        if not NAME_RE.fullmatch(name):
            self.err('Function names must look like fn"name" and use letters, numbers, or underscores.')
        if name in self.functions or name in BUILTINS or name == "length":
            self.err(f"'{name}' is already a function or a built-in.")
        params, seen = [], set()
        if params_src.strip():
            for part in params_src.split(","):
                m = re.fullmatch(r"\s*(?:(number|text|bool|list\.number|list\.text)\s+)?([A-Za-z_]\w*)\s*", part)
                if not m:
                    self.err(f"Bad parameter '{part.strip()}'. Write parameters like (a, b) or (text name, number age).")
                t = TYPE_NAMES[m.group(1)] if m.group(1) else NUM
                if m.group(2) in seen:
                    self.err(f"Parameter '{m.group(2)}' is listed twice.")
                seen.add(m.group(2))
                params.append((m.group(2), t))
        ret, declared = None, False
        if ret_src:
            if ret_src == "void":
                ret = VOID
            elif ret_src in TYPE_NAMES:
                ret = TYPE_NAMES[ret_src]
            else:
                self.err(f"Unknown return type '{ret_src}'. Use number, text, bool, list.number, list.text or void.")
            declared = True
        fn = Fn(name, params, ret, declared)
        self.functions[name] = fn
        self.cur_fn = fn
        self.fn_lines = []
        self.depth = 1
        self.push_block("fn", inc=0)
        for pn, pt in params:
            self.scopes[-1][pn] = Var(pn, pt)

    def close_fn(self):
        fn = self.cur_fn
        if fn.ret is None:
            fn.ret = VOID
        if fn.rec_num and fn.ret != NUM:
            self.err(f"{fn.name}() calls itself before its return type is known; add '-> {fn.ret}' to the fn line.")
        if fn.saw_bare and fn.ret != VOID:
            self.err(f"{fn.name}() mixes 'return' and 'return value'.")
        params = ", ".join(f"{CTYPES[t]} v_{n}" for n, t in fn.params)
        lines = [f"static {CTYPES[fn.ret]} f_{fn.name}({params}) {{"] + self.fn_lines
        if fn.ret != VOID:
            lines.append(f'    throw spp::Error("Function \'{fn.name}\' ended without returning a value");')
        lines += ["}", ""]
        self.funcs += lines
        self.cur_fn = None
        self.fn_lines = None
        self.depth = 2

    # ---- statements ----
    def statement(self, s):
        if s == "}":
            return self.close_block()
        m = re.fullmatch(r"\}\s*else\s+if\b\s*(.+?)\s*\{", s)
        if m:
            return self.else_block(m.group(1))
        if re.fullmatch(r"\}\s*else\s*\{", s):
            return self.else_block()
        if re.fullmatch(r"\}\s*catch\s*\{", s):
            return self.catch_block()
        if re.match(r"else\b", s):
            self.err("Write else on the same line as the closing brace, like:  } else {")

        m = re.fullmatch(r'fn\s*"([^"]*)"\s*\((.*)\)\s*(?:->\s*([\w.]+))?\s*\{', s)
        if m:
            return self.open_fn(m.group(1), m.group(2), m.group(3))
        m = re.fullmatch(r"if\b\s*(.+?)\s*\{", s)
        if m:
            c = self.cond(m.group(1))
            return self.open_block("if", f"if ({c}) {{")
        m = re.fullmatch(r"while\b\s*(.+?)\s*\{", s)
        if m:
            c = self.cond(m.group(1))
            return self.open_block("loop", f"while ({c}) {{")
        if re.fullmatch(r"forever\s*\{", s):
            return self.open_block("loop", "for (;;) {")
        m = re.fullmatch(r"repeat\b\s*(.+?)\s*\{", s)
        if m:
            cpp, t = self.expr(m.group(1))
            if t != NUM:
                self.err(f"repeat needs a number, not {t}.")
            k = self.new_id()
            return self.open_block(
                "loop", f"for (long long spp_i{k} = 0, spp_n{k} = (long long)({cpp}); spp_i{k} < spp_n{k}; ++spp_i{k}) {{")
        m = re.fullmatch(r'for\s*"([^"]*)"\s+from\s+(.+?)\s+to\s+(.+?)(?:\s+step\s+(.+?))?\s*\{', s)
        if m:
            return self.open_for_range(*m.groups())
        m = re.fullmatch(r'for\s*"([^"]*)"\s+in\s+(.+?)\s*\{', s)
        if m:
            return self.open_for_each(*m.groups())
        if re.fullmatch(r"try\s*\{", s):
            return self.open_block("try", "try {")

        if s in ("break", "continue"):
            if not self.in_loop():
                self.err(f"'{s}' can only be used inside a loop.")
            return self.emit(s + ";")
        m = re.fullmatch(r"return(?:\s+(.+))?", s)
        if m:
            return self.do_return(m.group(1))
        if s == "c":
            return self.emit("spp::clear();")
        m = re.fullmatch(r"(?:exit|stop)(?:\s+(.+))?", s)
        if m:
            if m.group(1):
                cpp, t = self.expr(m.group(1))
                if t != NUM:
                    self.err("The exit code must be a number.")
                return self.emit(f"std::exit((int)({cpp}));")
            return self.emit("std::exit(0);")

        m = DECL_RE.fullmatch(s)
        if m:
            kind, name, op, rhs = m.groups()
            val = self.expr(rhs)
            explicit = TYPE_NAMES.get(kind)
            if kind == "list":
                if val[1] not in (LNUM, LTXT):
                    self.err(f'list"{name}" needs a list value like [1, 2, 3], or use list.number / list.text for an empty list.')
            if kind in TYPE_NAMES and kind != "list" and self.lookup(name) is None and op:
                self.err(f"'{name}' doesn't exist yet, so '{op}=' can't be used.")
            return self.store(name, val, "const" if kind == "const" else "v", op, explicit)
        if re.match(r'(?:v|number|text|bool|list(?:\.number|\.text)?|const)\s*"', s):
            self.err('Expected something like  v"name" = value  (the same shape works for number, text, bool, list and const).')

        m = ASK_RE.fullmatch(s)
        if m:
            typ, name, prompt_src = m.groups()
            prompt = self.coerce(self.expr(prompt_src), TXT, "the ask prompt") if prompt_src else '""'
            fn = {"number": "ask_number", "bool": "ask_bool"}.get(typ, "ask_text")
            t = {"number": NUM, "bool": BOOL}.get(typ, TXT)
            return self.store(name, (f"spp::{fn}({prompt})", t), "v", "", t)

        if re.match(r'(?:pn|p)"', s):
            return self.print_literal(s)

        m = ELEM_ASSIGN_RE.fullmatch(s)
        if m:
            return self.assign_element(*m.groups())
        m = ASSIGN_RE.fullmatch(s)
        if m:
            name, op, rhs = m.groups()
            if self.lookup(name) is None:
                self.err(self.unknown_msg(name, "variable"))
            return self.store(name, self.expr(rhs), "v", op)

        m = re.fullmatch(r"(pn|p)\s+(.+)", s)
        if m:
            cpp, t = self.expr(m.group(2))
            if t == VOID:
                self.err("That call doesn't give a value to print.")
            end = "std::endl" if m.group(1) == "p" else "std::flush"
            return self.emit(f"std::cout << spp::str({cpp}) << {end};")

        m = re.fullmatch(r"w\s*(\d+(?:\.\d+)?)", s)
        if m:
            return self.emit(f"spp::sleep({m.group(1)});")
        m = re.fullmatch(r"w\s*(\(.*\)|\s.+)", s) or re.fullmatch(r"w\s+(.+)", s)
        if m:
            cpp, t = self.expr(m.group(1))
            if t != NUM:
                self.err(f"w needs a number of seconds, not {t}.")
            return self.emit(f"spp::sleep({cpp});")
        m = re.fullmatch(r"seed\s+(.+)", s)
        if m:
            cpp, t = self.expr(m.group(1))
            if t != NUM:
                self.err("seed needs a number.")
            return self.emit(f"spp::seed({cpp});")
        m = re.fullmatch(r"fail\s+(.+)", s)
        if m:
            cpp = self.coerce(self.expr(m.group(1)), TXT, "fail message")
            return self.emit(f"throw spp::Error({cpp});")

        m = LIST_STMT_RE.fullmatch(s)
        if m:
            var = self.lookup(m.group(1))
            if var is not None and var.type in (LNUM, LTXT):
                return self.list_statement(var, m.group(2), m.group(3))
        if CALL_STMT_RE.fullmatch(s):
            cpp, _t = self.expr(s)
            return self.emit(f"(void){cpp};")

        self.err("I don't recognize this SPP statement: " + s)

    def do_return(self, src):
        fn = self.cur_fn
        if fn is None:
            self.err("'return' can only be used inside a function.")
        if src:
            val = self.expr(src)
            if val[1] == VOID:
                self.err("That call doesn't return a value.")
            if fn.ret == VOID:
                self.err(f"{fn.name}() is declared as void, so it can't return a value.")
            if fn.saw_bare:
                self.err(f"{fn.name}() mixes 'return' and 'return value'.")
            if fn.ret is None:
                if val[1] == LANY:
                    self.err("Can't tell the list type here; add '-> list.number' or '-> list.text' to the fn line.")
                fn.ret = val[1]
            cpp = self.coerce(val, fn.ret, f"{fn.name}() returns {fn.ret}")
            return self.emit(f"return {cpp};")
        if fn.ret not in (None, VOID):
            self.err(f"{fn.name}() returns a {fn.ret}, so 'return' needs a value.")
        fn.saw_bare = True
        self.emit("return;")

    def open_for_range(self, name, a_src, b_src, step_src):
        if not NAME_RE.fullmatch(name):
            self.err('Loop variable names must look like for"i".')
        a, b = self.expr(a_src), self.expr(b_src)
        step = self.expr(step_src) if step_src else None
        for lbl, v in (("start", a), ("end", b), ("step", step)):
            if v is not None and v[1] != NUM:
                self.err(f"The for-loop {lbl} must be a number, not {v[1]}.")
        k = self.new_id()
        self.emit("{")
        self.depth += 1
        self.emit(f"double spp_a{k} = {a[0]};")
        self.emit(f"double spp_b{k} = {b[0]};")
        if step:
            self.emit(f"double spp_s{k} = {step[0]};")
        else:
            self.emit(f"double spp_s{k} = (spp_a{k} <= spp_b{k}) ? 1.0 : -1.0;")
        self.emit(f'if (spp_s{k} == 0) throw spp::Error("A for loop step can\'t be 0");')
        self.emit(f"for (double v_{name} = spp_a{k}; spp_s{k} > 0 ? v_{name} <= spp_b{k} : v_{name} >= spp_b{k}; v_{name} += spp_s{k}) {{")
        self.depth += 1
        self.push_block("loop", inc=2)
        self.scopes[-1][name] = Var(name, NUM)

    def open_for_each(self, name, src):
        if not NAME_RE.fullmatch(name):
            self.err('Loop variable names must look like for"item".')
        cpp, t = self.expr(src)
        if t == TXT:
            cpp, et = f"spp::chars({cpp})", TXT
        elif t in (LNUM, LTXT):
            et = ELEM[t]
        else:
            self.err(f"'for ... in' needs a list or text, not {t}.")
        self.emit(f"for (auto v_{name} : {cpp}) {{")
        self.depth += 1
        self.push_block("loop")
        self.scopes[-1][name] = Var(name, et)

    def print_literal(self, s):
        kind = "pn" if s.startswith("pn") else "p"
        q = s.index('"')
        end = scan_string(s, q)
        if end < 0:
            self.err("Text is missing its closing quote.")
        body = s[q + 1:end - 1]
        rest = s[end:].strip()
        if not rest.startswith("p"):
            self.err(f'Print syntax is {kind}"message"p.')
        rest = rest[1:].strip()
        fexpr = self.interpolate(body)
        tail = "std::endl" if kind == "p" else "std::flush"
        stmt = f"std::cout << {fexpr} << {tail};"
        if not rest:
            return self.emit(stmt)
        m = re.fullmatch(r"ST(\d+(?:\.\d+)?)(?:x(\d+))?", rest)
        if not m:
            self.err('After the closing p, only an ST repeat is allowed, like  p"hi"p ST5  or  p"hi"p ST5x3.')
        delay, times = m.group(1), m.group(2)
        k = self.new_id()
        if times is None:
            self.emit(f"for (;;) {{ {stmt} spp::sleep({delay}); }}")
        else:
            self.emit(f"for (int spp_s{k} = 0; spp_s{k} < {times}; ++spp_s{k}) {{ if (spp_s{k}) spp::sleep({delay}); {stmt} }}")

    def assign_element(self, name, idx_src, op, rhs_src):
        var = self.lookup(name)
        if var is None:
            self.err(self.unknown_msg(name, "variable"))
        if var.type not in (LNUM, LTXT):
            self.err(f"'{name}' is a {var.type}; only lists can be changed with {name}[...] = ...")
        if var.const:
            self.err(f"'{name}' is a constant and can't be changed.")
        idx = self.expr(idx_src)
        if idx[1] != NUM:
            self.err(f"A position must be a number, not {idx[1]}.")
        et = ELEM[var.type]
        target = f"spp::at({var.cpp}, {idx[0]})"
        val = self.expr(rhs_src)
        if op:
            val = self.binop(op, (target, et), val)
        cpp = self.coerce(val, et, f"{name} holds {et} items")
        self.emit(f"{target} = {cpp};")

    def list_statement(self, var, meth, args_src):
        if var.const and meth != "":
            self.err(f"'{var.name}' is a constant and can't be changed.")
        args = self.expr_list(args_src)
        et = ELEM[var.type]
        counts = {"add": 1, "remove": 1, "removeat": 1, "insert": 2, "clear": 0, "sort": 0, "reverse": 0}
        if len(args) != counts[meth]:
            self.err(f".{meth}() takes {counts[meth]} argument(s) but got {len(args)}.")
        v = var.cpp
        if meth == "add":
            self.emit(f"spp::add({v}, {self.coerce(args[0], et, '.add() argument')});")
        elif meth == "remove":
            self.emit(f"spp::remove_value({v}, {self.coerce(args[0], et, '.remove() argument')});")
        elif meth == "removeat":
            self.emit(f"spp::remove_at({v}, {self.coerce(args[0], NUM, '.removeat() position')});")
        elif meth == "insert":
            pos = self.coerce(args[0], NUM, ".insert() position")
            self.emit(f"spp::insert_at({v}, {pos}, {self.coerce(args[1], et, '.insert() value')});")
        elif meth == "clear":
            self.emit(f"spp::clear_list({v});")
        elif meth == "sort":
            self.emit(f"spp::sort_list({v});")
        else:
            self.emit(f"spp::reverse_list({v});")

    # ---- driver ----
    def compile(self):
        for file, ln, raw in self.lines:
            self.cur_file, self.cur_line = file, ln
            s = strip_comment(raw).strip()
            if not s:
                continue
            self.statement(s)
        if self.blocks:
            b = self.blocks[-1]
            raise SPPError("A block opened here was never closed with '}'.", b["line"], b["file"])
        return self.render()

    def render(self):
        out = [f"// Generated by SPP Compiler {VERSION} from {self.fname}", PRELUDE]
        out += self.globals
        out.append("")
        out += self.funcs
        out.append("int main() {")
        out.append("    spp::init();")
        out.append("    try {")
        out += self.main
        out.append("    } catch (const std::exception& spp_err) {")
        out.append('        std::cout << std::flush;')
        out.append('        std::cerr << "\\nSPP runtime error: " << spp_err.what() << std::endl;')
        out.append("        return 1;")
        out.append("    }")
        out.append("    return 0;")
        out.append("}")
        out.append("")
        return "\n".join(out)


GUI_RE = re.compile(r'^\s*gui\s*"', re.M)
GUI_SHORTHAND_RE = re.compile(
    r"(?P<kind>GB|GT)\s*=\s*(?P<align>[MLR])\s*:\s*"
    r"(?P<hook>ID(?:\d+|[A-Za-z_][A-Za-z0-9_]*))",
    re.I,
)
GUI_SHORTHAND_START_RE = re.compile(r"^\s*(?:GB|GT)\b", re.I)


def parse_gui_shorthand(line: str):
    """Parse a GUI declaration into its component, alignment, and flexible hook."""
    match = GUI_SHORTHAND_RE.fullmatch(line.strip())
    if not match:
        return None
    hook = match.group("hook").upper()
    if hook[2:].isdigit():
        hook = f"ID{int(hook[2:])}"
    return match.group("kind").upper(), match.group("align").upper(), hook


def has_gui_shorthand(source: str) -> bool:
    return any(GUI_SHORTHAND_START_RE.match(strip_comment(line)) for line in source.splitlines())


def compile_gui_shorthand(source: str, filename: str) -> str:
    declarations = []
    seen_hooks = set()
    seen_ids = set()
    for line_number, raw in enumerate(source.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        parsed = parse_gui_shorthand(line)
        if parsed is None:
            raise SPPError(
                "GUI shorthand must look like GB=M:ID2 or GT=L:ID3.",
                line_number,
                filename,
            )
        kind, align, hook = parsed
        if hook in seen_hooks:
            raise SPPError(f"GUI hook '{hook}' is already declared.", line_number, filename)
        seen_hooks.add(hook)
        numeric_id = None
        if hook[2:].isdigit():
            number = int(hook[2:])
            if number < 1 or number > 65435:
                raise SPPError("Numeric GUI hooks must be between ID1 and ID65435.", line_number, filename)
            numeric_id = 100 + number
            if numeric_id in seen_ids:
                raise SPPError(f"GUI hook '{hook}' maps to a control ID that is already in use.", line_number, filename)
            seen_ids.add(numeric_id)
        declarations.append((kind, align, hook, numeric_id, line_number))

    if not declarations:
        raise SPPError("Expected at least one GUI shorthand declaration.", 1, filename)

    controls = []
    next_id = 101
    for kind, align, hook, control_id, line_number in declarations:
        if control_id is None:
            while next_id in seen_ids and next_id <= 65535:
                next_id += 1
            if next_id > 65535:
                raise SPPError("No unused Win32 control IDs remain.", line_number, filename)
            control_id = next_id
            seen_ids.add(control_id)
            next_id += 1
        controls.append((kind, align, hook, control_id))

    lines = [
        "// Generated by SPP Compiler: native Win32 GUI",
        "#define WIN32_LEAN_AND_MEAN",
        "#include <windows.h>",
        "#include <algorithm>",
        "",
    ]
    for index, (kind, _align, hook, control_id) in enumerate(controls):
        lines += [
            f"constexpr int kControlID_{index} = {control_id}; // {hook}",
            f"HWND g_control_{index} = nullptr;",
            f"void OnClick_{index}(HWND control) {{",
            f'    SetWindowTextW(control, L"{hook} clicked");',
            "}",
        ]
    lines += [
        "",
        "void LayoutControls(HWND hwnd) {",
        "    RECT client{};",
        "    GetClientRect(hwnd, &client);",
        "    const int clientWidth = client.right - client.left;",
        "    const int clientHeight = client.bottom - client.top;",
    ]
    for index, (kind, align, _hook, _control_id) in enumerate(controls):
        width, height = (120, 36) if kind == "GB" else (160, 28)
        if align == "M":
            x = f"(clientWidth - {width}) / 2"
        elif align == "L":
            x = "16"
        else:
            x = f"clientWidth - {width} - 16"
        lines += [
            f"    if (g_control_{index}) {{",
            f"        const int x = std::max(0, {x});",
            f"        const int y = std::max(0, (clientHeight - {height}) / 2);",
            f"        SetWindowPos(g_control_{index}, nullptr, x, y, {width}, {height},",
            "                     SWP_NOZORDER | SWP_NOACTIVATE);",
            "    }",
        ]
    lines += [
        "}",
        "",
        "LRESULT CALLBACK SppWindowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {",
        "    switch (message) {",
        "    case WM_CREATE:",
    ]
    for index, (kind, _align, hook, _control_id) in enumerate(controls):
        if kind == "GB":
            window_class, caption, style = "BUTTON", "Button", "BS_PUSHBUTTON"
        else:
            window_class, caption, style = "STATIC", "Text", "SS_CENTER | SS_CENTERIMAGE | SS_NOTIFY"
        lines += [
            f'        g_control_{index} = CreateWindowExW(0, L"{window_class}", L"{caption}",',
            f"            WS_CHILD | WS_VISIBLE | {style}, 0, 0, 0, 0, hwnd,",
            f"            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kControlID_{index})),",
            "            GetModuleHandleW(nullptr), nullptr);",
            f"        if (!g_control_{index}) return -1;",
        ]
    lines += [
        "        return 0;",
        "    case WM_SIZE:",
        "        LayoutControls(hwnd);",
        "        return 0;",
        "    case WM_COMMAND:",
        "        switch (LOWORD(wParam)) {",
    ]
    for index, (kind, _align, hook, control_id) in enumerate(controls):
        click_code = "BN_CLICKED" if kind == "GB" else "STN_CLICKED"
        lines += [
            f"        case kControlID_{index}: // {hook}, Win32 ID {control_id}",
            f"            if (HIWORD(wParam) == {click_code}) {{",
            f"                OnClick_{index}(reinterpret_cast<HWND>(lParam));",
            "                return 0;",
            "            }",
            "            break;",
        ]
    lines += [
        "        }",
        "        break;",
        "    case WM_DESTROY:",
        "        PostQuitMessage(0);",
        "        return 0;",
        "    }",
        "    return DefWindowProcW(hwnd, message, wParam, lParam);",
        "}",
        "",
        "int WINAPI WinMain(HINSTANCE instance, HINSTANCE, LPSTR, int showCommand) {",
        "    const wchar_t* className = L\"SPPShorthandWindow\";",
        "    WNDCLASSW windowClass{};",
        "    windowClass.lpfnWndProc = SppWindowProc;",
        "    windowClass.hInstance = instance;",
        "    windowClass.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32512));",
        "    windowClass.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);",
        "    windowClass.lpszClassName = className;",
        "    if (!RegisterClassW(&windowClass)) return 1;",
        "",
        "    HWND hwnd = CreateWindowExW(0, className, L\"SPP GUI\", WS_OVERLAPPEDWINDOW,",
        "        CW_USEDEFAULT, CW_USEDEFAULT, 640, 480, nullptr, nullptr, instance, nullptr);",
        "    if (!hwnd) return 1;",
        "    ShowWindow(hwnd, showCommand);",
        "    UpdateWindow(hwnd);",
        "",
        "    MSG message{};",
        "    while (GetMessageW(&message, nullptr, 0, 0) > 0) {",
        "        TranslateMessage(&message);",
        "        DispatchMessageW(&message);",
        "    }",
        "    return static_cast<int>(message.wParam);",
        "}",
        "",
    ]
    return "\n".join(lines)


def is_gui_source(source: str) -> bool:
    return bool(GUI_RE.search(source) or has_gui_shorthand(source))


def compile_source(source: str, filename: str) -> str:
    if has_gui_shorthand(source):
        return compile_gui_shorthand(source, filename)
    if is_gui_source(source):
        return _compile_gui_legacy(source, filename)
    lines = expand_imports(source, filename)
    return Compiler(lines, filename).compile()


def find_compiler():
    for candidate in ("g++", "clang++"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def build_file(source_path: Path, output_path: Path, keep_cpp=False):
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as e:
        raise SPPError(f"Cannot read '{source_path}': {e}", 1)
    cpp = compile_source(source, str(source_path))
    cpp_path = output_path.with_suffix(".cpp") if keep_cpp else Path(tempfile.gettempdir()) / (output_path.stem + "_spp_generated.cpp")
    cpp_path.write_text(cpp, encoding="utf-8")
    compiler = find_compiler()
    if not compiler:
        raise RuntimeError("No C++ compiler found. Install MSYS2 UCRT64 (g++) or LLVM (clang++), then add its bin folder to PATH.")
    cmd = [compiler, "-std=c++17", "-O2", str(cpp_path), "-o", str(output_path)]
    if is_gui_source(source) and os.name == "nt":
        cmd += ["-luser32", "-lgdi32", "-mwindows"]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError("C++ compilation failed:\n" + detail)
    if not keep_cpp:
        try:
            cpp_path.unlink()
        except OSError:
            pass
    return compiler


def main():
    parser = argparse.ArgumentParser(prog="spp", description="SPP language compiler")
    parser.add_argument("--version", action="version", version=f"SPP Compiler {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("build", "run", "check", "cpp"):
        p = sub.add_parser(cmd, help={"cpp": "print the generated C++ source"}.get(cmd))
        p.add_argument("file", type=Path, help="SPP source file")
        if cmd == "build":
            p.add_argument("-o", "--output", type=Path)
            p.add_argument("--keep-cpp", action="store_true", help="Keep generated C++ source next to the executable")
    args = parser.parse_args()
    try:
        if args.command in ("check", "cpp"):
            cpp = compile_source(args.file.read_text(encoding="utf-8"), str(args.file))
            if args.command == "cpp":
                print(cpp)
            else:
                print(f"SPP check passed: {args.file}")
            return 0
        output = args.output if args.command == "build" and args.output else args.file.with_suffix(".exe" if os.name == "nt" else "")
        compiler = build_file(args.file, output, getattr(args, "keep_cpp", False))
        print(f"Built: {output}")
        print(f"Using: {compiler}")
        if args.command == "run":
            result = subprocess.run([str(output.resolve())])
            return result.returncode
        return 0
    except SPPError as e:
        print(f"{e.file or args.file}:{e.line}: SPP error: {e}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as e:
        print(f"SPP error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())