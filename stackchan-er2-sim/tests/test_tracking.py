from stackchan_er2_sim.tracking import face_to_pose


def test_center_face_maps_to_neutral_pose() -> None:
    assert face_to_pose(0.5, 0.5) == (0.0, 45.0)


def test_face_mapping_is_bounded() -> None:
    assert face_to_pose(-20, -20) == (40.0, 80.0)
    assert face_to_pose(20, 20) == (-40.0, 10.0)
