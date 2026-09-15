from glob import glob

from setuptools import find_packages, setup

PACKAGE = "silly_turtlebot_ros"

setup(
    name=PACKAGE,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE}"]),
        (f"share/{PACKAGE}", ["package.xml"]),
        (f"share/{PACKAGE}/launch", glob("launch/*.launch.py")),
        (f"share/{PACKAGE}/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="robium",
    maintainer_email="admin@robium.ai",
    description="Guarded HTTP-to-ROS 2 bridge for Silly TurtleBot",
    license="MIT",
    entry_points={
        "console_scripts": [
            "bridge = silly_turtlebot_ros.bridge:main",
            "external_camera_relay = silly_turtlebot_ros.external_camera_relay:main",
            "gamepad_actions = silly_turtlebot_ros.gamepad_actions:main",
            "remote_joy = silly_turtlebot_ros.remote_joy:main",
        ]
    },
)
