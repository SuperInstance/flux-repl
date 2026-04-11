"""
FLUX REPL — Interactive bytecode playground.

Web interface for writing, assembling, and executing FLUX bytecodes.
Run: python3 -m http.server 8080
"""
import json
import sys
import os

sys.path.insert(0, os.path.expanduser("~/.openclaw/workspace/repos/flux-runtime/src"))

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
        
        # Determine format size
        if opcode <= 0x07:
            size = 1
        elif opcode <= 0x17:
            size = 2
        elif opcode <= 0x1F:
            size = 3
        elif opcode <= 0x4F:
            size = 4
        else:
            size = 1
        
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


def execute(bytecode: list) -> dict:
    """Execute bytecode on a simple VM."""
    regs = [0] * 64
    stack = [0] * 4096
    sp = 4096
    pc = 0
    halted = False
    cycles = 0
    trace = []
    
    bc = bytes(bytecode)
    
    while not halted and pc < len(bc) and cycles < 10000:
        op = bc[pc]
        old_pc = pc
        
        if op == 0x00:  # HALT
            halted = True
            pc += 1
        elif op == 0x01:  # NOP
            pc += 1
        elif op == 0x08:  # INC
            regs[bc[pc+1]] += 1; pc += 2
        elif op == 0x09:  # DEC
            regs[bc[pc+1]] -= 1; pc += 2
        elif op == 0x0C:  # PUSH
            stack[sp-1] = regs[bc[pc+1]]; sp -= 1; pc += 2
        elif op == 0x0D:  # POP
            regs[bc[pc+1]] = stack[sp]; sp += 1; pc += 2
        elif op == 0x18:  # MOVI
            regs[bc[pc+1]] = (bc[pc+2] - 256 if bc[pc+2] > 127 else bc[pc+2]); pc += 3
        elif op == 0x19:  # ADDI
            regs[bc[pc+1]] += (bc[pc+2] - 256 if bc[pc+2] > 127 else bc[pc+2]); pc += 3
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
        
        # Record trace (first 100 steps)
        if cycles <= 100:
            regs_snapshot = regs[:8].copy()  # first 8 registers
            trace.append({"pc": old_pc, "op": op, "regs": regs_snapshot})
    
    return {
        "halted": halted,
        "cycles": cycles,
        "registers": regs[:16],
        "register_names": [f"R{i}" for i in range(16)],
        "stack_pointer": sp,
        "trace": trace,
    }


# ── Tests ──────────────────────────────────────────────

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
        # Check ADD opcode is present
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
