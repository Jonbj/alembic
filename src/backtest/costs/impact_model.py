"""Square-root market impact model (Almgren-Chriss inspired)."""
import math


class SquareRootImpactModel:
    """Impact (bps) = k * sqrt(order_usd / adv_usd) * 10000.

    Calibrated from literature: k=10 gives ~5bps for 0.25% of ADV order.
    Refs: Almgren & Chriss (2000), Kissell (2013).
    """

    def __init__(self, k: float = 10.0) -> None:
        self.k = k

    def impact_bps(self, order_usd: float, adv_usd: float) -> float:
        """Return one-way market impact in basis points.

        Args:
            order_usd: size of order in USD
            adv_usd: 20-day average daily volume in USD
        """
        if adv_usd <= 0:
            return 0.0
        participation = order_usd / adv_usd
        return self.k * math.sqrt(participation) * 100  # bps
