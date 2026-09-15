"""Tests del estado de ejecución y de los chequeos previos."""

import os
import socket
import time

from minerpro import preflight, run_state


class TestRunState:
    def test_guardar_leer_y_limpiar(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MINERPRO_HOME", str(tmp_path))
        state = run_state.RunState(
            pid=os.getpid(),
            profile="default",
            coin="XMR",
            pool="pool.supportxmr.com:3333",
            wallet="W",
            engine="xmrig",
            port=18080,
            started_at=time.time(),
            log_path=str(tmp_path / "x.log"),
        )
        run_state.save(state)
        loaded = run_state.load()
        assert loaded is not None
        assert loaded.pool == state.pool
        assert run_state.current() is not None  # el pid actual está vivo
        assert loaded.uptime_seconds >= 0
        run_state.clear()
        assert run_state.load() is None

    def test_pid_muerto_limpia_el_estado(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MINERPRO_HOME", str(tmp_path))
        state = run_state.RunState(
            pid=999_999_999,
            profile="default",
            coin="XMR",
            pool="p:1",
            wallet="W",
            engine="xmrig",
            port=1,
            started_at=0.0,
            log_path="",
        )
        run_state.save(state)
        assert run_state.current() is None
        assert run_state.load() is None

    def test_marcador_de_parada(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MINERPRO_HOME", str(tmp_path))
        assert run_state.stop_requested() is False
        run_state.request_stop()
        assert run_state.stop_requested() is True
        run_state.clear()
        assert run_state.stop_requested() is False

    def test_archivo_corrupto_no_rompe(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MINERPRO_HOME", str(tmp_path))
        run_state.state_path().write_text("{no es json")
        assert run_state.load() is None


class TestPreflight:
    def test_pool_con_url_invalida(self):
        ch = preflight.check_pool("sin-puerto")
        assert ch.ok is False and ch.fatal is True

    def test_pool_inalcanzable_no_es_fatal(self):
        ch = preflight.check_pool("127.0.0.1:9", timeout=1.0)
        assert ch.ok is False and ch.fatal is False

    def test_puerto_ocupado_se_detecta(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            ch = preflight.check_port_free(port)
        assert ch.ok is False
        assert str(port) in ch.detail

    def test_puerto_libre(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        assert preflight.check_port_free(port).ok is True

    def test_binario_inexistente_es_fatal(self):
        ch = preflight.check_binary(__import__("pathlib").Path("/no/existe/xmrig"))
        assert ch.ok is False and ch.fatal is True

    def test_binario_ejecutable(self):
        ch = preflight.check_binary(__import__("pathlib").Path("/bin/echo"))
        assert ch.ok is True

    def test_minero_externo_no_necesita_binario(self):
        assert preflight.check_binary(None).ok is True

    def test_run_all_solo_bloquea_por_fatales(self):
        ok, _ = preflight.run_all([preflight.Check("aviso", False, "d")])
        assert ok is True
        ok, _ = preflight.run_all([preflight.Check("grave", False, "d", fatal=True)])
        assert ok is False
