from glob import glob

from setuptools import find_packages, setup

PACKAGE = "silly_turtlebot_sim"

setup(
    name=PACKAGE,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE}"]),
        (f"share/{PACKAGE}", ["package.xml"]),
        (f"share/{PACKAGE}/launch", glob("launch/*.launch.py")),
        (f"share/{PACKAGE}/config", glob("config/*.yaml")),
        (
            f"share/{PACKAGE}/maps/furnished_house",
            glob("maps/furnished_house/*"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="robium",
    maintainer_email="admin@robium.ai",
    description="Gazebo Harmonic furnished-home bringup for Silly TurtleBot",
    license="MIT",
)
