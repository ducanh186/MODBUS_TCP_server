"""
BÀI TOÁN (Modbus TCP Server Simulator - skeleton):
- Chạy ở Terminal #1.
- Listen TCP 127.0.0.1:1502.
- Parse Modbus TCP từ TCP stream (stream = luồng byte).
- Hỗ trợ tối thiểu:
  - FC03 Read Holding Registers
  - FC06 Write Single Register
- Có FaultInjector để mô phỏng mạng xấu (delay/chunk/drop/close) - tắt mặc định.

MỤC TIÊU DEMO:
1) Client gửi FC06 (write) -> server ghi Holding Register
2) Client gửi FC03 (read) -> server trả lại value vừa ghi
=> "write rồi read lại"

CÁCH CHẠY:
  cd MODBUS_TCP_server
  python server.py
"""

import logging
import socket
import threading
from typing import Tuple

from modbus_tcp import (
    frame_from_stream_buffer,
    parse_request_pdu,
    build_response_adu,
    build_exception_adu,
    hexdump,
    ModbusRequest,
)
from device import DeviceModel
from faults import FaultInjector

HOST = "127.0.0.1"
PORT = 1502  # dev port (không cần quyền admin như 502)

# Tắt hết trước. Khi muốn mô phỏng mạng: tăng delay/chunk/drop/close.
FAULTS = FaultInjector(
    delay_ms_min=0,
    delay_ms_max=0,
    chunk_min=1,
    chunk_max=1,
    drop_rate=0.0,
    close_rate=0.0,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
device = DeviceModel(holding_size=200)


def handle_client(conn: socket.socket, addr: Tuple[str, int]) -> None:
    logging.info(f"[ACCEPT] client={addr}")
    conn.settimeout(5.0)
    buf = b""

    while True:
        try:
            data = conn.recv(4096)
            if not data:
                logging.info(f"[CLOSE] client={addr}")
                return

            logging.info(f"[RECV] {addr} bytes={len(data)} hex={hexdump(data)}")
            buf += data

            # Có thể dính nhiều frame -> xử lý hết frame đã đủ trong buffer
            while True:
                frame, buf = frame_from_stream_buffer(buf)
                if frame is None:
                    break

                try:
                    req: ModbusRequest = parse_request_pdu(frame)
                except Exception as e:
                    logging.warning(f"[PARSE_ERR] {addr} err={e} frame={hexdump(frame)}")
                    continue

                logging.info(
                    f"[REQ] {addr} TID={req.transaction_id} UID={req.unit_id} "
                    f"FC={req.function_code} addr={req.address} val/count={req.value_or_count}"
                )

                try:
                    if req.function_code == 3:
                        values = device.read_holding(req.address, req.value_or_count)
                        resp = build_response_adu(req, values)
                    elif req.function_code == 6:
                        device.write_single(req.address, req.value_or_count)
                        resp = build_response_adu(req, None)
                    else:
                        resp = build_exception_adu(req, exc_code=1)  # Illegal Function
                except ValueError:
                    resp = build_exception_adu(req, exc_code=2)  # Illegal Data Address
                except Exception:
                    resp = build_exception_adu(req, exc_code=4)  # Slave Device Failure

                # Fault injection
                FAULTS.maybe_sleep()
                if FAULTS.should_drop():
                    logging.warning(f"[DROP] {addr} response dropped for TID={req.transaction_id}")
                    continue

                for c in FAULTS.chunk_bytes(resp):
                    conn.sendall(c)
                    logging.info(f"[SEND] {addr} bytes={len(c)} hex={hexdump(c)}")

                if FAULTS.should_close():
                    logging.warning(f"[FORCE_CLOSE] {addr}")
                    conn.close()
                    return

        except socket.timeout:
            logging.info(f"[TIMEOUT] {addr}")
            continue
        except ConnectionResetError:
            logging.info(f"[RESET] {addr}")
            return
        except OSError as e:
            logging.info(f"[OSERR] {addr} err={e}")
            return


def main() -> None:
    device.start_background_updates()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        logging.info(f"Modbus TCP Server listening on {HOST}:{PORT}")

        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
