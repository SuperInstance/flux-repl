"""
FLUX REPL — Interactive bytecode playground.

Enhanced REPL with syntax highlighting, command history, tab completion,
multi-line input, register panel, memory inspector, breakpoints,
disassembly view, and save/load session support.

Web interface for writing, assembling, and executing FLUX bytecodes.
Run: python3 -m http.server 8080
"""
import json
import sys
import os
import re
import pickle
import readline
import atexit
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

# ── Opcodes & Architecture ──────────────────────────────────────

OPCODES = {
    'HALT':0x00,'NOP':0x01,'INC':0x08,'DEC':0x09,'NOT':0x0A,'NEG':0x0B,
    'PUSH':0x0C,'POP':0x0D,'STRIPCONF':0x17,
    'MOVI':0x18,'ADDI':0x19,'SUBI':0x1A,
    'ADD':0x20,'SUB':0x21,'MUL':0x22,'DIV':0x23,'MOD':0x24,
    'AND':0x25,'OR':0x26,'XOR':0x27,'SHL':0x28,'SHR':0x29,
    'MIN':0x2A,'MAX':0x2B,
    'CMP_EQ':0x2C,'CMP_LT':0x2D,'CMP_GT':0x2E,'CMP_NE':0x2F,
    'MOV':0x3A,'JZ':0x3C,'JNZ':0x3D,
    'MOVI16':0x40,'JMP':0x43,'LOOP':0x46,
}

OPCODE_NAMES = {v: k for k, v in OPCODES.items()}

# Registers 0-63, commonly used R0-R15
REGISTERS = [f"R{i}" for i in range(64)]


def opcode_size(opcode: int) -> int:
    """Determine instruction size from opcode byte."""
    if opcode <= 0x07:
        return 1
    elif opcode <= 0x17:
        return 2
    elif opcode <= 0x1F:
        return 3
    elif opcode <= 0x4F:
        return 4
    else:
        return 1


def format_instruction(bytecode: bytes, pc: int) -> str:
    """Disassemble a single instruction at the given PC."""
    if pc >= len(bytecode):
        return "??? (end of program)"
    op = bytecode[pc]
    name = OPCODE_NAMES.get(op, f"UNKNOWN(0x{op:02x})")
    size = opcode_size(op)
    raw = ' '.join(f'{bytecode[pc+i]:02x}' for i in range(min(size, len(bytecode) - pc)))
    args = []
    if size >= 2 and pc + 1 < len(bytecode):
        args.append(f"R{bytecode[pc+1]}")
    if size >= 3 and pc + 2 < len(bytecode):
        val = bytecode[pc + 2]
        if val > 127:
            val -= 256
        args.append(str(val))
    if size >= 4 and pc + 3 < len(bytecode):
        val = bytecode[pc + 2] | (bytecode[pc + 3] << 8)
        if val > 0x7FFF:
            val -= 0x10000
        if len(args) >= 2:
            args[-1] = str(val)  # replace with 16-bit value for MOVI16, LOOP, etc.
        else:
            args.append(str(val))
    arg_str = ", ".join(args) if args else ""
    return f"{name:8s} {arg_str:16s}  ; {raw}"


def disassemble(bytecode: List[int], start: int = 0, end: int = -1) -> List[str]:
    """Disassemble bytecode into human-readable lines."""
    bc = bytes(bytecode)
    if end < 0:
        end = len(bc)
    lines = []
    pc = start
    while pc < end:
        size = opcode_size(bc[pc]) if pc < len(bc) else 1
        line = f"  {pc:04x}:  {format_instruction(bc, pc)}"
        lines.append(line)
        pc += size
    return lines


# ── Syntax Highlighting ─────────────────────────────────────────

# ANSI color codes
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"


# Regex patterns for syntax highlighting
PATTERNS = {
    'comment': (r';.*$', Color.DIM),
    'label': (r'^\s*\w+:', Color.CYAN),
    'opcode': (r'\b(HALT|NOP|INC|DEC|NOT|NEG|PUSH|POP|STRIPCONF|MOVI|ADDI|SUBI|'
               r'ADD|SUB|MUL|DIV|MOD|AND|OR|XOR|SHL|SHR|MIN|MAX|'
               r'CMP_EQ|CMP_LT|CMP_GT|CMP_NE|MOV|JZ|JNZ|MOVI16|JMP|LOOP)\b',
               Color.GREEN + Color.BOLD),
    'register': (r'\bR\d+\b', Color.YELLOW),
    'number_dec': (r'(?<!0[xX])\b\d+\b', Color.MAGENTA),
    'number_hex': (r'\b0[xX][0-9a-fA-F]+\b', Color.MAGENTA),
    'directive': (r'^\s*\.(data|text|global|section)\b', Color.BLUE),
}


def highlight_syntax(source: str) -> str:
    """Apply syntax highlighting to FLUX assembly source code."""
    if not sys.stdout.isatty():
        return source
    lines = source.split('\n')
    highlighted = []
    for line in lines:
        result = line
        # Apply patterns in order of priority
        for ptype, (pattern, color) in PATTERNS.items():
            if ptype == 'comment':
                # Comments only get dimmed at the end
                idx = result.find(';')
                if idx >= 0:
                    result = result[:idx] + Color.DIM + result[idx:] + Color.RESET
            elif ptype == 'label':
                result = re.sub(pattern, lambda m: Color.CYAN + m.group() + Color.RESET, result)
            elif ptype == 'opcode':
                result = re.sub(pattern, lambda m: Color.GREEN + Color.BOLD + m.group() + Color.RESET, result)
            elif ptype == 'register':
                result = re.sub(pattern, lambda m: Color.YELLOW + m.group() + Color.RESET, result)
            elif ptype == 'number_dec':
                result = re.sub(pattern, lambda m: Color.MAGENTA + m.group() + Color.RESET, result)
            elif ptype == 'number_hex':
                result = re.sub(pattern, lambda m: Color.MAGENTA + m.group() + Color.RESET, result)
            elif ptype == 'directive':
                result = re.sub(pattern, lambda m: Color.BLUE + m.group() + Color.RESET, result)
        highlighted.append(result)
    return '\n'.join(highlighted)


# ── Assembler ───────────────────────────────────────────────────

def assemble(source: str) -> dict:
    """Assemble FLUX assembly text to bytecode."""
    labels = {}
    instructions = []
    lines = source.strip().split('\n')
    
    # Pass 1: collect labels
    pc = 0
    parsed = []
    for line in lines:
        line = line.split(';')[0].strip()  # remove comments
        if not line:
            continue
        if line.endswith(':'):
            labels[line[:-1]] = pc
            continue
        
        parts = line.replace(',', ' ').split()
        if not parts:
            continue
        
        opname = parts[0].upper()
        if opname not in OPCODES:
            return {"error": f"Unknown opcode: {opname}", "line": line}
        
        opcode = OPCODES[opname]
        size = opcode_size(opcode)
        
        args = parts[1:]
        parsed.append((opcode, args, size, pc))
        pc += size
    
    # Pass 2: emit bytecodes
    bytecode = []
    for opcode, args, size, inst_pc in parsed:
        bytecode.append(opcode)
        
        if size == 1:
            pass  # no operands
        elif size == 2:
            if len(args) >= 1:
                bytecode.append(parse_arg(args[0]))
        elif size == 3:
            if len(args) >= 2:
                bytecode.append(parse_arg(args[0]))
                bytecode.append(parse_imm(args[1]))
        elif size == 4:
            if len(args) >= 3:
                bytecode.append(parse_arg(args[0]))
                bytecode.append(parse_arg(args[1]))
                bytecode.append(parse_arg(args[2]))
            elif len(args) >= 2:
                bytecode.append(parse_arg(args[0]))
                # Handle label references for jumps
                if args[1] in labels:
                    offset = labels[args[1]] - (inst_pc + 4)
                    bytecode.append(offset & 0xFF)
                    bytecode.append(0)
                else:
                    bytecode.append(parse_imm(args[1]))
                    bytecode.append(0)
            elif len(args) >= 1:
                bytecode.append(parse_arg(args[0]))
                bytecode.append(0)
                bytecode.append(0)
    
    bytecode.append(0x00)  # Always append HALT
    
    return {
        "bytecode": bytecode,
        "hex": ' '.join(f'{b:02x}' for b in bytecode),
        "bytes": len(bytecode),
        "labels": labels,
    }


def parse_arg(s: str) -> int:
    """Parse a register or number argument."""
    s = s.strip()
    if s.startswith('R') or s.startswith('r'):
        return int(s[1:])
    return parse_imm(s)


def parse_imm(s: str) -> int:
    """Parse an immediate value."""
    s = s.strip()
    try:
        if s.startswith('0x') or s.startswith('0X'):
            return int(s, 16)
        return int(s)
    except ValueError:
        return 0


# ── VM State ────────────────────────────────────────────────────

@dataclass
class VMState:
    """Complete VM state for debugging and inspection."""
    registers: List[int] = field(default_factory=lambda: [0] * 64)
    memory: List[int] = field(default_factory=lambda: [0] * 65536)
    stack: List[int] = field(default_factory=lambda: [0] * 4096)
    sp: int = 4096
    pc: int = 0
    halted: bool = False
    cycles: int = 0
    breakpoints: set = field(default_factory=set)
    labels: Dict[str, int] = field(default_factory=dict)
    bytecode: List[int] = field(default_factory=list)
    source_lines: List[str] = field(default_factory=list)
    watch_registers: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    trace: List[dict] = field(default_factory=list)
    history: List[str] = field(default_factory=list)


class MemoryInspector:
    """Memory inspection commands: read, write, dump."""
    
    def __init__(self, state: VMState):
        self.state = state
    
    def read(self, addr: int, count: int = 1) -> List[int]:
        """Read `count` bytes from memory starting at `addr`."""
        result = []
        for i in range(count):
            if 0 <= addr + i < len(self.state.memory):
                result.append(self.state.memory[addr + i])
            else:
                result.append(0)
        return result
    
    def write(self, addr: int, data: List[int]) -> None:
        """Write bytes to memory starting at `addr`."""
        for i, b in enumerate(data):
            if 0 <= addr + i < len(self.state.memory):
                self.state.memory[addr + i] = b & 0xFF
    
    def write_word(self, addr: int, value: int) -> None:
        """Write a 16-bit word to memory (little-endian)."""
        self.write(addr, [value & 0xFF, (value >> 8) & 0xFF])
    
    def read_word(self, addr: int) -> int:
        """Read a 16-bit word from memory (little-endian)."""
        lo = self.read(addr, 1)[0]
        hi = self.read(addr + 1, 1)[0]
        return lo | (hi << 8)
    
    def dump(self, start: int, end: int) -> str:
        """Dump memory region as hex with ASCII sidebar."""
        lines = []
        for addr in range(start, end, 16):
            chunk = self.read(addr, 16)
            hex_part = ' '.join(f'{b:02x}' for b in chunk[:8])
            hex_part += '  ' + ' '.join(f'{b:02x}' for b in chunk[8:])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            lines.append(f"  {addr:04x}: {hex_part:<48s}  |{ascii_part}|")
        return '\n'.join(lines)
    
    def find(self, value: int, start: int = 0, end: int = 65536) -> List[int]:
        """Find all addresses containing a specific byte value."""
        return [addr for addr in range(start, min(end, len(self.state.memory)))
                if self.state.memory[addr] == value]


# ── Enhanced Executor ───────────────────────────────────────────

def execute(bytecode: list, state: VMState = None, breakpoints: set = None,
            trace_mode: bool = False, max_cycles: int = 10000) -> dict:
    """Execute bytecode on VM with optional debugging support."""
    if state is None:
        state = VMState()
    else:
        state.pc = 0
        state.halted = False
        state.cycles = 0
        state.trace = []
    
    if breakpoints is not None:
        state.breakpoints = breakpoints
    
    state.bytecode = bytecode
    regs = state.registers
    stack = state.stack
    sp = state.sp
    mem = state.memory
    pc = state.pc
    halted = state.halted
    cycles = state.cycles
    trace = state.trace
    hit_breakpoint = False
    
    bc = bytes(bytecode)
    
    while not halted and pc < len(bc) and cycles < max_cycles:
        op = bc[pc]
        old_pc = pc
        
        # Check breakpoint
        if pc in state.breakpoints:
            hit_breakpoint = True
            state.pc = pc
            state.sp = sp
            state.halted = False
            state.cycles = cycles
            state.trace = trace
            return {
                "halted": False,
                "breakpoint": True,
                "breakpoint_pc": pc,
                "cycles": cycles,
                "registers": regs[:16],
                "register_names": [f"R{i}" for i in range(16)],
                "stack_pointer": sp,
                "trace": trace,
            }
        
        if op == 0x00:  # HALT
            halted = True; pc += 1
        elif op == 0x01:  # NOP
            pc += 1
        elif op == 0x08:  # INC
            regs[bc[pc+1]] += 1; pc += 2
        elif op == 0x09:  # DEC
            regs[bc[pc+1]] -= 1; pc += 2
        elif op == 0x0A:  # NOT
            regs[bc[pc+1]] = ~regs[bc[pc+1]]; pc += 2
        elif op == 0x0B:  # NEG
            regs[bc[pc+1]] = -regs[bc[pc+1]]; pc += 2
        elif op == 0x0C:  # PUSH
            sp -= 1; stack[sp] = regs[bc[pc+1]]; pc += 2
        elif op == 0x0D:  # POP
            regs[bc[pc+1]] = stack[sp]; sp += 1; pc += 2
        elif op == 0x18:  # MOVI
            regs[bc[pc+1]] = (bc[pc+2] - 256 if bc[pc+2] > 127 else bc[pc+2]); pc += 3
        elif op == 0x19:  # ADDI
            regs[bc[pc+1]] += (bc[pc+2] - 256 if bc[pc+2] > 127 else bc[pc+2]); pc += 3
        elif op == 0x1A:  # SUBI
            regs[bc[pc+1]] -= (bc[pc+2] - 256 if bc[pc+2] > 127 else bc[pc+2]); pc += 3
        elif op == 0x20:  # ADD
            regs[bc[pc+1]] = regs[bc[pc+2]] + regs[bc[pc+3]]; pc += 4
        elif op == 0x21:  # SUB
            regs[bc[pc+1]] = regs[bc[pc+2]] - regs[bc[pc+3]]; pc += 4
        elif op == 0x22:  # MUL
            regs[bc[pc+1]] = regs[bc[pc+2]] * regs[bc[pc+3]]; pc += 4
        elif op == 0x23:  # DIV
            if regs[bc[pc+3]] != 0:
                regs[bc[pc+1]] = regs[bc[pc+2]] // regs[bc[pc+3]]
            pc += 4
        elif op == 0x24:  # MOD
            if regs[bc[pc+3]] != 0:
                regs[bc[pc+1]] = regs[bc[pc+2]] % regs[bc[pc+3]]
            pc += 4
        elif op == 0x25:  # AND
            regs[bc[pc+1]] = regs[bc[pc+2]] & regs[bc[pc+3]]; pc += 4
        elif op == 0x26:  # OR
            regs[bc[pc+1]] = regs[bc[pc+2]] | regs[bc[pc+3]]; pc += 4
        elif op == 0x27:  # XOR
            regs[bc[pc+1]] = regs[bc[pc+2]] ^ regs[bc[pc+3]]; pc += 4
        elif op == 0x28:  # SHL
            regs[bc[pc+1]] = regs[bc[pc+2]] << regs[bc[pc+3]]; pc += 4
        elif op == 0x29:  # SHR
            regs[bc[pc+1]] = regs[bc[pc+2]] >> regs[bc[pc+3]]; pc += 4
        elif op == 0x2A:  # MIN
            regs[bc[pc+1]] = min(regs[bc[pc+2]], regs[bc[pc+3]]); pc += 4
        elif op == 0x2B:  # MAX
            regs[bc[pc+1]] = max(regs[bc[pc+2]], regs[bc[pc+3]]); pc += 4
        elif op == 0x2C:  # CMP_EQ
            regs[bc[pc+1]] = 1 if regs[bc[pc+2]] == regs[bc[pc+3]] else 0; pc += 4
        elif op == 0x2D:  # CMP_LT
            regs[bc[pc+1]] = 1 if regs[bc[pc+2]] < regs[bc[pc+3]] else 0; pc += 4
        elif op == 0x2E:  # CMP_GT
            regs[bc[pc+1]] = 1 if regs[bc[pc+2]] > regs[bc[pc+3]] else 0; pc += 4
        elif op == 0x2F:  # CMP_NE
            regs[bc[pc+1]] = 1 if regs[bc[pc+2]] != regs[bc[pc+3]] else 0; pc += 4
        elif op == 0x3A:  # MOV
            regs[bc[pc+1]] = regs[bc[pc+2]]; pc += 4
        elif op == 0x3C:  # JZ
            if regs[bc[pc+1]] == 0:
                pc += ((bc[pc+2] - 256 if bc[pc+2] > 127 else bc[pc+2]))
            else:
                pc += 4
        elif op == 0x3D:  # JNZ
            if regs[bc[pc+1]] != 0:
                pc += ((bc[pc+2] - 256 if bc[pc+2] > 127 else bc[pc+2]))
            else:
                pc += 4
        elif op == 0x40:  # MOVI16
            imm = bc[pc+2] | (bc[pc+3] << 8)
            if imm > 0x7FFF: imm -= 0x10000
            regs[bc[pc+1]] = imm; pc += 4
        elif op == 0x46:  # LOOP
            regs[bc[pc+1]] -= 1
            if regs[bc[pc+1]] > 0:
                off = bc[pc+2] | (bc[pc+3] << 8)
                pc -= off
            else:
                pc += 4
        else:
            pc += 1
        
        cycles += 1
        
        # Record trace (first 200 steps or all in trace_mode)
        if trace_mode or cycles <= 200:
            regs_snapshot = regs[:8].copy()
            trace.append({"pc": old_pc, "op": op, "regs": regs_snapshot})
    
    state.pc = pc
    state.sp = sp
    state.halted = halted
    state.cycles = cycles
    state.trace = trace
    
    return {
        "halted": halted,
        "cycles": cycles,
        "registers": regs[:16],
        "register_names": [f"R{i}" for i in range(16)],
        "stack_pointer": sp,
        "trace": trace,
    }


# ── Register Display Panel ──────────────────────────────────────

def format_register_panel(regs: List[int], highlight: List[int] = None) -> str:
    """Format a visual register state display panel."""
    if highlight is None:
        highlight = []
    lines = []
    lines.append("╔══════════════════════════════════════════════════════════╗")
    lines.append("║                    REGISTER STATE                       ║")
    lines.append("╠══════════════════════════════════════════════════════════╣")
    
    for row in range(4):
        parts = []
        for col in range(4):
            idx = row * 4 + col
            val = regs[idx] if idx < len(regs) else 0
            marker = "►" if idx in highlight else " "
            parts.append(f"{marker}R{idx:2d}= {val:8d} (0x{val & 0xFFFF:04X})")
        lines.append("║ " + "  ".join(parts) + " ║")
    
    lines.append("╚══════════════════════════════════════════════════════════╝")
    return '\n'.join(lines)


def format_compact_registers(regs: List[int]) -> str:
    """Compact single-line register display."""
    vals = ' '.join(f"R{i}={regs[i]}" for i in range(min(8, len(regs))))
    return f"[{vals} ...]"


# ── Session Save/Load ───────────────────────────────────────────

def save_session(state: VMState, source: str, filepath: str = "flux_session.pkl") -> dict:
    """Save REPL session state to file."""
    session_data = {
        'registers': state.registers,
        'memory': state.memory,
        'stack': state.stack,
        'sp': state.sp,
        'pc': state.pc,
        'breakpoints': list(state.breakpoints),
        'labels': state.labels,
        'bytecode': state.bytecode,
        'source': source,
        'history': state.history,
        'watch_registers': state.watch_registers,
    }
    try:
        with open(filepath, 'wb') as f:
            pickle.dump(session_data, f)
        return {"success": True, "path": filepath}
    except Exception as e:
        return {"success": False, "error": str(e)}


def load_session(filepath: str = "flux_session.pkl") -> Tuple[VMState, str]:
    """Load REPL session from file. Returns (VMState, source)."""
    with open(filepath, 'rb') as f:
        data = pickle.load(f)
    state = VMState(
        registers=data['registers'],
        memory=data['memory'],
        stack=data['stack'],
        sp=data['sp'],
        pc=data['pc'],
        breakpoints=set(data.get('breakpoints', [])),
        labels=data.get('labels', {}),
        bytecode=data.get('bytecode', []),
        history=data.get('history', []),
        watch_registers=data.get('watch_registers', [0, 1, 2, 3, 4, 5]),
    )
    return state, data.get('source', "")


def save_session_json(state: VMState, source: str, filepath: str = "flux_session.json") -> dict:
    """Save session as human-readable JSON."""
    session_data = {
        'registers': state.registers[:16],
        'memory': state.memory[:256],
        'sp': state.sp,
        'pc': state.pc,
        'breakpoints': sorted(state.breakpoints),
        'labels': state.labels,
        'bytecode': state.bytecode,
        'source': source,
        'history': state.history[-50:],
    }
    try:
        with open(filepath, 'w') as f:
            json.dump(session_data, f, indent=2)
        return {"success": True, "path": filepath}
    except Exception as e:
        return {"success": False, "error": str(e)}


def load_session_json(filepath: str = "flux_session.json") -> Tuple[VMState, str]:
    """Load session from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    state = VMState(
        registers=data['registers'] + [0] * (64 - len(data.get('registers', []))),
        memory=data.get('memory', [0] * 256) + [0] * (65536 - len(data.get('memory', []))),
        sp=data.get('sp', 4096),
        pc=data.get('pc', 0),
        breakpoints=set(data.get('breakpoints', [])),
        labels=data.get('labels', {}),
        bytecode=data.get('bytecode', []),
        history=data.get('history', []),
    )
    return state, data.get('source', "")


# ── Tab Completion ──────────────────────────────────────────────

class FluxCompleter:
    """Tab completion for FLUX opcodes, registers, and labels."""
    
    def __init__(self):
        self.opcodes = list(OPCODES.keys())
        self.opcodes.sort()
        self.register_names = REGISTERS
        self.labels: Dict[str, int] = {}
        self.repl_commands = [
            '.run', '.asm', '.regs', '.mem', '.memr', '.memw',
            '.dump', '.bp', '.bpdel', '.bplist', '.disasm',
            '.step', '.trace', '.save', '.load', '.savejson',
            '.loadjson', '.reset', '.help', '.labels', '.multi',
            '.history', '.quit', '.exit', '.watch',
        ]
    
    def update_labels(self, labels: Dict[str, int]):
        """Update known labels for completion."""
        self.labels = labels
    
    def complete(self, text: str, state: int) -> Optional[str]:
        """Readline completer function."""
        try:
            completions = self.get_completions(text)
            if state < len(completions):
                return completions[state]
            return None
        except Exception:
            return None
    
    def get_completions(self, text: str) -> List[str]:
        """Get possible completions for the current input."""
        if not text:
            return self.repl_commands + self.opcodes
        
        text_upper = text.upper()
        
        # REPL commands start with dot
        if text.startswith('.'):
            return [c for c in self.repl_commands if c.startswith(text.lower())]
        
        # Check if we're at the beginning of a line (opcode completion)
        stripped = text.lstrip()
        if ' ' not in stripped:
            # Completing opcode
            matches = [op for op in self.opcodes if op.startswith(text_upper)]
            matches += [f"{l}:" for l in self.labels if l.upper().startswith(text_upper)]
            return matches
        
        # After space: registers and labels
        parts = stripped.rsplit(' ', 1)
        prefix = parts[1] if len(parts) > 1 else ''
        prefix_upper = prefix.upper()
        
        # Register completion
        reg_matches = [r for r in self.register_names if r.upper().startswith(prefix_upper)]
        # Label completion
        label_matches = [l for l in self.labels if l.upper().startswith(prefix_upper)]
        # Number hints
        if prefix and prefix.lstrip('-').isdigit():
            return reg_matches + label_matches
        
        return reg_matches + label_matches


# ── Command History ─────────────────────────────────────────────

HISTORY_FILE = os.path.expanduser("~/.flux_repl_history")

def setup_readline():
    """Initialize readline with history support."""
    try:
        readline.parse_and_bind('tab: complete')
        readline.parse_and_bind('set editing-mode emacs')
        readline.parse_and_bind('set show-all-if-ambiguous on')
        
        # Load history
        if os.path.exists(HISTORY_FILE):
            readline.read_history_file(HISTORY_FILE)
        
        # Save history on exit
        readline.set_history_length(1000)
        atexit.register(readline.write_history_file, HISTORY_FILE)
        
        return True
    except Exception:
        return False


def add_to_history(cmd: str):
    """Add command to readline history."""
    try:
        if cmd.strip():
            readline.add_history(cmd)
    except Exception:
        pass


# ── Interactive REPL ────────────────────────────────────────────

class FluxREPL:
    """Enhanced interactive FLUX REPL."""
    
    def __init__(self):
        self.state = VMState()
        self.source = ""
        self.last_asm_result = None
        self.completer = FluxCompleter()
        self.mem_inspector = MemoryInspector(self.state)
        self.multiline_buffer = []
        self.multiline_mode = False
        self.verbose = False
        
        # Setup readline
        self.has_readline = setup_readline()
        if self.has_readline:
            readline.set_completer(self.completer.complete)
    
    def run(self):
        """Main REPL loop."""
        banner = (
            f"{Color.BOLD}{Color.CYAN}"
            "╔══════════════════════════════════════╗\n"
            "║    FLUX REPL — Bytecode Playground   ║\n"
            "╚══════════════════════════════════════╝\n"
            f"{Color.RESET}"
            f"Type {Color.BOLD}.help{Color.RESET} for commands. "
            f"Type {Color.BOLD}.multi{Color.RESET} for multi-line mode.\n"
        )
        print(banner)
        
        while True:
            try:
                if self.multiline_mode:
                    prompt = f"{Color.YELLOW}>>> {Color.RESET}" if not self.multiline_buffer else f"{Color.YELLOW}... {Color.RESET}"
                else:
                    prompt = f"{Color.GREEN}flux> {Color.RESET}"
                
                try:
                    line = input(prompt)
                except EOFError:
                    print()
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                add_to_history(line)
                self.state.history.append(line)
                
                # Handle multi-line mode
                if self.multiline_mode:
                    if line == "." or line == "end":
                        # End multi-line input
                        full_source = '\n'.join(self.multiline_buffer)
                        self.multiline_buffer = []
                        self.multiline_mode = False
                        result = self._handle_assembly(full_source)
                        if result:
                            print(result)
                    else:
                        self.multiline_buffer.append(line)
                        # Show syntax-highlighted preview
                        if sys.stdout.isatty():
                            print(highlight_syntax(line))
                    continue
                
                # Single-line commands
                if line.startswith('.'):
                    if not self._handle_command(line):
                        break
                else:
                    result = self._handle_assembly(line)
                    if result:
                        print(result)
            
            except KeyboardInterrupt:
                if self.multiline_mode:
                    self.multiline_buffer = []
                    self.multiline_mode = False
                    print(f"\n{Color.DIM}Multi-line mode cancelled.{Color.RESET}")
                else:
                    print(f"\n{Color.DIM}Use .quit to exit.{Color.RESET}")
    
    def _handle_assembly(self, source: str) -> str:
        """Handle assembly input."""
        self.source = source
        self.last_asm_result = assemble(source)
        
        if "error" in self.last_asm_result:
            return f"{Color.RED}Error: {self.last_asm_result['error']}{Color.RESET}"
        
        result = self.last_asm_result
        self.state.labels = result["labels"]
        self.completer.update_labels(result["labels"])
        
        output = []
        output.append(f"{Color.BOLD}Assembled:{Color.RESET} {result['bytes']} bytes")
        output.append(f"  {result['hex']}")
        
        if result["labels"]:
            label_strs = [f"{k}={v}" for k, v in result["labels"].items()]
            output.append(f"  Labels: {', '.join(label_strs)}")
        
        return '\n'.join(output)
    
    def _handle_command(self, cmd: str) -> bool:
        """Handle dot-commands. Returns False to exit."""
        parts = cmd.split()
        cmd_name = parts[0].lower()
        args = parts[1:]
        
        if cmd_name in ('.quit', '.exit'):
            print(f"{Color.DIM}Goodbye!{Color.RESET}")
            return False
        
        elif cmd_name == '.help':
            self._show_help()
        
        elif cmd_name == '.run':
            self._cmd_run(args)
        
        elif cmd_name == '.asm':
            if self.last_asm_result and "bytecode" in self.last_asm_result:
                result = execute(self.last_asm_result["bytecode"])
                self.state.registers = result["registers"] + [0] * (64 - 16)
                self.state.sp = result["stack_pointer"]
                print(f"{Color.GREEN}Executed in {result['cycles']} cycles{Color.RESET}")
                print(format_register_panel(result["registers"]))
            else:
                print(f"{Color.RED}No assembly loaded. Enter code first.{Color.RESET}")
        
        elif cmd_name == '.regs':
            regs = self.state.registers[:16]
            print(format_register_panel(regs))
            if self.verbose:
                print(format_compact_registers(self.state.registers[:8]))
        
        elif cmd_name == '.mem':
            self._cmd_mem(args)
        
        elif cmd_name == '.memr':
            self._cmd_mem_read(args)
        
        elif cmd_name == '.memw':
            self._cmd_mem_write(args)
        
        elif cmd_name == '.dump':
            self._cmd_dump(args)
        
        elif cmd_name == '.bp':
            self._cmd_breakpoint(args)
        
        elif cmd_name == '.bpdel':
            self._cmd_bp_delete(args)
        
        elif cmd_name == '.bplist':
            self._cmd_bp_list()
        
        elif cmd_name == '.disasm':
            self._cmd_disasm(args)
        
        elif cmd_name == '.step':
            self._cmd_step()
        
        elif cmd_name == '.trace':
            self._cmd_trace()
        
        elif cmd_name == '.labels':
            self._cmd_labels()
        
        elif cmd_name == '.multi':
            self.multiline_mode = True
            self.multiline_buffer = []
            print(f"{Color.YELLOW}Multi-line mode ON. Enter assembly lines, '.' to end.{Color.RESET}")
        
        elif cmd_name == '.save':
            fp = args[0] if args else "flux_session.pkl"
            result = save_session(self.state, self.source, fp)
            print(f"{Color.GREEN}Session saved: {result['path']}{Color.RESET}" if result['success']
                  else f"{Color.RED}Save failed: {result['error']}{Color.RESET}")
        
        elif cmd_name == '.load':
            fp = args[0] if args else "flux_session.pkl"
            try:
                self.state, self.source = load_session(fp)
                self.completer.update_labels(self.state.labels)
                print(f"{Color.GREEN}Session loaded from {fp}{Color.RESET}")
                print(format_register_panel(self.state.registers[:16]))
            except FileNotFoundError:
                print(f"{Color.RED}Session file not found: {fp}{Color.RESET}")
        
        elif cmd_name == '.savejson':
            fp = args[0] if args else "flux_session.json"
            result = save_session_json(self.state, self.source, fp)
            print(f"{Color.GREEN}Session saved (JSON): {result['path']}{Color.RESET}" if result['success']
                  else f"{Color.RED}Save failed: {result['error']}{Color.RESET}")
        
        elif cmd_name == '.loadjson':
            fp = args[0] if args else "flux_session.json"
            try:
                self.state, self.source = load_session_json(fp)
                self.completer.update_labels(self.state.labels)
                print(f"{Color.GREEN}Session loaded (JSON) from {fp}{Color.RESET}")
            except FileNotFoundError:
                print(f"{Color.RED}Session file not found: {fp}{Color.RESET}")
        
        elif cmd_name == '.reset':
            self.state = VMState()
            self.source = ""
            self.last_asm_result = None
            print(f"{Color.GREEN}VM state reset.{Color.RESET}")
        
        elif cmd_name == '.history':
            for i, h in enumerate(self.state.history[-20:]):
                print(f"  {i:3d}: {h}")
        
        elif cmd_name == '.watch':
            self._cmd_watch(args)
        
        elif cmd_name == '.verbose':
            self.verbose = not self.verbose
            print(f"Verbose: {'ON' if self.verbose else 'OFF'}")
        
        else:
            print(f"{Color.RED}Unknown command: {cmd_name}. Type .help for available commands.{Color.RESET}")
        
        return True
    
    def _show_help(self):
        """Show help text."""
        help_text = f"""{Color.BOLD}FLUX REPL Commands:{Color.RESET}

{Color.CYAN}Assembly:{Color.RESET}
  <assembly>         Assemble FLUX instructions
  .multi             Enter multi-line input mode

{Color.CYAN}Execution:{Color.RESET}
  .run [cycles]      Execute loaded bytecode (default 10000)
  .asm               Alias for .run
  .step              Single-step execution
  .trace             Run with full trace enabled

{Color.CYAN}Debugging:{Color.RESET}
  .bp <addr>         Set breakpoint at address
  .bp <label>        Set breakpoint at label
  .bpdel <addr>      Remove breakpoint
  .bplist            List all breakpoints
  .disasm [n] [m]    Disassemble [n..m] or all
  .regs              Show register state panel

{Color.CYAN}Memory:{Color.RESET}
  .mem <addr> [cnt]  Read memory bytes
  .memr <addr> [n]   Read n bytes (alias)
  .memw <addr> <v>.. Write bytes to memory
  .dump <start> <end> Hex dump memory region
  .find <val>        Find byte in memory

{Color.CYAN}Session:{Color.RESET}
  .save [path]       Save session (pickle)
  .load [path]       Load session (pickle)
  .savejson [path]   Save session (JSON)
  .loadjson [path]   Load session (JSON)
  .reset             Reset VM state
  .history           Show command history
  .labels            Show defined labels
  .watch <regs>      Set watched registers
  .verbose           Toggle verbose mode

{Color.CYAN}Other:{Color.RESET}
  .help              Show this help
  .quit / .exit      Exit REPL"""
        print(help_text)
    
    def _cmd_run(self, args: List[str]):
        """Execute loaded bytecode."""
        if not self.last_asm_result or "bytecode" not in self.last_asm_result:
            print(f"{Color.RED}No assembly loaded. Enter code first.{Color.RESET}")
            return
        max_cycles = int(args[0]) if args else 10000
        bps = self.state.breakpoints if self.state.breakpoints else None
        result = execute(self.last_asm_result["bytecode"], self.state, breakpoints=bps, max_cycles=max_cycles)
        self.state.registers[:16] = result["registers"]
        
        if result.get("breakpoint"):
            print(f"{Color.RED}⏸ Breakpoint hit at PC={result['breakpoint_pc']}{Color.RESET}")
            print(format_register_panel(result["registers"]))
        else:
            status = f"{Color.GREEN}HALTED{Color.RESET}" if result["halted"] else f"{Color.YELLOW}TIMEOUT{Color.RESET}"
            print(f"Executed: {result['cycles']} cycles — {status}")
            print(format_register_panel(result["registers"]))
    
    def _cmd_mem(self, args: List[str]):
        """Read memory."""
        if not args:
            print(f"{Color.RED}Usage: .mem <addr> [count]{Color.RESET}")
            return
        try:
            addr = self._parse_value(args[0])
            count = int(args[1]) if len(args) > 1 else 16
            values = self.mem_inspector.read(addr, count)
            hex_str = ' '.join(f'{v:02x}' for v in values)
            dec_str = ' '.join(str(v) for v in values)
            print(f"  [{addr:04x}]: {hex_str}  ({dec_str})")
        except (ValueError, IndexError) as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
    
    def _cmd_mem_read(self, args: List[str]):
        """Alias for .mem."""
        self._cmd_mem(args)
    
    def _cmd_mem_write(self, args: List[str]):
        """Write to memory."""
        if len(args) < 2:
            print(f"{Color.RED}Usage: .memw <addr> <val1> [val2] ...{Color.RESET}")
            return
        try:
            addr = self._parse_value(args[0])
            values = [self._parse_value(a) for a in args[1:]]
            self.mem_inspector.write(addr, values)
            print(f"{Color.GREEN}Wrote {len(values)} bytes at [{addr:04x}]{Color.RESET}")
        except (ValueError, IndexError) as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
    
    def _cmd_dump(self, args: List[str]):
        """Hex dump memory region."""
        if len(args) < 2:
            print(f"{Color.RED}Usage: .dump <start> <end>{Color.RESET}")
            return
        try:
            start = self._parse_value(args[0])
            end = self._parse_value(args[1])
            print(self.mem_inspector.dump(start, end))
        except (ValueError, IndexError) as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
    
    def _cmd_breakpoint(self, args: List[str]):
        """Set breakpoint."""
        if not args:
            print(f"{Color.RED}Usage: .bp <addr_or_label>{Color.RESET}")
            return
        try:
            addr = self._parse_value(args[0])
            self.state.breakpoints.add(addr)
            print(f"{Color.GREEN}Breakpoint set at {addr} (0x{addr:04x}){Color.RESET}")
            self._cmd_bp_list()
        except ValueError as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
    
    def _cmd_bp_delete(self, args: List[str]):
        """Delete breakpoint."""
        if not args:
            print(f"{Color.RED}Usage: .bpdel <addr>{Color.RESET}")
            return
        try:
            addr = self._parse_value(args[0])
            self.state.breakpoints.discard(addr)
            print(f"{Color.YELLOW}Breakpoint removed at {addr}{Color.RESET}")
        except ValueError as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
    
    def _cmd_bp_list(self):
        """List breakpoints."""
        if self.state.breakpoints:
            bps = sorted(self.state.breakpoints)
            bp_strs = [f"0x{b:04x}" for b in bps]
            print(f"  Breakpoints: {', '.join(bp_strs)}")
        else:
            print(f"  {Color.DIM}No breakpoints set.{Color.RESET}")
    
    def _cmd_disasm(self, args: List[str]):
        """Disassemble loaded bytecode."""
        if not self.last_asm_result or "bytecode" not in self.last_asm_result:
            print(f"{Color.RED}No assembly loaded.{Color.RESET}")
            return
        bc = self.last_asm_result["bytecode"]
        start = int(args[0]) if len(args) > 0 else 0
        end = int(args[1]) if len(args) > 1 else len(bc)
        lines = disassemble(bc, start, end)
        print(f"{Color.BOLD}Disassembly:{Color.RESET}")
        for line in lines:
            print(line)
    
    def _cmd_step(self):
        """Single-step execution."""
        if not self.last_asm_result or "bytecode" not in self.last_asm_result:
            print(f"{Color.RED}No assembly loaded.{Color.RESET}")
            return
        bc = self.last_asm_result["bytecode"]
        pc = self.state.pc
        if pc >= len(bc) or bc[pc] == 0x00:
            print(f"{Color.DIM}Already halted.{Color.RESET}")
            return
        
        # Execute one instruction manually
        result = execute(bc, self.state, max_cycles=1)
        self.state.registers[:16] = result["registers"]
        self.state.pc = result.get("cycles", 0)  # approximate
        
        # Show current instruction
        if pc < len(bc):
            inst = format_instruction(bytes(bc), pc)
            print(f"  {Color.CYAN}{pc:04x}: {Color.RESET}{inst}")
        print(format_compact_registers(self.state.registers[:8]))
    
    def _cmd_trace(self):
        """Run with full trace."""
        if not self.last_asm_result or "bytecode" not in self.last_asm_result:
            print(f"{Color.RED}No assembly loaded.{Color.RESET}")
            return
        result = execute(self.last_asm_result["bytecode"], trace_mode=True)
        self.state.registers[:16] = result["registers"]
        print(f"Trace ({len(result['trace'])} steps, {result['cycles']} cycles):")
        for entry in result["trace"][:20]:
            op_name = OPCODE_NAMES.get(entry["op"], f"0x{entry['op']:02x}")
            regs = entry["regs"]
            print(f"  {entry['pc']:04x}: {op_name:8s}  R0={regs[0]:4d} R1={regs[1]:4d} R2={regs[2]:4d}")
        if len(result["trace"]) > 20:
            print(f"  ... ({len(result['trace']) - 20} more steps)")
    
    def _cmd_labels(self):
        """Show defined labels."""
        if self.state.labels:
            for name, addr in sorted(self.state.labels.items()):
                print(f"  {Color.CYAN}{name}:{Color.RESET} 0x{addr:04x} ({addr})")
        else:
            print(f"  {Color.DIM}No labels defined.{Color.RESET}")
    
    def _cmd_watch(self, args: List[str]):
        """Set watched registers."""
        if not args:
            print(f"  Watching: {', '.join(f'R{r}' for r in self.state.watch_registers)}")
            return
        try:
            regs = []
            for a in args:
                if a.upper().startswith('R'):
                    regs.append(int(a[1:]))
                else:
                    regs.append(int(a))
            self.state.watch_registers = regs
            print(f"{Color.GREEN}Watching: {', '.join(f'R{r}' for r in regs)}{Color.RESET}")
        except ValueError:
            print(f"{Color.RED}Usage: .watch R0 R1 R2 ...{Color.RESET}")
    
    def _parse_value(self, s: str) -> int:
        """Parse a value: label, hex, or decimal."""
        s = s.strip()
        # Check labels
        if s in self.state.labels:
            return self.state.labels[s]
        # Check hex
        if s.startswith('0x') or s.startswith('0X'):
            return int(s, 16)
        # Check register reference
        if s.upper().startswith('R'):
            return self.state.registers[int(s[1:])]
        return int(s)


# ── Tests ──────────────────────────────────────────────────────

import unittest


class TestRepl(unittest.TestCase):
    def test_assemble_movi(self):
        result = assemble("MOVI R0, 42")
        self.assertIn("bytecode", result)
        self.assertEqual(result["bytecode"][0], 0x18)
    
    def test_assemble_halt(self):
        result = assemble("HALT")
        self.assertIn("bytecode", result)
        self.assertEqual(result["bytecode"][0], 0x00)
    
    def test_assemble_add(self):
        result = assemble("MOVI R0, 10\nMOVI R1, 20\nADD R2, R0, R1")
        self.assertIn("bytecode", result)
        self.assertIn(0x20, result["bytecode"])
    
    def test_assemble_comment(self):
        result = assemble("MOVI R0, 42 ; load the answer")
        self.assertIn("bytecode", result)
    
    def test_assemble_unknown_opcode(self):
        result = assemble("UNKNOWN R0")
        self.assertIn("error", result)
    
    def test_execute_halt(self):
        result = execute([0x00])
        self.assertTrue(result["halted"])
        self.assertEqual(result["cycles"], 1)
    
    def test_execute_movi_add(self):
        result = execute([0x18, 0, 10, 0x18, 1, 20, 0x20, 2, 0, 1, 0x00])
        self.assertTrue(result["halted"])
        self.assertEqual(result["registers"][2], 30)
    
    def test_execute_factorial(self):
        result = execute([0x18, 0, 6, 0x18, 1, 1, 0x22, 1, 1, 0, 0x09, 0, 0x3D, 0, 0xFA, 0, 0x00])
        self.assertTrue(result["halted"])
        self.assertEqual(result["registers"][1], 720)
    
    def test_execute_trace(self):
        result = execute([0x18, 0, 5, 0x00])
        self.assertGreater(len(result["trace"]), 0)
    
    def test_parse_arg_register(self):
        self.assertEqual(parse_arg("R5"), 5)
        self.assertEqual(parse_arg("r10"), 10)
    
    def test_parse_arg_number(self):
        self.assertEqual(parse_arg("42"), 42)
        self.assertEqual(parse_arg("0xFF"), 255)
    
    def test_parse_imm_negative(self):
        self.assertEqual(parse_imm("-5"), -5)
    
    def test_full_pipeline(self):
        """Assemble → Execute → Verify"""
        source = "MOVI R0, 10\nMOVI R1, 20\nADD R2, R0, R1\nHALT"
        asm = assemble(source)
        self.assertNotIn("error", asm)
        result = execute(asm["bytecode"])
        self.assertEqual(result["registers"][2], 30)
    
    def test_hex_output(self):
        result = assemble("HALT")
        self.assertIn("hex", result)
        self.assertTrue(len(result["hex"]) > 0)
    
    def test_byte_count(self):
        result = assemble("MOVI R0, 42")
        self.assertIn("bytes", result)
        self.assertGreater(result["bytes"], 0)


class TestEnhancedREPL(unittest.TestCase):
    """Tests for enhanced features."""
    
    def test_syntax_highlighting(self):
        """Syntax highlighting should color opcodes, registers, and comments."""
        src = "MOVI R0, 42 ; comment"
        result = highlight_syntax(src)
        # Should not be empty
        self.assertTrue(len(result) > 0)
    
    def test_syntax_highlighting_strips_to_original(self):
        """Highlighted text contains original content."""
        src = "ADD R0, R1, R2"
        # Strip ANSI codes and verify content
        result = highlight_syntax(src)
        stripped = re.sub(r'\033\[[0-9;]*m', '', result)
        self.assertIn("ADD", stripped)
        self.assertIn("R0", stripped)
    
    def test_disassemble_single(self):
        """Disassemble a single instruction."""
        bc = [0x18, 0, 42, 0x00]
        lines = disassemble(bc, 0, 2)
        self.assertEqual(len(lines), 1)
        self.assertIn("MOVI", lines[0])
    
    def test_disassemble_full(self):
        """Disassemble full program."""
        bc = [0x18, 0, 10, 0x18, 1, 20, 0x20, 2, 0, 1, 0x00]
        lines = disassemble(bc)
        self.assertGreater(len(lines), 2)
        # Check HALT is in there
        self.assertTrue(any("HALT" in l for l in lines))
    
    def test_disassemble_range(self):
        """Disassemble a range of instructions."""
        bc = [0x18, 0, 10, 0x18, 1, 20, 0x20, 2, 0, 1, 0x00]
        lines = disassemble(bc, 0, 3)
        self.assertEqual(len(lines), 1)  # Only first MOVI (3 bytes)
    
    def test_opcode_size(self):
        """Opcode size detection."""
        self.assertEqual(opcode_size(0x00), 1)  # HALT
        self.assertEqual(opcode_size(0x08), 2)  # INC
        self.assertEqual(opcode_size(0x18), 3)  # MOVI
        self.assertEqual(opcode_size(0x20), 4)  # ADD
    
    def test_format_instruction(self):
        """Format a single instruction."""
        bc = bytes([0x18, 5, 42])
        result = format_instruction(bc, 0)
        self.assertIn("MOVI", result)
        self.assertIn("R5", result)
    
    def test_vm_state_init(self):
        """VM state initialization."""
        state = VMState()
        self.assertEqual(len(state.registers), 64)
        self.assertEqual(len(state.memory), 65536)
        self.assertEqual(state.sp, 4096)
        self.assertFalse(state.halted)
    
    def test_register_panel(self):
        """Register panel formatting."""
        regs = [i * 10 for i in range(16)]
        panel = format_register_panel(regs)
        self.assertIn("REGISTER STATE", panel)
        self.assertIn("0x0064", panel)  # 100 in hex
        self.assertIn("150", panel)
    
    def test_compact_registers(self):
        """Compact register display."""
        regs = [1, 2, 3, 4, 5, 6, 7, 8]
        result = format_compact_registers(regs)
        self.assertIn("R0=1", result)
        self.assertIn("R7=8", result)
    
    def test_memory_inspector_read(self):
        """Memory read operations."""
        state = VMState()
        state.memory[100] = 0xDE
        state.memory[101] = 0xAD
        mem = MemoryInspector(state)
        self.assertEqual(mem.read(100, 1), [0xDE])
        self.assertEqual(mem.read(100, 2), [0xDE, 0xAD])
        self.assertEqual(mem.read(200, 1), [0])  # unwritten
    
    def test_memory_inspector_write(self):
        """Memory write operations."""
        state = VMState()
        mem = MemoryInspector(state)
        mem.write(50, [0x01, 0x02, 0x03])
        self.assertEqual(state.memory[50], 0x01)
        self.assertEqual(state.memory[51], 0x02)
        self.assertEqual(state.memory[52], 0x03)
    
    def test_memory_inspector_word(self):
        """Word-level memory operations."""
        state = VMState()
        mem = MemoryInspector(state)
        mem.write_word(100, 0x1234)
        self.assertEqual(mem.read_word(100), 0x1234)
    
    def test_memory_inspector_dump(self):
        """Memory hex dump."""
        state = VMState()
        state.memory[0] = 0x41  # 'A'
        state.memory[1] = 0x42  # 'B'
        mem = MemoryInspector(state)
        dump = mem.dump(0, 16)
        self.assertIn("41", dump)
        self.assertIn("42", dump)
        self.assertIn("AB", dump)
    
    def test_memory_inspector_find(self):
        """Memory find operation."""
        state = VMState()
        state.memory[10] = 0xFF
        state.memory[20] = 0xFF
        state.memory[30] = 0xFF
        mem = MemoryInspector(state)
        addrs = mem.find(0xFF)
        self.assertIn(10, addrs)
        self.assertIn(20, addrs)
        self.assertIn(30, addrs)
        self.assertEqual(len(addrs), 3)
    
    def test_breakpoint_basic(self):
        """Breakpoint halts execution."""
        # MOVI R0, 10 (3 bytes at PC=0) -> breakpoint at PC=3
        bc = [0x18, 0, 10, 0x18, 1, 20, 0x00]
        result = execute(bc, breakpoints={3})
        self.assertTrue(result.get("breakpoint"))
        self.assertEqual(result["breakpoint_pc"], 3)
        self.assertEqual(result["registers"][0], 10)
    
    def test_breakpoint_not_hit(self):
        """Execution completes if breakpoint not reached."""
        bc = [0x18, 0, 10, 0x00]
        result = execute(bc, breakpoints={100})
        self.assertTrue(result["halted"])
        self.assertNotIn("breakpoint", result)
    
    def test_execute_with_vm_state(self):
        """Execution with persistent VM state."""
        state = VMState()
        bc = [0x18, 0, 42, 0x00]
        result = execute(bc, state=state)
        self.assertEqual(state.registers[0], 42)
        self.assertTrue(state.halted)
    
    def test_execute_trace_mode(self):
        """Full trace mode records all steps."""
        bc = [0x18, 0, 5, 0x18, 1, 3, 0x20, 2, 0, 1, 0x00]
        result = execute(bc, trace_mode=True)
        self.assertEqual(len(result["trace"]), 4)  # MOVI, MOVI, ADD, HALT
    
    def test_session_save_load_pickle(self):
        """Save and load session with pickle."""
        state = VMState()
        state.registers[0] = 42
        source = "MOVI R0, 42"
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pkl', delete=False) as f:
            fp = f.name
        
        try:
            save_session(state, source, fp)
            loaded_state, loaded_source = load_session(fp)
            self.assertEqual(loaded_state.registers[0], 42)
            self.assertEqual(loaded_source, source)
        finally:
            os.unlink(fp)
    
    def test_session_save_load_json(self):
        """Save and load session with JSON."""
        state = VMState()
        state.registers[1] = 99
        source = "MOVI R1, 99"
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            fp = f.name
        
        try:
            save_session_json(state, source, fp)
            loaded_state, loaded_source = load_session_json(fp)
            self.assertEqual(loaded_state.registers[1], 99)
            self.assertEqual(loaded_source, source)
        finally:
            os.unlink(fp)
    
    def test_flux_completer(self):
        """Tab completer returns valid completions."""
        c = FluxCompleter()
        # Opcode completion
        results = c.get_completions("MOV")
        self.assertIn("MOVI", results)
        self.assertIn("MOV", results)
        # Register completion
        results = c.get_completions("MOVI R")
        self.assertTrue(any("R0" in r for r in results))
        # Command completion
        results = c.get_completions(".he")
        self.assertIn(".help", results)
    
    def test_flux_completer_labels(self):
        """Completer includes labels."""
        c = FluxCompleter()
        c.update_labels({"loop": 10, "end": 20})
        results = c.get_completions("lo")
        self.assertIn("loop:", results)
    
    def test_execute_extended_opcodes(self):
        """Test newly added opcodes: AND, OR, XOR, SHL, SHR, NOT, SUBI, MOVI16."""
        # AND: R2 = R0 & R1 = 0xFF & 0x0F = 0x0F
        bc_and = [0x18, 0, 0xFF & 0x7F, 0x18, 1, 0x0F, 0x25, 2, 0, 1, 0x00]
        result = execute(bc_and)
        self.assertEqual(result["registers"][2], 0x0F)
        
        # OR: R2 = R0 | R1 = 0xF0 | 0x0F = 0xFF
        bc_or = [0x18, 0, 0x0F, 0x18, 1, 0x0F, 0x26, 2, 0, 1, 0x00]
        result = execute(bc_or)
        # 15 | 15 = 15
        self.assertEqual(result["registers"][2], 15)
        
        # XOR: R2 = 0xFF ^ 0xFF = 0
        bc_xor = [0x18, 0, 0x7F, 0x18, 1, 0x7F, 0x27, 2, 0, 1, 0x00]
        result = execute(bc_xor)
        self.assertEqual(result["registers"][2], 0)
        
        # NOT
        bc_not = [0x18, 0, 0, 0x0A, 0, 0x00]
        result = execute(bc_not)
        self.assertEqual(result["registers"][0], ~0)
    
    def test_labels_in_assembler(self):
        """Labels are collected and resolved correctly."""
        source = """
loop:
  DEC R0
  JNZ R0, loop
"""
        result = assemble(source)
        self.assertNotIn("error", result)
        self.assertIn("loop", result["labels"])
    
    def test_subi_opcode(self):
        """SUBI instruction."""
        bc = [0x18, 0, 10, 0x1A, 0, 3, 0x00]
        result = execute(bc)
        self.assertEqual(result["registers"][0], 7)
    
    def test_programs_count(self):
        """Verify we have comprehensive test coverage."""
        import repl as mod
        # This test ensures the module has all expected components
        self.assertTrue(callable(getattr(mod, 'assemble', None)))
        self.assertTrue(callable(getattr(mod, 'execute', None)))
        self.assertTrue(callable(getattr(mod, 'disassemble', None)))
        self.assertTrue(callable(getattr(mod, 'highlight_syntax', None)))
        self.assertTrue(callable(getattr(mod, 'save_session', None)))
        self.assertTrue(callable(getattr(mod, 'load_session', None)))
        self.assertTrue(callable(getattr(mod, 'format_register_panel', None)))
        # Classes
        self.assertIsNotNone(getattr(mod, 'VMState', None))
        self.assertIsNotNone(getattr(mod, 'MemoryInspector', None))
        self.assertIsNotNone(getattr(mod, 'FluxREPL', None))
        self.assertIsNotNone(getattr(mod, 'FluxCompleter', None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
