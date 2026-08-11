import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'indoor_nav_bringup'

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
        (os.path.join('share', package_name, 'maps'), glob('maps/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robium',
    maintainer_email='admin@robium.ai',
    description='Bringup, SLAM, and navigation composition for the indoor-navigation app.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'drive_mapping_route = indoor_nav_bringup.drive_mapping_route:main',
            'send_goals = indoor_nav_bringup.send_goals:main',
            'demo_init = indoor_nav_bringup.demo_init:main',
            'teleop_relay = indoor_nav_bringup.teleop_relay:main',
            'map_manager = indoor_nav_bringup.map_manager:main',
        ],
    },
)
