FROM ros:humble-ros-core-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    RMW_IMPLEMENTATION=rmw_zenoh_cpp

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       python3-colcon-common-extensions \
       python3-setuptools \
       ros-humble-ament-cmake \
       ros-humble-ament-package \
       ros-humble-builtin-interfaces \
       ros-humble-launch-ros \
       ros-humble-rcl-interfaces \
       ros-humble-rclpy \
       ros-humble-rmw-zenoh-cpp \
       ros-humble-rosidl-default-generators \
       ros-humble-rosidl-default-runtime \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ros2_ws
COPY ros2_ws/src ./src

RUN bash -c "source /opt/ros/humble/setup.bash && colcon build --symlink-install"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
