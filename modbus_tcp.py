"""
Modbus TCP framing + parse/build tối thiểu.

TCP là stream -> recv() có thể:
- partial/fragmentation (bị cắt nhỏ)
- coalescing (dính chùm)
=> cần buffer và cắt frame theo MBAP Length.

MBAP:
- Transaction ID: match request/response
- Protocol ID: phải = 0
- Length: số byte còn lại (UnitID + PDU)
- Unit ID: giữ lại để simulate gateway/multi-slave
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional, Tuple, List


def hexdump(b: bytes) -> str:
    return b.hex(" ")


@dataclass(frozen=True)
class ModbusRequest:
    transaction_id: int
    protocol_id: int
    unit_id: int
    function_code: int
    address: int
    value_or_count: int


def frame_from_stream_buffer(buf: bytes) -> Tuple[Optional[bytes], bytes]:
    # cần ít nhất 6 byte để đọc TID/PID/LEN
    if len(buf) < 6:
        return None, buf

    tid, pid, length = struct.unpack(">HHH", buf[:6])
    total = 6 + length  # length = UnitID(1) + PDU(n)

    if len(buf) < total:
        return None, buf

    return buf[:total], buf[total:]


def parse_request_pdu(frame: bytes) -> ModbusRequest:
    if len(frame) < 8:
        raise ValueError("frame too short")

    tid, pid, length = struct.unpack(">HHH", frame[:6])
    if pid != 0:
        raise ValueError("protocol id must be 0")

    unit_id = frame[6]
    pdu = frame[7:]

    if len(pdu) < 5:
        raise ValueError("pdu too short")

    fc = pdu[0]
    address = struct.unpack(">H", pdu[1:3])[0]
    value_or_count = struct.unpack(">H", pdu[3:5])[0]

    return ModbusRequest(tid, pid, unit_id, fc, address, value_or_count)


def build_response_adu(req: ModbusRequest, values: Optional[List[int]]) -> bytes:
    if req.function_code == 3:
        assert values is not None
        byte_count = len(values) * 2
        pdu = bytes([3, byte_count]) + b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
    elif req.function_code == 6:
        # Echo request: FC + addr + value
        pdu = bytes([6]) + struct.pack(">H", req.address) + struct.pack(">H", req.value_or_count)
    else:
        pdu = bytes([req.function_code | 0x80, 1])

    length = 1 + len(pdu)
    mbap = struct.pack(">HHH", req.transaction_id, 0, length) + bytes([req.unit_id])
    return mbap + pdu


def build_exception_adu(req: ModbusRequest, exc_code: int) -> bytes:
    pdu = bytes([req.function_code | 0x80, exc_code & 0xFF])
    length = 1 + len(pdu)
    mbap = struct.pack(">HHH", req.transaction_id, 0, length) + bytes([req.unit_id])
    return mbap + pdu
