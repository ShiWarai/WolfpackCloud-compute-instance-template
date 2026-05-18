"""Launch wolfpackcloud_peer node with configurable topics."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "publish_topic",
                default_value="/topic_a",
                description="Outgoing wolfpackcloud_peer_interfaces/msg/RttPacket topic",
            ),
            DeclareLaunchArgument(
                "subscribe_topic",
                default_value="/topic_b",
                description="Incoming wolfpackcloud_peer_interfaces/msg/RttPacket topic",
            ),
            DeclareLaunchArgument(
                "pulse_period_sec",
                default_value="1.0",
                description="Seconds between locally originated pings",
            ),
            DeclareLaunchArgument(
                "log_period_sec",
                default_value="5.0",
                description="Seconds between rosout INFO aggregates (median RTT)",
            ),
            DeclareLaunchArgument(
                "peer_shard",
                default_value="0",
                description="uint32 shard for correlation_id high bits; 0 = derive from hostname hash",
            ),
            Node(
                package="wolfpackcloud_peer",
                executable="peer_node",
                name="wolfpackcloud_peer_node",
                output="screen",
                parameters=[
                    {
                        "publish_topic": LaunchConfiguration("publish_topic"),
                        "subscribe_topic": LaunchConfiguration("subscribe_topic"),
                        "pulse_period_sec": LaunchConfiguration("pulse_period_sec"),
                        "log_period_sec": LaunchConfiguration("log_period_sec"),
                        "peer_shard": ParameterValue(
                            LaunchConfiguration("peer_shard"),
                            value_type=int,
                        ),
                    }
                ],
            ),
        ]
    )
