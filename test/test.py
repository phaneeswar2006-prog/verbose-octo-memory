
# SPDX-FileCopyrightText: 2026 Tiny Tapeout Project
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, ClockCycles


CLOCK_PERIOD_NS = 20
PWM_PERIOD = 20
INITIAL_DUTY = 10
NEW_DUTY = 5
DEAD_TIME = 3


async def sample_cycle(dut):
    """Sample outputs after the rising-edge sequential logic settles."""
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    return int(dut.uo_out.value)



async def write_shadow(dut, sel, value):
    """Write a shadow register without unintentionally disabling PWM."""
    await FallingEdge(dut.clk)

    # Preserve the current PWM enable state.
    pwm_was_enabled = int(dut.uio_in.value) & 0x08

    dut.ui_in.value = value & 0xFF
    dut.uio_in.value = pwm_was_enabled | (sel & 0x03) | 0x04

    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)

    # Disable register writing, but preserve PWM enable.
    dut.uio_in.value = pwm_was_enabled



async def collect_samples(dut, count):
    samples = []
    for _ in range(count):
        samples.append(await sample_cycle(dut))
    return samples


def check_no_overlap(samples):
    """Check that high-side and low-side outputs are never both HIGH."""
    for index, value in enumerate(samples):
        high = (value >> 0) & 1
        low = (value >> 1) & 1

        assert not (high and low), (
            f"Output overlap at sample {index}: "
            f"pwm_h={high}, pwm_l={low}"
        )


def period_tick_indices(samples):
    """Return sample positions where the period-boundary output is HIGH."""
    return [
        index for index, value in enumerate(samples)
        if (value >> 3) & 1
    ]


def check_deadtime(samples, dead_time):
    """Check the minimum sampled gap between opposite output transitions."""
    transitions = []

    for i in range(1, len(samples)):
        previous = samples[i - 1]
        current = samples[i]

        prev_h = previous & 1
        prev_l = (previous >> 1) & 1
        curr_h = current & 1
        curr_l = (current >> 1) & 1

        if prev_h and not curr_h:
            transitions.append(("H_OFF", i))

        if prev_l and not curr_l:
            transitions.append(("L_OFF", i))

    for kind, off_index in transitions:
        opposite_bit = 1 if kind == "H_OFF" else 0
        next_on = None

        for j in range(off_index + 1, len(samples)):
            if (samples[j] >> opposite_bit) & 1:
                next_on = j
                break

        if next_on is not None:
            gap = next_on - off_index
            assert gap >= dead_time, (
                f"Dead-time too short after {kind}: "
                f"{gap} clock cycles, required at least {dead_time}"
            )


def raw_high_widths_between_ticks(samples):
    """Count raw PWM HIGH samples between consecutive period ticks."""
    ticks = period_tick_indices(samples)
    widths = []

    for first, second in zip(ticks, ticks[1:]):
        # Exclude the first boundary sample; include the next one.
        segment = samples[first + 1:second + 1]
        widths.append(sum((value >> 2) & 1 for value in segment))

    return widths


@cocotb.test()
async def test_deadtime_pwm(dut):
    dut._log.info("Starting dead-time PWM verification")

    dut.ena.value = 1
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.ui_in.value = 0
    dut.uio_in.value = 0

    cocotb.start_soon(
        Clock(dut.clk, CLOCK_PERIOD_NS, units="ns").start()
    )

    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 3)

    # Check reset/default outputs and pin configuration.
    value = int(dut.uo_out.value)
    assert (value & 0x03) == 0, "PWM outputs should be OFF after reset"
    assert int(dut.uio_oe.value) == 0, "Bidirectional pins should be inputs"
    assert int(dut.uio_out.value) == 0, "Unused bidirectional outputs should be zero"
    dut._log.info("PASS: Reset and pin configuration")

    # Configure the module while PWM is disabled.
    # Select 00 = duty, 01 = period, 10 = dead-time.
    await write_shadow(dut, 0b01, PWM_PERIOD - 1)
    await write_shadow(dut, 0b00, INITIAL_DUTY)
    await write_shadow(dut, 0b10, DEAD_TIME)

    await ClockCycles(dut.clk, 3)

    # Enable PWM.
    await FallingEdge(dut.clk)
    dut.uio_in.value = 0x08

    # Collect enough samples to observe multiple PWM periods.
    samples = await collect_samples(dut, 140)

    check_no_overlap(samples)
    dut._log.info("PASS: High-side and low-side never overlap")

    ticks = period_tick_indices(samples)
    assert len(ticks) >= 4, (
        f"Expected multiple period-boundary pulses, found {len(ticks)}"
    )

    differences = [
        ticks[i + 1] - ticks[i]
        for i in range(len(ticks) - 1)
    ]

    assert all(diff == PWM_PERIOD for diff in differences), (
        f"Incorrect PWM period: observed tick differences {differences}"
    )
    dut._log.info("PASS: PWM period is %d clock cycles", PWM_PERIOD)

    widths = raw_high_widths_between_ticks(samples)
    assert INITIAL_DUTY in widths, (
        f"Expected raw PWM HIGH width of {INITIAL_DUTY}; "
        f"observed widths {widths}"
    )
    dut._log.info("PASS: Initial raw PWM duty cycle")

    check_deadtime(samples, DEAD_TIME)
    dut._log.info("PASS: Minimum sampled dead-time check")

    # Change the shadow duty while PWM is running.
    await write_shadow(dut, 0b00, NEW_DUTY)

    # The active duty should change at a period boundary, not immediately.
    updated_samples = await collect_samples(dut, 3 * PWM_PERIOD + 10)

    check_no_overlap(updated_samples)

    updated_widths = raw_high_widths_between_ticks(updated_samples)
    assert NEW_DUTY in updated_widths, (
        f"New duty did not appear at a sampled period boundary. "
        f"Expected width {NEW_DUTY}; observed {updated_widths}"
    )

    check_deadtime(updated_samples, DEAD_TIME)
    dut._log.info("PASS: Shadow duty update and dead-time check")

    dut._log.info("----------------------------------------")
    dut._log.info("PASS: All directed PWM checks completed")
    dut._log.info("----------------------------------------")
