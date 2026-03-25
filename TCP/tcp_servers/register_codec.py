"""
Generic register codec for Huawei Modbus data types.

Supports: U16, I16, U32, I32, U64, I64, STR, MAC, Bitfield16, Bitfield32

Convention:
    encode: real_value * gain → raw uint16 register(s)
    decode: raw uint16 register(s) / gain → real_value
"""

from __future__ import annotations

from typing import Any, Dict, List, Union


# ---------------------------------------------------------------------------
# Size lookup (registers per dtype). STR/MAC use quantity from spec.
# ---------------------------------------------------------------------------

DTYPE_SIZE = {
    "U16": 1, "I16": 1,
    "U32": 2, "I32": 2,
    "U64": 4, "I64": 4,
    "Bitfield16": 1, "Bitfield32": 2,
    # STR, MAC: variable — use quantity from point spec
}


# ---------------------------------------------------------------------------
# Encode functions: value → list[uint16]
# ---------------------------------------------------------------------------

def encode_u16(value: Union[int, float], gain: int = 1) -> List[int]:
    raw = int(round(value * gain))
    return [raw & 0xFFFF]


def encode_i16(value: Union[int, float], gain: int = 1) -> List[int]:
    raw = int(round(value * gain))
    return [raw & 0xFFFF]


def encode_u32(value: Union[int, float], gain: int = 1) -> List[int]:
    raw = int(round(value * gain))
    return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]


def encode_i32(value: Union[int, float], gain: int = 1) -> List[int]:
    raw = int(round(value * gain))
    if raw < 0:
        raw += 0x1_0000_0000
    return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]


def encode_u64(value: Union[int, float], gain: int = 1) -> List[int]:
    raw = int(round(value * gain))
    return [
        (raw >> 48) & 0xFFFF,
        (raw >> 32) & 0xFFFF,
        (raw >> 16) & 0xFFFF,
        raw & 0xFFFF,
    ]


def encode_i64(value: Union[int, float], gain: int = 1) -> List[int]:
    raw = int(round(value * gain))
    if raw < 0:
        raw += (1 << 64)
    return [
        (raw >> 48) & 0xFFFF,
        (raw >> 32) & 0xFFFF,
        (raw >> 16) & 0xFFFF,
        raw & 0xFFFF,
    ]


def encode_str(value: str, quantity: int) -> List[int]:
    """String → list[uint16]. 2 ASCII chars per register, null-padded."""
    encoded = value.encode("ascii", errors="ignore")
    padded = encoded.ljust(quantity * 2, b"\x00")[: quantity * 2]
    regs = []
    for i in range(0, len(padded), 2):
        regs.append((padded[i] << 8) | padded[i + 1])
    return regs


def encode_mac(mac_str: str) -> List[int]:
    """MAC "AA:BB:CC:DD:EE:FF" → 3 uint16 registers."""
    parts = [int(x, 16) for x in mac_str.split(":")]
    return [
        (parts[0] << 8) | parts[1],
        (parts[2] << 8) | parts[3],
        (parts[4] << 8) | parts[5],
    ]


def encode_bitfield16(value: int) -> List[int]:
    return [int(value) & 0xFFFF]


def encode_bitfield32(value: int) -> List[int]:
    raw = int(value)
    return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]


# ---------------------------------------------------------------------------
# Decode functions: list[uint16] → value
# ---------------------------------------------------------------------------

def decode_u16(regs: List[int], gain: int = 1) -> Union[int, float]:
    raw = regs[0]
    return raw / gain if gain != 1 else raw


def decode_i16(regs: List[int], gain: int = 1) -> Union[int, float]:
    raw = regs[0]
    raw = raw - 0x10000 if raw >= 0x8000 else raw
    return raw / gain if gain != 1 else raw


def decode_u32(regs: List[int], gain: int = 1) -> Union[int, float]:
    raw = (regs[0] << 16) | regs[1]
    return raw / gain if gain != 1 else raw


def decode_i32(regs: List[int], gain: int = 1) -> Union[int, float]:
    raw = (regs[0] << 16) | regs[1]
    if raw >= 0x8000_0000:
        raw -= 0x1_0000_0000
    return raw / gain if gain != 1 else raw


def decode_u64(regs: List[int], gain: int = 1) -> Union[int, float]:
    raw = (regs[0] << 48) | (regs[1] << 32) | (regs[2] << 16) | regs[3]
    return raw / gain if gain != 1 else raw


def decode_i64(regs: List[int], gain: int = 1) -> Union[int, float]:
    raw = (regs[0] << 48) | (regs[1] << 32) | (regs[2] << 16) | regs[3]
    if raw >= (1 << 63):
        raw -= (1 << 64)
    return raw / gain if gain != 1 else raw


def decode_str(regs: List[int]) -> str:
    """list[uint16] → ASCII string (null-stripped)."""
    raw = bytearray()
    for r in regs:
        raw.extend([(r >> 8) & 0xFF, r & 0xFF])
    return raw.rstrip(b"\x00").decode("ascii", errors="ignore").strip()


def decode_mac(regs: List[int]) -> str:
    """3 uint16 → "AA:BB:CC:DD:EE:FF"."""
    raw = bytearray()
    for r in regs:
        raw.extend([(r >> 8) & 0xFF, r & 0xFF])
    return ":".join(f"{b:02X}" for b in raw[:6])


def decode_bitfield16(regs: List[int]) -> int:
    return regs[0]


def decode_bitfield32(regs: List[int]) -> int:
    return (regs[0] << 16) | regs[1]


# ---------------------------------------------------------------------------
# Generic dispatch: encode(dtype, ...) / decode(dtype, ...)
# ---------------------------------------------------------------------------

_ENCODERS = {
    "U16":        lambda v, g, q: encode_u16(v, g),
    "I16":        lambda v, g, q: encode_i16(v, g),
    "U32":        lambda v, g, q: encode_u32(v, g),
    "I32":        lambda v, g, q: encode_i32(v, g),
    "U64":        lambda v, g, q: encode_u64(v, g),
    "I64":        lambda v, g, q: encode_i64(v, g),
    "STR":        lambda v, g, q: encode_str(v, q),
    "MAC":        lambda v, g, q: encode_mac(v),
    "Bitfield16": lambda v, g, q: encode_bitfield16(v),
    "Bitfield32": lambda v, g, q: encode_bitfield32(v),
}

_DECODERS = {
    "U16":        lambda r, g: decode_u16(r, g),
    "I16":        lambda r, g: decode_i16(r, g),
    "U32":        lambda r, g: decode_u32(r, g),
    "I32":        lambda r, g: decode_i32(r, g),
    "U64":        lambda r, g: decode_u64(r, g),
    "I64":        lambda r, g: decode_i64(r, g),
    "STR":        lambda r, g: decode_str(r),
    "MAC":        lambda r, g: decode_mac(r),
    "Bitfield16": lambda r, g: decode_bitfield16(r),
    "Bitfield32": lambda r, g: decode_bitfield32(r),
}


def encode(dtype: str, value: Any, gain: int = 1, quantity: int = 1) -> List[int]:
    """Encode a value to uint16 register list according to dtype.

    Args:
        dtype:    "U16", "I32", "STR", "MAC", etc.
        value:    The engineering value (float/int/str)
        gain:     Multiplier: raw = value * gain
        quantity: Number of registers (only used for STR)

    Returns:
        List of uint16 values (length depends on dtype)
    """
    enc = _ENCODERS.get(dtype)
    if enc is None:
        raise ValueError(f"Unsupported dtype: {dtype}")
    return enc(value, gain, quantity)


def decode(dtype: str, regs: List[int], gain: int = 1) -> Any:
    """Decode uint16 register list to engineering value.

    Args:
        dtype: "U16", "I32", "STR", "MAC", etc.
        regs:  List of uint16 raw register values
        gain:  Divisor: value = raw / gain

    Returns:
        Decoded value (int/float/str depending on dtype)
    """
    dec = _DECODERS.get(dtype)
    if dec is None:
        raise ValueError(f"Unsupported dtype: {dtype}")
    return dec(regs, gain)


# ---------------------------------------------------------------------------
# Point-level helpers (work with point spec dicts)
# ---------------------------------------------------------------------------

def encode_point(point: Dict[str, Any], value: Any) -> List[int]:
    """Encode a value according to a register point spec.

    point: {"dtype": "U32", "gain": 1000, "quantity": 2, ...}
    """
    return encode(
        dtype=point["dtype"],
        value=value,
        gain=point.get("gain", 1),
        quantity=point.get("quantity", DTYPE_SIZE.get(point["dtype"], 1)),
    )


def decode_point(point: Dict[str, Any], regs: List[int]) -> Any:
    """Decode registers according to a register point spec."""
    return decode(
        dtype=point["dtype"],
        regs=regs,
        gain=point.get("gain", 1),
    )


# ---------------------------------------------------------------------------
# Block-level helpers (work with block spec dicts)
# ---------------------------------------------------------------------------

def decode_block(raw_regs: List[int], block_start: int, points: List[Dict]) -> Dict[str, Any]:
    """Decode a block of raw registers into a named-value dict.

    Args:
        raw_regs:    list[uint16] from a single read_holding_registers call
        block_start: the starting address of the block (e.g. 30000)
        points:      list of point specs, each with "name", "address", "quantity", "dtype", "gain"

    Returns:
        {"model": "LUNA2000...", "rated_power_kw": 2000.0, ...}
    """
    result = {}
    for p in points:
        offset = p["address"] - block_start
        qty = p.get("quantity", DTYPE_SIZE.get(p["dtype"], 1))
        regs_slice = raw_regs[offset: offset + qty]
        result[p["name"]] = decode_point(p, regs_slice)
    return result


def encode_block(block_start: int, block_size: int,
                 points_with_values: List[tuple]) -> List[int]:
    """Encode named values into a flat register array.

    Args:
        block_start: starting address (e.g. 30000)
        block_size:  total register count in this block
        points_with_values: list of (point_spec, value) tuples

    Returns:
        list[uint16] of length block_size (unset positions = 0)
    """
    regs = [0] * block_size
    for point, value in points_with_values:
        offset = point["address"] - block_start
        encoded = encode_point(point, value)
        regs[offset: offset + len(encoded)] = encoded
    return regs
