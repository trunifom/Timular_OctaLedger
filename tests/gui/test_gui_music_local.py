"""GUI tests: a cube face plays a local folder (repeat, shuffle); the holder can let it run on."""

from pathlib import Path

from tests.conftest import RunningApi
from tests.gui.test_gui_control import FACES, music_setup
from tests.gui.test_gui_devices_catalog import open_page
from tests.unit.test_local_player import make_album


def test_a_face_gets_a_local_folder_with_repeat_and_shuffle(
    api_server: RunningApi, tmp_path: Path
) -> None:
    did, _ = music_setup(api_server)
    album = make_album(tmp_path)
    at = open_page(api_server, FACES)
    base = f"faces_music_{did}_1"
    assert at.button(key=f"{base}_pick_file").help and at.button(key=f"{base}_pick_folder").help
    at.text_input(key=f"{base}_link").input(str(album)).run()
    assert any("Lokale Datei, Ordner oder Playlist" in s.value for s in at.success)
    assert at.segmented_control(key=f"{base}_repeat").help and at.toggle(key=f"{base}_shuffle").help
    at.segmented_control(key=f"{base}_repeat").set_value("one")
    at.toggle(key=f"{base}_shuffle").set_value(True)
    at.text_input(key=f"{base}_label").input("Album Endlos").run()
    at.button(key=f"{base}_save").click().run()
    assert not at.exception
    steps = api_server.context.integrations.get_steps(did, 1)  # type: ignore[union-attr]
    play = next(s for s in steps if s.params["action"] == "play_path")
    assert play.params["path"] == str(album)
    assert play.params["repeat"] == "one" and play.params["shuffle"] is True


def test_a_wrong_folder_is_refused_when_the_title_is_saved(
    api_server: RunningApi, tmp_path: Path
) -> None:
    did, _ = music_setup(api_server)
    at = open_page(api_server, FACES)
    base = f"faces_music_{did}_1"
    at.text_input(key=f"{base}_link").input(str(tmp_path / "gibt-es-nicht")).run()
    at.text_input(key=f"{base}_label").input("Nichts").run()
    at.button(key=f"{base}_save").click().run()
    assert any("gibt es nicht" in e.value for e in at.error)
    assert api_server.client.devices()[0]["actions"] == {}


def test_the_holder_can_let_the_music_run_on(api_server: RunningApi) -> None:
    did, _ = music_setup(api_server)
    at = open_page(api_server, FACES)
    options = [str(o) for o in at.selectbox(key=f"music_base_{did}").options]
    assert any("weiterlaufen" in o for o in options)
    at.selectbox(key=f"music_base_{did}").select("continue").run()
    at.button(key=f"music_settings_save_{did}").click().run()
    assert api_server.client.music_settings(did)["base_action"] == "continue"
