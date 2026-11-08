### Deep-Dive Overview of SPP 0.3.0

SPP (Simple Plus Plus) 0.3.0 is a robust, statically compiled programming language that bridges beginner-friendly readability with the raw execution speed of native C++. Moving far beyond a basic command-line prototype, version 0.3.0 introduces an advanced Abstract Syntax Tree (AST) expression parser, modular file imports, strict type-checking, and native GUI capabilities.

---

### Core Architectural Features & Capabilities

* **AST Expression Parser:** Replaces legacy line-by-line matching with a typed expression engine that enforces operator precedence and provides intelligent diagnostic feedback.


* **String Interpolation (`f"..."`):** Lets developers evaluate variables and math expressions inline directly inside string literals using `{expr}` without manual text concatenation.


* **First-Class Collections:** Provides native typed dynamic arrays (`list.number`, `list.text`) equipped with robust container methods like `.add()`, `.sort()`, `.reverse()`, and `.length`.


* **Advanced Control Flow & Safety:** Supports numerical range loops (`for ... from ... to`), unconstrained `forever` loops, multi-branch `else if` statements, and structured `try / catch` exception blocks to intercept runtime errors gracefully.


* **Standard Library Modules:** Ships with built-in modules for advanced math (`sqrt`, `clamp`, `random`), text manipulation (`text.upper`, `text.sub`), file/folder I/O, and system/time utilities.



---

### Why You Should Use SPP

* **Blazing Speed & Minimal Footprint:** Because SPP code compiles directly into standard C++17 and links against lightweight headers, compiled binaries start up in under 2 milliseconds and consume less than 1.5 megabytes of RAM during base execution.


* **Clean, Accessible Ergonomics:** SPP eliminates verbose syntax and unnecessary semicolons, favoring clean line-break separation, intuitive variable inference (`v"name"`), and convenient productivity shortcuts like terminal repetition (`ST`) and interactive prompts (`ask`).


* **Rapid Prototyping & GUI Building:** Developers can quickly build tools, automation scripts, and native Win32 window applications using compact shorthand syntax (such as `GB` for buttons and `GT` for text labels).



---

### Device & Platform Compatibility

SPP offers exceptional multi-platform flexibility. Its compilation backend interfaces directly with standard C++ toolchains (`g++` or `clang++`) with `-O2` optimizations enabled to produce optimized native binaries:

* **Operating System Support:** Targets **Windows** (generating standalone `.exe` binaries with native Win32 support), **macOS**, and **Linux** environments seamlessly.


* **Zero Runtime Dependencies:** Once compiled, **SPP binaries do not require Python, interpreters, or heavy virtual machines to run**.
* **Low-Spec Hardware Friendly:** Due to its tiny memory footprint and direct machine-code compilation, SPP is an ideal choice for running high-performance CLI utilities and automation scripts on minimal or resource-constrained hardware.
