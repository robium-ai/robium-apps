from stackchan_er2_sim.router import route


def test_local_router_covers_first_run_commands() -> None:
    assert route("look left").yaw == 30
    assert route("please look right").yaw == -30
    assert route("nod yes").action == "nod"
    assert route("show what you can do").action == "showcase"
    assert route("track me").tracking == "start"
    assert route("stop tracking").tracking == "stop"


def test_stop_tracking_wins_over_generic_tracking() -> None:
    command = route("Stack Chan, stop tracking me")
    assert command.tracking == "stop"
    assert command.action == "center"
