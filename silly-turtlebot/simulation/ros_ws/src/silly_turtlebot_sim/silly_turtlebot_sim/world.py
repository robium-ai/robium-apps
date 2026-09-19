"""Shared preparation of the pinned furnished-home world.

Both robot profiles drive the same legacy AWS Small House asset, which was
authored for Gazebo Classic and needs the same repairs and the same physics
tuning whichever robot is spawned into it. The one thing that differs is the
system plugin list: TurtleBot 4's Create 3 description carries its own
model-scoped Sensors system, so that world must NOT add a second one, while
TurtleBot 3 has no such system and the world must supply it.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ASSET_ROOT = Path("/opt/robium/assets/world.aws-small-house")
SOURCE_WORLD = ASSET_ROOT / "worlds" / "small_house.world"
WORLD_NAME = "small_house"
SPAWN_X = "3.5"
SPAWN_Y = "1.0"
COLLADA_TAGS_WITH_GLOBAL_NAMES = {"effect", "image", "material"}


def namespace_collada(path: Path) -> None:
    """Make legacy material resources unique across one Ogre2 scene."""
    tree = ET.parse(path)
    root = tree.getroot()
    namespace = root.tag.partition("}")[0].removeprefix("{")
    if namespace:
        ET.register_namespace("", namespace)

    relative = path.relative_to(ASSET_ROOT / "models")
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", f"{relative.parts[0]}_{path.stem}")
    renamed: dict[str, str] = {}
    for element in root.iter():
        old_id = element.get("id")
        if old_id:
            renamed[old_id] = f"{prefix}_{old_id}"

        local_tag = element.tag.rsplit("}", 1)[-1]
        old_name = element.get("name")
        if old_name and local_tag in COLLADA_TAGS_WITH_GLOBAL_NAMES:
            element.set("name", f"{prefix}_{old_name}")

    for element in root.iter():
        old_id = element.get("id")
        if old_id:
            element.set("id", renamed[old_id])
        for attribute, value in tuple(element.attrib.items()):
            if value in renamed:
                element.set(attribute, renamed[value])
            elif value.startswith("#") and value[1:] in renamed:
                element.set(attribute, f"#{renamed[value[1:]]}")
        if element.text:
            value = element.text.strip()
            if value in renamed:
                element.text = element.text.replace(value, renamed[value])
            elif value.startswith("#") and value[1:] in renamed:
                element.text = element.text.replace(value, f"#{renamed[value[1:]]}")

    tree.write(path, encoding="unicode")


def tune_physics(world: ET.Element) -> None:
    """Coarsen the legacy AWS step size so the house can approach real time.

    The pinned asset ships Gazebo Classic's defaults: a 1 ms step at a 1000 Hz
    update rate, i.e. 1000 physics steps per simulated second. Under this
    demo's CPU-only rendering the simulator cannot afford them. Real-time
    factor is what makes the demo legible -- at the measured upstream RTF of
    0.079, a TurtleBot 4 commanded to 0.3 m/s appears to crawl at 2 cm/s and a
    short hallway trip takes several minutes of a viewer's patience.

    A 4 ms step is well inside what TurtleBot 4 rolling on a flat floor needs;
    the Tugbot Warehouse asset ships 10 ms and drives correctly. Together with
    the sensor rates set in the Dockerfile this measures RTF 0.996 and 0.977
    over two clean 60 s windows at 249 physics iterations per real second,
    against 0.079 before -- effectively real time, about 12x faster.

    `real_time_factor` is a throttle rather than a target: modern Gazebo paces
    itself with sleeps and does not make them up after a render stall, so a cap
    of exactly 1.0 settles below it. 1.15 leaves the cap clear of where this
    demo actually runs, so rendering rather than the throttle sets the pace and
    a faster host is free to use its headroom. It is also not step x rate the
    way Gazebo Classic computed it, so the update rate alone cannot raise the
    ceiling -- 250 Hz is the step's natural partner (1 / 0.004), not a lever.

    `<solver><iters>` is deliberately not set: modern Gazebo runs dartsim
    (the asset's `type='ode'` attribute is legacy decoration) and ignores it.
    """
    physics = world.find("physics")
    if physics is None:
        raise RuntimeError("furnished-home asset has no <physics> element")
    for tag, value in (
        ("max_step_size", "0.004"),
        ("real_time_update_rate", "250"),
        ("real_time_factor", "1.15"),
    ):
        element = physics.find(tag)
        if element is None:
            element = ET.SubElement(physics, tag)
        element.text = value


def prepare_world(systems, prepared_name) -> str:
    """Repair the pinned Gazebo Classic world for modern Gazebo Harmonic."""
    if not SOURCE_WORLD.is_file():
        raise RuntimeError(f"furnished-home asset is missing: {SOURCE_WORLD}")

    root = ET.parse(SOURCE_WORLD).getroot()
    world = root.find("world")
    if world is None:
        raise RuntimeError("furnished-home asset has no <world> element")
    # The legacy file calls this world "default". Give it a stable explicit
    # name because TurtleBot 4's Gazebo bridges build sensor topic paths from it.
    world.set("name", WORLD_NAME)

    # The source asset contains a duplicate ixx field where the second entry is
    # izz. Be strict so an upstream asset change cannot silently corrupt physics.
    shoe_model = (
        ASSET_ROOT
        / "models"
        / "aws_robomaker_residential_ShoeRack_01"
        / "model.sdf"
    )
    shoe_tree = ET.parse(shoe_model)
    inertia = shoe_tree.getroot().find(".//inertia")
    if inertia is None:
        raise RuntimeError("shoe-rack model has no inertia")
    ixx = inertia.findall("ixx")
    izz = inertia.findall("izz")
    if len(ixx) == 2 and not izz:
        ixx[1].tag = "izz"
        shoe_tree.write(shoe_model, encoding="unicode")
    elif len(ixx) != 1 or len(izz) != 1:
        raise RuntimeError("shoe-rack inertia changed; re-verify the world patch")

    # Correct legacy portrait texture paths and namespace COLLADA identifiers.
    # The asset was authored for Gazebo Classic and repeats names such as
    # "Material #25" across files; Ogre2 treats those names as scene-global.
    for mesh in (ASSET_ROOT / "models").rglob("*.DAE"):
        contents = mesh.read_text(encoding="utf-8")
        corrected = contents.replace("../../../../photos/", "../../../photos/")
        if corrected != contents:
            mesh.write_text(corrected, encoding="utf-8")
        namespace_collada(mesh)

    tune_physics(world)

    existing = {plugin.get("name") for plugin in world.findall("plugin")}
    for filename, name in systems:
        if name in existing:
            continue
        ET.SubElement(world, "plugin", {"filename": filename, "name": name})

    prepared = SOURCE_WORLD.with_name(prepared_name)
    ET.ElementTree(root).write(prepared, encoding="unicode")
    return str(prepared)


