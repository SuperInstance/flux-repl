# FLUX REPL — Bytecode Playground

Interactive FLUX bytecode assembler, executor, and debugger.

## Features
- **Assemble**: Write FLUX assembly, get hex bytecodes
- **Execute**: Run bytecodes on built-in VM
- **Trace**: Step-by-step execution log
- **Web UI**: Browser-based playground (index.html)

## Usage

```python
from repl import assemble, execute

# Assemble from text
result = assemble("MOVI R0, 42\nADD R0, R0, R0\nHALT")
print(result["hex"])  # 18 00 2a 20 00 00 00 00

# Execute bytecodes
state = execute(result["bytecode"])
print(state["registers"][:4])  # [84, 0, 0, 0]
```

## Web UI
Open `index.html` in a browser for interactive assembly and visualization.

15 tests passing.
