"""Symmetrical Zenoh peer: echoes peer pings and measures round-trip latency (median over a window)."""

from __future__ import annotations

import hashlib
import os
import statistics
import time
from collections import deque
from typing import Deque, Dict

import rclpy
from rcl_interfaces.msg import ParameterType
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from wolfpackcloud_peer_interfaces.msg import RttPacket

_INT32_MAX = 2**31 - 1
_INT32_MIN = -_INT32_MAX - 1


class PeerNode(Node):
    """Publish/subscribe loop with echoed correlation_id; RTT uses local monotonic clock."""

    def __init__(self) -> None:
        super().__init__("wolfpackcloud_peer_node")

        self.declare_parameter("publish_topic", "/topic_a")
        self.declare_parameter("subscribe_topic", "/topic_b")
        self.declare_parameter("pulse_period_sec", 1.0)
        self.declare_parameter("log_period_sec", 5.0)
        self.declare_parameter("stats_window_size", 64)
        self.declare_parameter("qos_depth", 32)
        self.declare_parameter("pending_cap", 128)
        self.declare_parameter("counter_reset_abs_max", 2_000_000_000)
        self.declare_parameter("peer_shard", 0)

        pub_topic = self.get_parameter("publish_topic").get_parameter_value().string_value
        sub_topic = self.get_parameter("subscribe_topic").get_parameter_value().string_value
        pulse_period = float(self.get_parameter("pulse_period_sec").value)
        log_period = float(self.get_parameter("log_period_sec").value)
        self._window_size = max(1, int(self.get_parameter("stats_window_size").value))
        qos_depth = max(1, int(self.get_parameter("qos_depth").value))
        self._pending_cap = int(self.get_parameter("pending_cap").value)
        self._counter_cap = max(1, int(self.get_parameter("counter_reset_abs_max").value))

        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=qos_depth,
        )

        self._cb_group = MutuallyExclusiveCallbackGroup()
        self._publisher = self.create_publisher(RttPacket, pub_topic, qos)
        self.create_subscription(RttPacket, sub_topic, self._on_msg, qos, callback_group=self._cb_group)

        self._counter = 0
        self._seq_u32 = 0
        self._shard = self._compute_peer_shard()
        self._pending_mono: Dict[int, float] = {}
        self._rtt_samples: Deque[float] = deque(maxlen=self._window_size)
        self._last_rtt_s: float | None = None

        self.create_timer(max(0.05, pulse_period), self._pulse, callback_group=self._cb_group)
        self.create_timer(max(0.5, log_period), self._log_stats, callback_group=self._cb_group)

        self.get_logger().info(
            f"publish={pub_topic} subscribe={sub_topic} peer_shard=0x{self._shard:08x} "
            f"window={self._window_size} qos_depth={qos_depth} pending_cap={self._pending_cap}; "
            "aggregate RTT uses median over the window (not arithmetic mean)"
        )

    @staticmethod
    def _clamp_int32(value: int) -> int:
        return value if _INT32_MIN <= value <= _INT32_MAX else 0

    def _shard_from_hostname(self) -> int:
        return int.from_bytes(hashlib.sha256(os.uname().nodename.encode()).digest()[:4], "big") & 0xFFFFFFFF

    def _compute_peer_shard(self) -> int:
        """Launch often passes peer_shard as a string; 0 / empty / auto → hash(hostname)."""
        pv = self.get_parameter("peer_shard").get_parameter_value()
        auto = self._shard_from_hostname

        if pv.type == ParameterType.PARAMETER_INTEGER:
            return auto() if pv.integer_value == 0 else int(pv.integer_value) & 0xFFFFFFFF
        if pv.type == ParameterType.PARAMETER_STRING:
            raw = pv.string_value.strip().lower()
            return auto() if raw in ("", "0", "auto") else int(raw, 0) & 0xFFFFFFFF
        return auto()

    def _next_correlation_id(self) -> int:
        self._seq_u32 = ((self._seq_u32 + 1) & 0xFFFFFFFF) or 1
        return (self._shard << 32) | self._seq_u32

    def _sanitize_counter(self) -> None:
        if abs(self._counter) > self._counter_cap:
            self.get_logger().warning(
                f"counter |{self._counter}| exceeded {self._counter_cap}; resetting counter and latency state"
            )
            self._hard_reset_latency_state()

    def _increment_counter(self) -> None:
        self._sanitize_counter()
        if self._counter == _INT32_MAX:
            self.get_logger().warning("int32 counter saturated high; resetting to 0")
            self._counter = 0
        elif self._counter == _INT32_MIN:
            self.get_logger().warning("int32 counter saturated low; resetting to 0")
            self._counter = 0
        else:
            self._counter += 1

    def _pending_overflow(self) -> bool:
        return len(self._pending_mono) >= self._pending_cap

    def _clear_latency_buffers(self) -> None:
        self._pending_mono.clear()
        self._rtt_samples.clear()
        self._last_rtt_s = None

    def _hard_reset_latency_state(self, counter_to: int = 0) -> None:
        self._clear_latency_buffers()
        self._counter = counter_to

    def _overflow_guard(self, reason: str) -> None:
        if not self._pending_overflow():
            return
        self.get_logger().warning(
            f"{reason}: pending map size {len(self._pending_mono)} >= cap {self._pending_cap}; "
            "resetting pending, RTT window, last RTT (counter preserved)"
        )
        self._clear_latency_buffers()

    def _on_msg(self, msg: RttPacket) -> None:
        cid = int(msg.correlation_id)
        now_mono = time.monotonic()

        if msg.is_reply:
            if cid in self._pending_mono:
                start = self._pending_mono.pop(cid)
                rtt = now_mono - start
                if rtt >= 0.0:
                    self._last_rtt_s = rtt
                    self._rtt_samples.append(rtt)
            return

        if cid in self._pending_mono:
            self.get_logger().warning(
                "dropping peer ping whose correlation_id collides with a pending local ping"
            )
            return

        self._overflow_guard("incoming peer packet while pending map is full")

        self._increment_counter()
        echo = RttPacket()
        echo.stamp_sent = msg.stamp_sent
        echo.correlation_id = msg.correlation_id
        echo.counter_value = self._clamp_int32(self._counter)
        echo.is_reply = True
        self._publisher.publish(echo)

    def _pulse(self) -> None:
        self._overflow_guard("pulse timer")

        cid = self._next_correlation_id()
        self._pending_mono[cid] = time.monotonic()

        pkt = RttPacket()
        pkt.stamp_sent = self.get_clock().now().to_msg()
        pkt.correlation_id = cid
        pkt.counter_value = self._clamp_int32(self._counter)
        pkt.is_reply = False
        self._publisher.publish(pkt)

    def _median_rtt_s(self) -> float | None:
        return float(statistics.median(self._rtt_samples)) if self._rtt_samples else None

    def _log_stats(self) -> None:
        pend = len(self._pending_mono)
        n = len(self._rtt_samples)
        tail = f"(window_cap={self._window_size} pending={pend})"
        med = self._median_rtt_s()

        if med is None:
            self.get_logger().info(f"rtt_ms median=n/a last=n/a samples=0 {tail}")
            return

        last_ms = f"{self._last_rtt_s * 1000.0:.3f}" if self._last_rtt_s is not None else "n/a"
        self.get_logger().info(
            f"rtt_ms median={med * 1000.0:.3f} last={last_ms} samples={n} {tail}"
        )


def main() -> None:
    rclpy.init()
    node = PeerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
