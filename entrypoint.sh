#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash
exec ros2 launch wolfpackcloud_peer peer.launch.py "$@"
