import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'robot_nav_bringup'


def install_tree(source):
    """Return setuptools data-file groups while preserving subdirectories."""
    groups = []
    for path in glob(os.path.join(source, '**', '*'), recursive=True):
        if os.path.isfile(path):
            groups.append((
                os.path.join('share', package_name, os.path.dirname(path)),
                [path],
            ))
    return groups

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'worlds'), glob('worlds/*')),
    ] + install_tree('maps'),
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robium',
    maintainer_email='admin@robium.ai',
    description='Bringup, SLAM, and navigation composition for the robot-navigation app.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'drive_mapping_route = robot_nav_bringup.drive_mapping_route:main',
            'send_goals = robot_nav_bringup.send_goals:main',
            'cloud_demo_status = robot_nav_bringup.cloud_demo_status:main',
            'demo_init = robot_nav_bringup.demo_init:main',
            'teleop_relay = robot_nav_bringup.teleop_relay:main',
            'map_manager = robot_nav_bringup.map_manager:main',
            'session_manager = robot_nav_bringup.session_manager:main',
        ],
    },
)
