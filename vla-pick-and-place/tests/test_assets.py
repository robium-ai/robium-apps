"""The SO-101 asset must be the menagerie one, and must load under our MuJoCo."""
import mujoco
import pytest

from vla_pick_and_place.config import SCENE_XML, SCENE_CAM, WRIST_CAM


def test_scene_xml_exists():
    assert SCENE_XML.is_file(), f"missing MJCF at {SCENE_XML} — run `make assets`"


def test_menagerie_asset_is_vendored():
    """`scene_pick.xml` is OURS and tracked in git; the menagerie files it
    `include`s are vendored by `make assets` and gitignored. A fresh clone
    therefore has a non-empty assets dir with no robot in it, and every
    scene load fails with a bare `XML Error: Error opening file
    'scene_box.xml'`. Assert on a menagerie-owned file so the failure names
    its own fix.
    """
    so101 = SCENE_XML.parent / "so101.xml"
    assert so101.is_file(), (
        f"menagerie SO-101 not vendored at {so101} — run `make assets`. "
        "A non-empty assets dir is NOT proof it ran: scene_pick.xml lives "
        "there and is tracked."
    )


def test_scene_loads_and_has_expected_actuators():
    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    # SO-101: 5 arm joints + 1 gripper.
    assert model.nu == 6, f"expected 6 actuators, got {model.nu}"


def test_scene_has_both_cameras():
    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    names = {
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_CAMERA, i)
        for i in range(model.ncam)
    }
    assert {WRIST_CAM, SCENE_CAM} <= names, f"cameras found: {names}"
