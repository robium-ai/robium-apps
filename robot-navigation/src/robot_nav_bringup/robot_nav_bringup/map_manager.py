#!/usr/bin/env python3
"""Dashboard-facing map operations: save, load, reset — guarded by session mode.

Exists because the underlying services are awkward to drive from a browser
button: slam_toolbox's `save_map` takes a std_msgs/String inside the request,
nav2's `load_map` takes a URL, they live on different nodes, and neither knows
whether the current session is even allowed to do the thing being asked. This
node wraps all three behind std_srvs/Trigger, which the Lichtblick CallService
panel fires with an empty `{}` request — so a button is one click with nothing
to type.

The filename comes from the `map_name` PARAMETER rather than the request, which
is what makes map selection possible without a dropdown panel (Lichtblick has
none). foxglove_bridge enables `parameters` by default with param_whitelist
['.*'], so `map_name` is editable live from the Parameters panel: type a name,
then click Save or Load.

One artifact: <maps_dir>/<map_name>.yaml + .pgm, the occupancy grid. Mapping
sessions write it with slam_toolbox; localization sessions read it with nav2's
map_server + AMCL. No pose graph is serialised — resuming a mapping session is
not a workflow this app offers, and skipping it keeps saved maps to ~30 KB
instead of ~1.3 MB apiece.

Mode guard: the two sessions run genuinely different stacks — mapping has
slam_toolbox and no AMCL, localization has map_server + AMCL and no
slam_toolbox — so the services each session can honour differ, and the ones it
cannot are refused with an explanatory message rather than half-executed.
Lichtblick cannot grey out a button from ROS state, which is exactly why the
refusal has to live here: the guard holds no matter what calls it.
"""
import os
import threading

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile

from nav2_msgs.srv import LoadMap
from slam_toolbox.srv import Reset, SaveMap
from std_msgs.msg import String
from std_srvs.srv import Trigger

# Latched: a panel that connects after we publish still gets the current value.
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

SERVICE_TIMEOUT_S = 30.0  # rasterising and writing a large grid is not instant


class MapManager(Node):

    def __init__(self):
        super().__init__('map_manager')
        self.declare_parameter('map_name', 'map')
        self.declare_parameter('maps_dir', '/ws/maps')
        self.declare_parameter('session_mode', 'mapping')

        self.mode = self.get_parameter('session_mode').value
        if self.mode not in ('mapping', 'localization'):
            raise ValueError(
                f"session_mode must be 'mapping' or 'localization', got {self.mode!r}")

        # Reentrant throughout: every handler below calls another service and
        # waits for it. On the default mutually-exclusive group that is an
        # instant self-deadlock — the executor cannot service the response
        # while it is still inside the handler that triggered it.
        group = ReentrantCallbackGroup()

        self.cli_save = self.create_client(SaveMap, '/slam_toolbox/save_map',
                                           callback_group=group)
        self.cli_load = self.create_client(LoadMap, '/map_server/load_map',
                                           callback_group=group)
        self.cli_reset = self.create_client(Reset, '/slam_toolbox/reset',
                                            callback_group=group)

        self.create_service(Trigger, '/mapping/save', self.on_save, callback_group=group)
        self.create_service(Trigger, '/mapping/load', self.on_load, callback_group=group)
        self.create_service(Trigger, '/mapping/reset', self.on_reset, callback_group=group)

        self.pub_state = self.create_publisher(String, '/mapping/state', LATCHED)
        self.pub_maps = self.create_publisher(String, '/maps/available', LATCHED)
        self.pub_state.publish(String(data=self.mode.upper()))
        self.publish_available()
        # Cheap directory listing; keeps the panel honest if a map is added or
        # removed outside this node.
        self.create_timer(5.0, self.publish_available, callback_group=group)

        self.get_logger().info(f'map_manager up in {self.mode} mode')

    # --- helpers -----------------------------------------------------------

    def map_path(self):
        return os.path.join(self.get_parameter('maps_dir').value,
                            self.get_parameter('map_name').value)

    def publish_available(self):
        maps_dir = self.get_parameter('maps_dir').value
        try:
            names = sorted(os.path.splitext(e)[0] for e in os.listdir(maps_dir)
                           if e.endswith('.yaml'))
        except OSError as exc:
            self.pub_maps.publish(String(data=f'<cannot read {maps_dir}: {exc}>'))
            return
        self.pub_maps.publish(
            String(data='\n'.join(names) if names else '<none saved yet>'))

    def call(self, client, request, what):
        """Call a downstream service, returning (ok, message).

        Waits on a threading.Event rather than spinning. Do NOT reach for
        rclpy.spin_until_future_complete(self, ...) here: it builds a fresh
        SingleThreadedExecutor and calls add_node, which silently returns False
        because this node already belongs to the MultiThreadedExecutor in
        main(). It then spins an executor with no nodes and blocks for the full
        timeout while the response is delivered on the other executor's threads
        — so every call "times out" while actually having succeeded, and
        foxglove_bridge blacklists this node's parameters after its own
        parameter request times out behind the blocked callback.

        add_done_callback fires on the executor thread that is already running,
        so blocking this callback thread on an Event is safe: the reentrant
        callback group means the executor still has threads free to service the
        response that sets it.
        """
        if not client.wait_for_service(timeout_sec=5.0):
            return False, f'{what}: {client.srv_name} unavailable'
        done = threading.Event()
        future = client.call_async(request)
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=SERVICE_TIMEOUT_S):
            return False, f'{what}: timed out after {SERVICE_TIMEOUT_S:.0f}s'
        response = future.result()
        if response is None:
            return False, f'{what}: call failed (no response)'
        # SaveMap and LoadMap both report a nonzero uint8 on failure; Reset's
        # result is always RESULT_SUCCESS. getattr's default covers any
        # response type without the field.
        result = getattr(response, 'result', 0)
        if result != 0:
            return False, f'{what}: returned result={result}'
        return True, f'{what}: ok'

    def refuse(self, action, needed):
        msg = (f'refused: {action} needs a {needed} session, '
               f'this one is {self.mode}')
        self.get_logger().warning(msg)
        return msg

    # --- services ----------------------------------------------------------

    def on_save(self, _request, response):
        if self.mode != 'mapping':
            response.success = False
            response.message = self.refuse('save', 'mapping')
            return response
        path = self.map_path()
        ok, msg = self.call(
            self.cli_save, SaveMap.Request(name=String(data=path)), 'save')
        response.success = ok
        # Saving does not pause the mapper — keep driving and refine it.
        response.message = f'{path}.yaml: {msg} (still mapping)'
        self.publish_available()
        return response

    def on_load(self, _request, response):
        if self.mode != 'localization':
            response.success = False
            response.message = self.refuse('load', 'localization')
            return response
        path = self.map_path() + '.yaml'
        if not os.path.exists(path):
            response.success = False
            response.message = f'{path} not found'
            return response
        # map_server already loaded map_name at launch; this is how you SWITCH
        # to another one without restarting. AMCL keeps its pose estimate
        # across the swap (always_reset_initial_pose is false), so a map of
        # somewhere else needs a pose estimate dragged in the 3D panel.
        response.success, response.message = self.call(
            self.cli_load, LoadMap.Request(map_url=path), f'load {path}')
        return response

    def on_reset(self, _request, response):
        if self.mode != 'mapping':
            response.success = False
            response.message = self.refuse('reset', 'mapping')
            return response
        response.success, response.message = self.call(
            self.cli_reset, Reset.Request(), 'reset')
        return response


def main(argv=None):
    rclpy.init(args=argv)
    node = MapManager()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
