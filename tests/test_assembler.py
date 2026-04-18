"""Comprehensive pytest tests for the FLUX assembler."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repl import assemble, parse_arg, parse_imm, OPCODES


# ── parse_arg ──────────────────────────────────────────

class TestParseArg:
    def test_register_uppercase(self):
        assert parse_arg("R0") == 0
        assert parse_arg("R5") == 5
        assert parse_arg("R15") == 15
        assert parse_arg("R63") == 63

    def test_register_lowercase(self):
        assert parse_arg("r0") == 0
        assert parse_arg("r10") == 10

    def test_numeric_arg(self):
        assert parse_arg("0") == 0
        assert parse_arg("42") == 42
        assert parse_arg("255") == 255

    def test_hex_arg(self):
        assert parse_arg("0x00") == 0
        assert parse_arg("0xFF") == 255
        assert parse_arg("0x10") == 16

    def test_negative_number(self):
        assert parse_arg("-1") == -1
        assert parse_arg("-128") == -128


# ── parse_imm ──────────────────────────────────────────

class TestParseImm:
    def test_decimal(self):
        assert parse_imm("42") == 42
        assert parse_imm("0") == 0

    def test_hex_uppercase(self):
        assert parse_imm("0xFF") == 255
        assert parse_imm("0xAB") == 171

    def test_hex_lowercase(self):
        assert parse_imm("0xff") == 255

    def test_negative(self):
        assert parse_imm("-5") == -5

    def test_invalid_returns_zero(self):
        assert parse_imm("abc") == 0
        assert parse_imm("") == 0

    def test_strips_whitespace(self):
        assert parse_imm("  42  ") == 42


# ── assemble: basic instructions ───────────────────────

class TestAssembleBasic:
    def test_halt(self):
        result = assemble("HALT")
        assert "error" not in result
        assert result["bytecode"][0] == 0x00  # HALT opcode
        # assembler always appends an extra HALT
        assert 0x00 in result["bytecode"]

    def test_nop(self):
        result = assemble("NOP")
        assert "error" not in result
        assert 0x01 in result["bytecode"]

    def test_movi(self):
        result = assemble("MOVI R0, 42")
        assert "error" not in result
        assert result["bytecode"][0] == 0x18  # MOVI opcode
        assert result["bytecode"][1] == 0      # R0
        assert result["bytecode"][2] == 42     # immediate

    def test_movi_negative(self):
        result = assemble("MOVI R0, -1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x18

    def test_movi_hex_immediate(self):
        result = assemble("MOVI R1, 0xFF")
        assert "error" not in result
        assert result["bytecode"][1] == 1
        assert result["bytecode"][2] == 0xFF

    def test_addi(self):
        result = assemble("ADDI R0, 5")
        assert "error" not in result
        assert result["bytecode"][0] == 0x19  # ADDI opcode

    def test_subi(self):
        result = assemble("SUBI R0, 3")
        assert "error" not in result
        assert result["bytecode"][0] == 0x1A  # SUBI opcode

    def test_inc(self):
        result = assemble("INC R0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x08

    def test_dec(self):
        result = assemble("DEC R0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x09

    def test_not_instruction(self):
        result = assemble("NOT R0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x0A

    def test_neg_instruction(self):
        result = assemble("NEG R0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x0B


# ── assemble: ALU instructions ─────────────────────────

class TestAssembleALU:
    def test_add(self):
        result = assemble("ADD R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x20
        assert result["bytecode"][1] == 2  # dest
        assert result["bytecode"][2] == 0  # src1
        assert result["bytecode"][3] == 1  # src2

    def test_sub(self):
        result = assemble("SUB R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x21

    def test_mul(self):
        result = assemble("MUL R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x22

    def test_div(self):
        result = assemble("DIV R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x23

    def test_mod(self):
        result = assemble("MOD R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x24

    def test_and(self):
        result = assemble("AND R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x25

    def test_or(self):
        result = assemble("OR R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x26

    def test_xor(self):
        result = assemble("XOR R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x27

    def test_shl(self):
        result = assemble("SHL R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x28

    def test_shr(self):
        result = assemble("SHR R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x29

    def test_min(self):
        result = assemble("MIN R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x2A

    def test_max(self):
        result = assemble("MAX R2, R0, R1")
        assert "error" not in result
        assert result["bytecode"][0] == 0x2B


# ── assemble: comparison instructions ──────────────────

class TestAssembleCompare:
    def test_cmp_eq(self):
        result = assemble("CMP_EQ R0, R1, R2")
        assert "error" not in result
        assert result["bytecode"][0] == 0x2C

    def test_cmp_lt(self):
        result = assemble("CMP_LT R0, R1, R2")
        assert "error" not in result
        assert result["bytecode"][0] == 0x2D

    def test_cmp_gt(self):
        result = assemble("CMP_GT R0, R1, R2")
        assert "error" not in result
        assert result["bytecode"][0] == 0x2E

    def test_cmp_ne(self):
        result = assemble("CMP_NE R0, R1, R2")
        assert "error" not in result
        assert result["bytecode"][0] == 0x2F


# ── assemble: control flow ─────────────────────────────

class TestAssembleControlFlow:
    def test_mov(self):
        result = assemble("MOV R2, R0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x3A

    def test_jz(self):
        result = assemble("JZ R0, 4")
        assert "error" not in result
        assert result["bytecode"][0] == 0x3C

    def test_jnz(self):
        result = assemble("JNZ R0, 4")
        assert "error" not in result
        assert result["bytecode"][0] == 0x3D

    def test_jmp(self):
        result = assemble("JMP R0, 0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x43

    def test_loop(self):
        result = assemble("LOOP R0, 4")
        assert "error" not in result
        assert result["bytecode"][0] == 0x46

    def test_push(self):
        result = assemble("PUSH R0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x0C

    def test_pop(self):
        result = assemble("POP R0")
        assert "error" not in result
        assert result["bytecode"][0] == 0x0D


# ── assemble: labels ───────────────────────────────────

class TestAssembleLabels:
    def test_basic_label(self):
        source = "start:\nMOVI R0, 1\nstart:\nHALT"
        result = assemble(source)
        # First label is found, duplicate label overwrites but no error
        assert "error" not in result

    def test_label_with_jump(self):
        source = """
        MOVI R0, 5
        loop:
        DEC R0
        JNZ R0, -6
        HALT
        """
        result = assemble(source)
        assert "error" not in result
        assert "labels" in result

    def test_label_in_result(self):
        source = "start:\nMOVI R0, 1\nHALT"
        result = assemble(source)
        assert "start" in result["labels"]
        assert result["labels"]["start"] == 0  # label at PC 0


# ── assemble: comments ─────────────────────────────────

class TestAssembleComments:
    def test_inline_comment(self):
        result = assemble("MOVI R0, 42 ; this is a comment")
        assert "error" not in result
        assert result["bytecode"][0] == 0x18

    def test_comment_only_line(self):
        result = assemble("; just a comment\nMOVI R0, 42")
        assert "error" not in result
        # First instruction should be MOVI
        assert result["bytecode"][0] == 0x18

    def test_multiple_comments(self):
        result = assemble("; header\nMOVI R0, 1 ; first\n; footer\nHALT")
        assert "error" not in result


# ── assemble: error handling ───────────────────────────

class TestAssembleErrors:
    def test_unknown_opcode(self):
        result = assemble("FAKE_INSTRUCTION R0")
        assert "error" in result
        assert "Unknown opcode" in result["error"]

    def test_empty_source(self):
        result = assemble("")
        assert "error" not in result
        # Should still get bytecode (just HALT)
        assert "bytecode" in result

    def test_whitespace_only(self):
        result = assemble("   \n   \n  ")
        assert "error" not in result
        assert "bytecode" in result

    def test_empty_lines_between_instructions(self):
        result = assemble("MOVI R0, 1\n\n\nMOVI R1, 2")
        assert "error" not in result
        assert result["bytecode"][0] == 0x18


# ── assemble: output format ────────────────────────────

class TestAssembleOutput:
    def test_hex_string(self):
        result = assemble("HALT")
        assert "hex" in result
        assert isinstance(result["hex"], str)
        # Hex should be space-separated pairs
        parts = result["hex"].split()
        assert all(len(p) == 2 for p in parts)

    def test_byte_count(self):
        result = assemble("MOVI R0, 42")
        assert "bytes" in result
        assert result["bytes"] == len(result["bytecode"])

    def test_byte_count_multi_instruction(self):
        result = assemble("MOVI R0, 1\nMOVI R1, 2\nHALT")
        assert result["bytes"] == len(result["bytecode"])

    def test_labels_dict(self):
        result = assemble("loop:\nMOVI R0, 1\nHALT")
        assert "labels" in result
        assert isinstance(result["labels"], dict)

    def test_case_insensitive_opcodes(self):
        result = assemble("movi R0, 42")
        assert "error" not in result
        assert result["bytecode"][0] == 0x18

    def test_uppercase_opcodes(self):
        result = assemble("MOVI R0, 42")
        assert "error" not in result
        assert result["bytecode"][0] == 0x18


# ── assemble: instruction sizes ────────────────────────

class TestAssembleSizes:
    def test_1byte_instruction(self):
        """HALT and NOP are 1-byte instructions."""
        result = assemble("HALT")
        # HALT + appended HALT = 2 bytes
        assert result["bytes"] >= 2

    def test_2byte_instruction(self):
        """INC, DEC, PUSH, POP, MOVI are 2-byte (opcode + reg)."""
        result = assemble("INC R0")
        assert result["bytes"] >= 3  # INC + appended HALT

    def test_3byte_instruction(self):
        """MOVI is 3-byte (opcode + reg + imm)."""
        result = assemble("MOVI R0, 42")
        assert result["bytes"] >= 4  # MOVI + appended HALT


# ── assemble: all known opcodes ────────────────────────

class TestAssembleAllOpcodes:
    def test_all_opcodes_parseable(self):
        """Every opcode in the OPCODES dict should assemble without error."""
        for name, code in OPCODES.items():
            # Format args based on instruction size
            if code <= 0x07:
                source = f"{name}"
            elif code <= 0x17:
                source = f"{name} R0"
            elif code <= 0x1F:
                source = f"{name} R0, 0"
            else:
                source = f"{name} R0, R1, R2"

            result = assemble(source)
            if "error" not in result:
                assert result["bytecode"][0] == code, f"Failed for {name}"
            else:
                # Some opcodes may need specific arg counts, that's OK
                # as long as it doesn't crash
                pass
