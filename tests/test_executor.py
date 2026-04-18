"""Comprehensive pytest tests for the FLUX executor (VM)."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repl import execute


# ── basic execution ────────────────────────────────────

class TestExecuteBasic:
    def test_halt_only(self):
        result = execute([0x00])
        assert result["halted"] is True
        assert result["cycles"] == 1
        assert result["registers"] == [0] * 16

    def test_nop(self):
        result = execute([0x01, 0x00])
        assert result["halted"] is True
        assert result["cycles"] == 2

    def test_multiple_nops(self):
        result = execute([0x01, 0x01, 0x01, 0x00])
        assert result["halted"] is True
        assert result["cycles"] == 4


# ── MOVI instruction ───────────────────────────────────

class TestExecuteMOVI:
    def test_movi_zero(self):
        result = execute([0x18, 0, 0, 0x00])
        assert result["halted"] is True
        assert result["registers"][0] == 0

    def test_movi_positive(self):
        result = execute([0x18, 0, 42, 0x00])
        assert result["halted"] is True
        assert result["registers"][0] == 42

    def test_movi_large(self):
        result = execute([0x18, 0, 127, 0x00])
        assert result["registers"][0] == 127

    def test_movi_negative(self):
        result = execute([0x18, 0, 200, 0x00])
        # 200 > 127, so signed interpretation: 200 - 256 = -56
        assert result["registers"][0] == -56

    def test_movi_different_registers(self):
        result = execute([0x18, 5, 10, 0x00])
        assert result["registers"][5] == 10
        # Other registers should still be 0
        assert result["registers"][0] == 0
        assert result["registers"][1] == 0

    def test_movi_overwrite(self):
        result = execute([0x18, 0, 10, 0x18, 0, 20, 0x00])
        assert result["registers"][0] == 20  # last write wins


# ── ADDI instruction ───────────────────────────────────

class TestExecuteADDI:
    def test_addi_positive(self):
        result = execute([0x18, 0, 10, 0x19, 0, 5, 0x00])
        assert result["registers"][0] == 15

    def test_addi_negative(self):
        result = execute([0x18, 0, 10, 0x19, 0, 200, 0x00])
        # 200 as signed = -56, so 10 + (-56) = -46
        assert result["registers"][0] == -46

    def test_addi_zero(self):
        result = execute([0x18, 0, 10, 0x19, 0, 0, 0x00])
        assert result["registers"][0] == 10


# ── INC / DEC ──────────────────────────────────────────

class TestExecuteIncDec:
    def test_inc_from_zero(self):
        result = execute([0x08, 0, 0x00])
        assert result["registers"][0] == 1

    def test_inc_multiple(self):
        result = execute([0x08, 0, 0x08, 0, 0x08, 0, 0x00])
        assert result["registers"][0] == 3

    def test_dec_from_zero(self):
        result = execute([0x09, 0, 0x00])
        assert result["registers"][0] == -1

    def test_dec_after_inc(self):
        result = execute([0x08, 0, 0x09, 0, 0x00])
        assert result["registers"][0] == 0

    def test_inc_different_registers(self):
        result = execute([0x08, 0, 0x08, 1, 0x00])
        assert result["registers"][0] == 1
        assert result["registers"][1] == 1


# ── ALU: ADD, SUB, MUL, DIV, MOD ──────────────────────

class TestExecuteALU:
    def test_add(self):
        result = execute([0x18, 0, 10, 0x18, 1, 20, 0x20, 2, 0, 1, 0x00])
        assert result["registers"][2] == 30

    def test_sub(self):
        result = execute([0x18, 0, 20, 0x18, 1, 10, 0x21, 2, 0, 1, 0x00])
        assert result["registers"][2] == 10

    def test_sub_negative(self):
        result = execute([0x18, 0, 10, 0x18, 1, 20, 0x21, 2, 0, 1, 0x00])
        assert result["registers"][2] == -10

    def test_mul(self):
        result = execute([0x18, 0, 6, 0x18, 1, 7, 0x22, 2, 0, 1, 0x00])
        assert result["registers"][2] == 42

    def test_mul_zero(self):
        result = execute([0x18, 0, 0, 0x18, 1, 7, 0x22, 2, 0, 1, 0x00])
        assert result["registers"][2] == 0

    def test_div(self):
        result = execute([0x18, 0, 20, 0x18, 1, 4, 0x23, 2, 0, 1, 0x00])
        assert result["registers"][2] == 5

    def test_div_by_zero(self):
        """Division by zero should not crash; register should remain unchanged."""
        result = execute([0x18, 0, 10, 0x18, 1, 0, 0x18, 2, 99, 0x23, 2, 0, 1, 0x00])
        assert result["halted"] is True
        # R2 should not have been modified (div-by-zero guard)
        assert result["registers"][2] == 99

    def test_mod(self):
        result = execute([0x18, 0, 17, 0x18, 1, 5, 0x24, 2, 0, 1, 0x00])
        assert result["registers"][2] == 2

    def test_mod_by_zero(self):
        """Modulo by zero should not crash."""
        result = execute([0x18, 0, 10, 0x18, 1, 0, 0x18, 2, 99, 0x24, 2, 0, 1, 0x00])
        assert result["halted"] is True
        assert result["registers"][2] == 99


# ── comparison instructions ────────────────────────────

class TestExecuteCompare:
    def test_cmp_eq_true(self):
        result = execute([0x18, 0, 10, 0x18, 1, 10, 0x2C, 2, 0, 1, 0x00])
        assert result["registers"][2] == 1

    def test_cmp_eq_false(self):
        result = execute([0x18, 0, 10, 0x18, 1, 20, 0x2C, 2, 0, 1, 0x00])
        assert result["registers"][2] == 0

    def test_cmp_lt_true(self):
        result = execute([0x18, 0, 5, 0x18, 1, 10, 0x2D, 2, 0, 1, 0x00])
        assert result["registers"][2] == 1

    def test_cmp_lt_false(self):
        result = execute([0x18, 0, 10, 0x18, 1, 5, 0x2D, 2, 0, 1, 0x00])
        assert result["registers"][2] == 0

    def test_cmp_gt_true(self):
        result = execute([0x18, 0, 10, 0x18, 1, 5, 0x2E, 2, 0, 1, 0x00])
        assert result["registers"][2] == 1

    def test_cmp_gt_false(self):
        result = execute([0x18, 0, 5, 0x18, 1, 10, 0x2E, 2, 0, 1, 0x00])
        assert result["registers"][2] == 0

    def test_cmp_ne_true(self):
        result = execute([0x18, 0, 10, 0x18, 1, 20, 0x2F, 2, 0, 1, 0x00])
        assert result["registers"][2] == 1

    def test_cmp_ne_false(self):
        result = execute([0x18, 0, 10, 0x18, 1, 10, 0x2F, 2, 0, 1, 0x00])
        assert result["registers"][2] == 0


# ── MOV instruction ────────────────────────────────────

class TestExecuteMOV:
    def test_mov(self):
        result = execute([0x18, 0, 42, 0x3A, 1, 0, 0, 0x00])
        assert result["registers"][1] == 42
        assert result["registers"][0] == 42  # source unchanged

    def test_mov_chain(self):
        result = execute([0x18, 0, 7, 0x3A, 1, 0, 0, 0x3A, 2, 1, 0, 0x00])
        assert result["registers"][0] == 7
        assert result["registers"][1] == 7
        assert result["registers"][2] == 7


# ── PUSH / POP ─────────────────────────────────────────

class TestExecutePushPop:
    def test_push_pop_roundtrip(self):
        # PUSH R0, then POP R1
        result = execute([0x18, 0, 42, 0x0C, 0, 0x0D, 1, 0x00])
        assert result["registers"][0] == 42
        assert result["registers"][1] == 42

    def test_stack_pointer_changes(self):
        result = execute([0x0C, 0, 0x0C, 0, 0x0C, 0, 0x00])
        # 3 pushes, SP should decrease by 3
        assert result["stack_pointer"] == 4096 - 3

    def test_pop_restores_stack(self):
        result = execute([0x18, 0, 10, 0x0C, 0, 0x0D, 1, 0x00])
        # Push then pop = net zero SP change
        assert result["stack_pointer"] == 4096


# ── control flow: JZ, JNZ ──────────────────────────────

class TestExecuteJumps:
    def test_jz_taken(self):
        """JZ should jump when register is 0, landing at HALT (R0 stays 0)."""
        # Layout:
        #   PC 0: MOVI R0, 0    (3 bytes)
        #   PC 3: JZ R0, 7      (4 bytes) — taken: pc=3+7=10 (HALT); not taken: pc=7
        #   PC 7: MOVI R0, 99   (3 bytes)
        #   PC 10: HALT         (1 byte)
        bytecode = [0x18, 0, 0, 0x3C, 0, 7, 0, 0x18, 0, 99, 0x00]
        result = execute(bytecode)
        assert result["halted"] is True
        assert result["registers"][0] == 0  # JZ taken, skipped MOVI R0, 99

    def test_jz_not_taken(self):
        """JZ should NOT jump when register is non-zero, executing the MOVI."""
        bytecode = [0x18, 0, 5, 0x3C, 0, 7, 0, 0x18, 0, 99, 0x00]
        result = execute(bytecode)
        assert result["halted"] is True
        assert result["registers"][0] == 99  # JZ not taken, executed MOVI R0, 99

    def test_jnz_not_taken(self):
        """JNZ should NOT jump when register is 0, executing the MOVI."""
        bytecode = [0x18, 0, 0, 0x3D, 0, 7, 0, 0x18, 0, 99, 0x00]
        result = execute(bytecode)
        assert result["halted"] is True
        assert result["registers"][0] == 99  # JNZ not taken, executed MOVI

    def test_jnz_taken(self):
        """JNZ should jump when register is non-zero, skipping the MOVI."""
        bytecode = [0x18, 0, 5, 0x3D, 0, 7, 0, 0x18, 0, 99, 0x00]
        result = execute(bytecode)
        assert result["halted"] is True
        assert result["registers"][0] == 5  # JNZ taken, skipped MOVI R0, 99


# ── MOVI16 instruction ─────────────────────────────────

class TestExecuteMOVI16:
    def test_mov16_small(self):
        result = execute([0x40, 0, 42, 0, 0x00])
        assert result["registers"][0] == 42

    def test_mov16_large(self):
        result = execute([0x40, 0, 0xFF, 0x00, 0x00])
        assert result["registers"][0] == 255

    def test_mov16_negative(self):
        # 0x8000 = -32768 in signed 16-bit
        result = execute([0x40, 0, 0x00, 0x80, 0x00])
        assert result["registers"][0] == -32768


# ── execution trace ────────────────────────────────────

class TestExecuteTrace:
    def test_trace_has_entries(self):
        result = execute([0x18, 0, 5, 0x00])
        assert len(result["trace"]) > 0

    def test_trace_max_100(self):
        result = execute([0x01] * 200 + [0x00])
        assert len(result["trace"]) <= 100

    def test_trace_pc_values(self):
        result = execute([0x18, 0, 5, 0x00])
        pcs = [t["pc"] for t in result["trace"]]
        assert 0 in pcs  # first instruction at PC 0

    def test_trace_opcode_values(self):
        result = execute([0x18, 0, 5, 0x00])
        ops = [t["op"] for t in result["trace"]]
        assert 0x18 in ops  # MOVI opcode
        assert 0x00 in ops  # HALT opcode

    def test_trace_registers(self):
        result = execute([0x18, 0, 42, 0x00])
        # Find the HALT trace entry - R0 should be 42 by then
        halt_trace = [t for t in result["trace"] if t["op"] == 0x00][0]
        assert halt_trace["regs"][0] == 42


# ── execution limits ───────────────────────────────────

class TestExecuteLimits:
    def test_cycle_limit(self):
        """VM should stop after 10000 cycles."""
        # JNZ R0, 0 with R0=1 creates infinite loop
        result = execute([0x18, 0, 1, 0x3D, 0, 0, 0x00])
        assert result["cycles"] == 10000
        assert result["halted"] is False

    def test_empty_bytecode(self):
        """Empty bytecode should halt immediately (pc >= len)."""
        result = execute([])
        assert result["halted"] is False
        assert result["cycles"] == 0


# ── return value structure ─────────────────────────────

class TestExecuteOutput:
    def test_output_keys(self):
        result = execute([0x00])
        assert "halted" in result
        assert "cycles" in result
        assert "registers" in result
        assert "register_names" in result
        assert "stack_pointer" in result
        assert "trace" in result

    def test_registers_length(self):
        result = execute([0x00])
        assert len(result["registers"]) == 16

    def test_register_names(self):
        result = execute([0x00])
        assert result["register_names"][0] == "R0"
        assert result["register_names"][15] == "R15"

    def test_stack_pointer_initial(self):
        result = execute([0x00])
        assert result["stack_pointer"] == 4096


# ── integration: full pipeline ─────────────────────────

class TestFullPipeline:
    def test_assemble_execute_add(self):
        """Full pipeline: assemble text -> execute -> verify."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from repl import assemble
        source = "MOVI R0, 10\nMOVI R1, 20\nADD R2, R0, R1\nHALT"
        asm = assemble(source)
        assert "error" not in asm
        result = execute(asm["bytecode"])
        assert result["halted"] is True
        assert result["registers"][2] == 30

    def test_assemble_execute_multiply(self):
        from repl import assemble
        source = "MOVI R0, 6\nMOVI R1, 7\nMUL R2, R0, R1\nHALT"
        asm = assemble(source)
        result = execute(asm["bytecode"])
        assert result["registers"][2] == 42

    def test_counting_loop(self):
        """Manual bytecode for a 10-iteration counting loop."""
        # PC 0:  MOVI R0, 10   [0x18, 0, 10]
        # PC 3:  MOVI R1, 0    [0x18, 1, 0]
        # PC 6:  ADDI R1, 1    [0x19, 1, 1]    ← loop target
        # PC 9:  DEC R0        [0x09, 0]
        # PC 11: JNZ R0, -5    [0x3D, 0, 251, 0]  offset = 6-11 = -5, (-5)&0xFF=251
        # PC 15: HALT          [0x00]
        bytecode = [0x18, 0, 10, 0x18, 1, 0, 0x19, 1, 1, 0x09, 0, 0x3D, 0, 251, 0, 0x00]
        result = execute(bytecode)
        assert result["halted"] is True
        assert result["registers"][1] == 10  # counted up 10 times


# ── register range ─────────────────────────────────────

class TestRegisterRange:
    def test_high_register(self):
        """VM has 64 registers; test accessing a high one."""
        result = execute([0x18, 63, 99, 0x00])
        # Register 63 is in the regs array but only first 16 are returned
        assert result["halted"] is True
