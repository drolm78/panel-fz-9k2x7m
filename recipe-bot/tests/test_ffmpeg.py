from pathlib import Path

from recipe_bot.pipeline.audio import cmd_extraer_audio
from recipe_bot.pipeline.frames import cmd_escenas, cmd_intervalo

VIDEO = Path("/tmp/v.mp4")
SALIDA = Path("/tmp/out")


def test_escenas_limita_cuadros_y_escala():
    cmd = cmd_escenas(VIDEO, SALIDA, 16, 640)
    vf = cmd[cmd.index("-vf") + 1]
    assert "scene,0.25" in vf and "scale=640:-2" in vf
    assert cmd[cmd.index("-frames:v") + 1] == "16"


def test_intervalo_reparte_los_cuadros_a_lo_largo_del_video():
    # 16 cuadros en 45 s -> ~0.36 fps
    vf = cmd_intervalo(VIDEO, SALIDA, 16, 640, 45.0)
    assert "fps=0.3556" in vf[vf.index("-vf") + 1]


def test_intervalo_no_divide_entre_cero_en_videos_sin_duracion():
    cmd = cmd_intervalo(VIDEO, SALIDA, 16, 640, 0.0)
    assert "fps=16.0000" in cmd[cmd.index("-vf") + 1]


def test_audio_sale_mono_a_16k_que_es_lo_que_whisper_usa():
    cmd = cmd_extraer_audio(VIDEO, SALIDA / "a.mp3")
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert "-vn" in cmd
