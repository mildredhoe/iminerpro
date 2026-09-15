"""Tests del estimador de rentabilidad y de las fuentes de datos."""

import pytest

from minerpro import market


def fake_get(responses: dict[str, dict]):
    def _get(url: str) -> dict:
        for fragment, payload in responses.items():
            if fragment in url:
                return payload
        raise RuntimeError(f"sin datos para {url}")
    return _get


MONEROBLOCKS = {
    "difficulty": 817089574663,
    "height": 3762714,
    "hashrate": 6809079788.85,
    "last_reward": 622778320000,
}
BLOCKCHAIR = {
    "data": {"difficulty": 817089574663, "hashrate_24h": 6809079788, "best_block_height": 3762713}
}
XMRCHAIN = {"data": {"difficulty": 817089574663, "height": 3762713}}
COINGECKO = {"monero": {"usd": 500.0}, "bitcoin": {"usd": 78000.0}}


class TestNetwork:
    def test_usa_moneroblocks_y_calcula_recompensa(self):
        net = market.fetch_network(fake_get({"moneroblocks": MONEROBLOCKS}))
        assert net.source == "moneroblocks.info"
        assert net.hashrate_hps == pytest.approx(6809079788.85)
        assert net.block_reward == pytest.approx(0.62277832)
        assert net.blocks_per_day == 720.0

    def test_cae_a_blockchair(self):
        net = market.fetch_network(fake_get({"blockchair": BLOCKCHAIR}))
        assert net.source == "blockchair.com"
        assert net.block_reward is None

    def test_cae_a_xmrchain(self):
        net = market.fetch_network(fake_get({"xmrchain": XMRCHAIN}))
        assert net.source == "xmrchain.net"
        assert net.hashrate_hps == pytest.approx(817089574663 / 120.0)

    def test_sin_fuentes_avisa(self):
        with pytest.raises(RuntimeError, match="sin datos de red"):
            market.fetch_network(fake_get({}))

    def test_precios(self):
        prices = market.fetch_prices(fake_get({"coingecko": COINGECKO}))
        assert prices.coin_usd == 500.0
        assert prices.btc_usd == 78000.0


class TestNiceHashMarket:
    ALGORITHMS = {  # noqa: RUF012
        "miningAlgorithms": [
            {"algorithm": "RANDOMXMONERO", "marketFactor": "1000000000.00000000",
             "displayMarketFactor": "GH"},
        ]
    }
    ORDERS = {  # noqa: RUF012
        "list": [
            {"price": "0.42", "rigsCount": 5, "acceptedCurrentSpeed": "0.001"},
            {"price": "0.39", "rigsCount": 0, "acceptedCurrentSpeed": "0.0"},
            {"price": "0.45", "rigsCount": 3, "acceptedCurrentSpeed": "0.002"},
        ]
    }

    def test_factor_de_mercado(self):
        algo = market.nicehash_algorithm("randomxmonero", fake_get({"algorithms": self.ALGORITHMS}))
        assert float(algo["marketFactor"]) == 1e9

    def test_mejor_precio_ignora_ordenes_vacias(self):
        price, count = market.nicehash_best_price("RANDOMXMONERO", fake_get({"orders/active2": self.ORDERS}))
        assert price == pytest.approx(0.42)
        assert count == 2

    def test_algoritmo_desconocido(self):
        with pytest.raises(RuntimeError):
            market.nicehash_algorithm("NOEXISTE", fake_get({"algorithms": self.ALGORITHMS}))


class TestEstimate:
    NET = market.NetworkStats(
        difficulty=817089574663,
        hashrate_hps=6.8e9,
        block_reward=0.62277832,
        height=3762714,
        source="test",
    )
    PRICES = market.Prices(coin_usd=500.0, btc_usd=78000.0, source="test")

    def test_cuentas_del_arriendo(self):
        est = market.estimate(
            speed_units=1.0,
            price_btc_per_unit_day=0.01,
            days=1.0,
            pool_fee_percent=0.6,
            market_factor_hps=1e9,
            network=self.NET,
            prices=self.PRICES,
            block_reward=0.62277832,
        )
        assert est.speed_hps == pytest.approx(1e9)
        assert est.network_share == pytest.approx(1 / 6.8)
        assert est.coins_mined == pytest.approx(65.545586, abs=1e-4)
        assert est.cost_usd == pytest.approx(780.0)
        assert est.revenue_usd == pytest.approx(32772.79, abs=0.5)
        assert est.net_usd == pytest.approx(31992.79, abs=0.5)
        assert est.profitable is True
        assert est.break_even_btc_per_unit_day == pytest.approx(0.420164, abs=1e-5)

    def test_arriendo_caro_da_perdida(self):
        est = market.estimate(1.0, 1.0, 1.0, 0.6, 1e9, self.NET, self.PRICES, 0.62277832)
        assert est.profitable is False
        assert est.net_usd < 0

    def test_el_fee_reduce_lo_minado(self):
        zero = market.estimate(1.0, 0.01, 1.0, 0.0, 1e9, self.NET, self.PRICES, 0.62277832)
        one = market.estimate(1.0, 0.01, 1.0, 1.0, 1e9, self.NET, self.PRICES, 0.62277832)
        assert one.coins_mined == pytest.approx(zero.coins_mined * 0.99)

    def test_valida_entradas(self):
        with pytest.raises(ValueError):
            market.estimate(1.0, 0.01, 1.0, 0.6, 0, self.NET, self.PRICES, 0.6)
        with pytest.raises(ValueError):
            market.estimate(1.0, 0.01, 1.0, 0.6, 1e9, self.NET, market.Prices(1, 0, "t"), 0.6)

    def test_formato_de_hashrate(self):
        assert market.format_hashrate(1e9) == "1.000 GH/s"
        assert market.format_hashrate(6.8e9) == "6.800 GH/s"
        assert market.format_hashrate(1000) == "1.000 kH/s"
