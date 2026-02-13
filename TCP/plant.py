"""
Plant orchestrator — starts all Modbus TCP servers (PMS, PCS, BMS)
and the Multimeter RTU server as separate processes.

Usage:
    python plant.py --config config/plant.yaml

Each device runs in its own process:
  - PMS  (TCP server + PMS controller thread)
  - PCS1 (TCP server + PCS controller thread)
  - PCS2 (TCP server + PCS controller thread)
  - BMS1 (TCP server + BMS controller thread)
  - BMS2 (TCP server + BMS controller thread)
  - Multimeter (RTU server + updater thread)

Controllers communicate with other devices ONLY via Modbus TCP/RTU.
No shared memory across processes.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import signal
import sys
import time
from typing import Any, Dict, List

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | PLANT | %(levelname)s | %(message)s",
)
log = logging.getLogger("plant")


# ---------------------------------------------------------------------------
# Process target wrappers (must be top-level for pickling on Windows)
# ---------------------------------------------------------------------------

def _start_pms(host, port, pcs_ports, bms_ports, pairing, tick_interval_s):
    """Entry for PMS subprocess."""
    # Re-add paths in subprocess
    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    sys.path.insert(0, os.path.join(base, "tcp_servers"))

    from tcp_servers.pms_server import run_pms_server
    run_pms_server(host, port, pcs_ports, bms_ports, pairing, tick_interval_s)


def _start_pcs(device_name, host, port, paired_bms_host, paired_bms_port, tick_interval_s):
    """Entry for PCS subprocess."""
    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    sys.path.insert(0, os.path.join(base, "tcp_servers"))

    from tcp_servers.pcs_server import run_pcs_server
    run_pcs_server(device_name, host, port, paired_bms_host, paired_bms_port, tick_interval_s)


def _start_bms(device_name, host, port, paired_pcs_host, paired_pcs_port, tick_interval_s):
    """Entry for BMS subprocess."""
    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    sys.path.insert(0, os.path.join(base, "tcp_servers"))

    from tcp_servers.bms_server import run_bms_server
    run_bms_server(device_name, host, port, paired_pcs_host, paired_pcs_port, tick_interval_s)


def _start_multimeter(com_port, slave_id, baudrate, host, pcs_ports, loss_ratio, tick_interval_s):
    """Entry for Multimeter RTU subprocess."""
    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    sys.path.insert(0, os.path.join(base, "tcp_servers"))

    from rtu_multimeter.multimeter_rtu_server import run_multimeter_server
    run_multimeter_server(com_port, slave_id, baudrate, host, pcs_ports, loss_ratio, tick_interval_s)


# ---------------------------------------------------------------------------
# Plant class
# ---------------------------------------------------------------------------

class Plant:
    """Owns all device processes and manages lifecycle."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.host: str = config["host"]
        self.tick: float = config["tick_interval_s"]
        self.loss: float = config["loss_ratio"]
        self.tcp_ports: Dict[str, int] = config["tcp_ports"]
        self.pairing: Dict[str, str] = config["pairing"]
        self.com0com: Dict[str, Any] = config.get("com0com", {})
        self.processes: List[multiprocessing.Process] = []

    # -- helpers to derive port dicts --
    @property
    def pcs_ports(self) -> Dict[str, int]:
        return {k: v for k, v in self.tcp_ports.items() if k.startswith("pcs")}

    @property
    def bms_ports(self) -> Dict[str, int]:
        return {k: v for k, v in self.tcp_ports.items() if k.startswith("bms")}

    def start(self) -> None:
        """Launch all device processes."""

        # 1) BMS servers first (PCS controllers need them)
        for bms_name, bms_port in self.bms_ports.items():
            # Find paired PCS
            paired_pcs = None
            for pcs_name, paired_bms in self.pairing.items():
                if paired_bms == bms_name:
                    paired_pcs = pcs_name
                    break
            paired_pcs_port = self.tcp_ports.get(paired_pcs, 0) if paired_pcs else 0

            p = multiprocessing.Process(
                target=_start_bms,
                args=(bms_name.upper(), self.host, bms_port,
                      self.host, paired_pcs_port, self.tick),
                name=f"proc-{bms_name}",
                daemon=True,
            )
            p.start()
            self.processes.append(p)
            log.info(f"Started {bms_name.upper()} process (pid={p.pid}, port={bms_port})")

        # Small delay so BMS servers bind before PCS tries to connect
        time.sleep(1.0)

        # 2) PCS servers
        for pcs_name, pcs_port in self.pcs_ports.items():
            paired_bms = self.pairing[pcs_name]
            paired_bms_port = self.tcp_ports[paired_bms]

            p = multiprocessing.Process(
                target=_start_pcs,
                args=(pcs_name.upper(), self.host, pcs_port,
                      self.host, paired_bms_port, self.tick),
                name=f"proc-{pcs_name}",
                daemon=True,
            )
            p.start()
            self.processes.append(p)
            log.info(f"Started {pcs_name.upper()} process (pid={p.pid}, port={pcs_port})")

        time.sleep(1.0)

        # 3) PMS server
        pms_port = self.tcp_ports["pms"]
        p = multiprocessing.Process(
            target=_start_pms,
            args=(self.host, pms_port, self.pcs_ports, self.bms_ports,
                  self.pairing, self.tick),
            name="proc-pms",
            daemon=True,
        )
        p.start()
        self.processes.append(p)
        log.info(f"Started PMS process (pid={p.pid}, port={pms_port})")

        # 4) Multimeter RTU (optional — only if com0com section present)
        if self.com0com and self.com0com.get("server_port"):
            p = multiprocessing.Process(
                target=_start_multimeter,
                args=(
                    self.com0com["server_port"],
                    self.com0com.get("slave_id", 10),
                    self.com0com.get("baudrate", 9600),
                    self.host,
                    self.pcs_ports,
                    self.loss,
                    self.tick,
                ),
                name="proc-multimeter",
                daemon=True,
            )
            p.start()
            self.processes.append(p)
            log.info(f"Started Multimeter RTU process (pid={p.pid}, "
                     f"port={self.com0com['server_port']})")
        else:
            log.warning("com0com not configured — skipping Multimeter RTU server")

        log.info("All device processes started.")

    def wait(self) -> None:
        """Block until all processes exit or Ctrl-C."""
        try:
            while True:
                alive = [p for p in self.processes if p.is_alive()]
                if not alive:
                    log.info("All processes exited.")
                    break
                time.sleep(1.0)
        except KeyboardInterrupt:
            log.info("Ctrl-C received — shutting down.")
            self.stop()

    def stop(self) -> None:
        """Terminate all child processes."""
        for p in self.processes:
            if p.is_alive():
                log.info(f"Terminating {p.name} (pid={p.pid})")
                p.terminate()
        for p in self.processes:
            p.join(timeout=5)
        log.info("All processes stopped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Modbus Plant Simulator")
    parser.add_argument("--config", default="config/plant.yaml",
                        help="Path to plant.yaml config file")
    args = parser.parse_args()

    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_path)

    log.info(f"Loading config from {config_path}")
    config = load_config(config_path)

    plant = Plant(config)
    plant.start()
    plant.wait()


if __name__ == "__main__":
    # Required for multiprocessing on Windows
    multiprocessing.freeze_support()
    main()
