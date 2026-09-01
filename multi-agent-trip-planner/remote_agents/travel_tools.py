"""Mock travel tools for the three specialist agents.

In a real deployment these tools would query live systems (a GDS / flight
aggregator, a hotel booking API, a points-of-interest database). Here they
return fixed, in-memory data so the demo is deterministic and offline: each
specialist does NOT invent flights, hotels or attractions with the LLM — it
looks them up through a tool, which is how it would work in production.

The tools are exposed to the Strands `Agent` (and, through it, published as the
A2A agent card's skills) via the `@tool` decorator; the model decides which one
to call based on their descriptions.
"""

from strands import tool

from common.logging_config import setup_logging

logger = setup_logging("remote_agents.log", "remote_agents")

# ─────────────────────────────────────────────────────────────────────────────
# In-memory "databases" — fixed sample data keyed by destination.
# Destinations are matched case-insensitively on their key (e.g. "barcelona").
# ─────────────────────────────────────────────────────────────────────────────
_FLIGHTS: dict[str, list[str]] = {
    "barcelona": [
        "Iberia IB6845 — Buenos Aires (EZE) -> Barcelona (BCN), direct, 12h 40m, USD 980 round trip.",
        "Level LV1503 — Buenos Aires (EZE) -> Barcelona (BCN), direct, 12h 55m, USD 910 round trip.",
        "Lufthansa LH510 — Buenos Aires (EZE) -> Barcelona (BCN) via Frankfurt, 17h 10m, USD 840 round trip.",
    ],
    "lisbon": [
        "TAP TP122 — Buenos Aires (EZE) -> Lisbon (LIS), direct, 11h 20m, USD 890 round trip.",
        "Iberia IB6842 — Buenos Aires (EZE) -> Lisbon (LIS) via Madrid, 15h 05m, USD 790 round trip.",
    ],
    "tokyo": [
        "ANA NH802 — Buenos Aires (EZE) -> Tokyo (HND) via Sao Paulo, 30h 15m, USD 1,720 round trip.",
        "Qatar QR772 — Buenos Aires (EZE) -> Tokyo (HND) via Doha, 32h 40m, USD 1,540 round trip.",
    ],
}

_HOTELS: dict[str, list[str]] = {
    "barcelona": [
        "Hotel Gotico — 4 stars, in the Gothic Quarter, USD 130/night, breakfast included.",
        "Apartments Eixample — 3 stars, near Passeig de Gracia, USD 95/night.",
        "Barcelona Beach Hostel — 2 stars, in Barceloneta, USD 45/night.",
    ],
    "lisbon": [
        "Hotel Alfama Terrace — 4 stars, historic center, USD 120/night, rooftop terrace.",
        "Baixa Guesthouse — 3 stars, downtown, USD 80/night, breakfast included.",
    ],
    "tokyo": [
        "Shinjuku Grand Hotel — 4 stars, in Shinjuku, USD 160/night.",
        "Asakusa Ryokan — traditional inn near Senso-ji, USD 110/night.",
    ],
}

_HIGHLIGHTS: dict[str, list[str]] = {
    "barcelona": [
        "Sagrada Familia (Gaudi's basilica).",
        "Park Guell and its mosaics.",
        "The Gothic Quarter and Barcelona Cathedral.",
        "La Rambla and La Boqueria market.",
        "Barceloneta beach.",
        "Casa Batllo and Casa Mila (La Pedrera).",
    ],
    "lisbon": [
        "Belem Tower and the Jeronimos Monastery.",
        "The Alfama district and its viewpoints.",
        "Tram 28 through the historic center.",
        "Praca do Comercio.",
        "A day trip to Sintra.",
    ],
    "tokyo": [
        "Senso-ji temple in Asakusa.",
        "Shibuya crossing and Shibuya district.",
        "The Meiji shrine and Yoyogi park.",
        "Akihabara (electronics and anime).",
        "A day trip to Nikko or Hakone.",
    ],
}

_NO_FLIGHTS = "No flight options were found for that route in our system."
_NO_HOTELS = "No hotel options were found for that destination in our system."
_NO_HIGHLIGHTS = "No points of interest were found for that destination in our system."


def _normalize(destination: str) -> str:
    """Reduce a destination to its lookup key (lowercase, trimmed, first word).

    Keeps the demo forgiving: "Barcelona, Spain" and "barcelona" both map to the
    same key.
    """
    return destination.strip().lower().split(",")[0].split()[0] if destination.strip() else ""


@tool
def search_flights(origin: str, destination: str, month: str) -> str:
    """Search available flight options for a route and travel month.

    Args:
        origin: departure city, e.g. "Buenos Aires".
        destination: arrival city, e.g. "Barcelona".
        month: travel month or date, e.g. "March".

    Returns:
        A newline-separated list of flight options, or a not-found message.
    """
    logger.info(
        "TOOL CALL: search_flights(origin=%r, destination=%r, month=%r)",
        origin,
        destination,
        month,
    )
    options = _FLIGHTS.get(_normalize(destination))
    if not options:
        return _NO_FLIGHTS
    lines = "\n".join(f"- {opt}" for opt in options)
    return (
        f"Flight options from {origin} to {destination} in {month}:\n{lines}"
    )


@tool
def search_hotels(destination: str, nights: int) -> str:
    """Search available hotel options for a destination and number of nights.

    Args:
        destination: the destination city, e.g. "Barcelona".
        nights: number of nights of the stay, e.g. 5.

    Returns:
        A newline-separated list of hotel options, or a not-found message.
    """
    logger.info(
        "TOOL CALL: search_hotels(destination=%r, nights=%r)", destination, nights
    )
    options = _HOTELS.get(_normalize(destination))
    if not options:
        return _NO_HOTELS
    lines = "\n".join(f"- {opt}" for opt in options)
    return f"Hotel options in {destination} for {nights} nights:\n{lines}"


@tool
def get_destination_highlights(destination: str) -> str:
    """Return the main points of interest of a destination.

    Args:
        destination: the destination city, e.g. "Barcelona".

    Returns:
        A newline-separated list of highlights, or a not-found message.
    """
    logger.info("TOOL CALL: get_destination_highlights(destination=%r)", destination)
    highlights = _HIGHLIGHTS.get(_normalize(destination))
    if not highlights:
        return _NO_HIGHLIGHTS
    lines = "\n".join(f"- {item}" for item in highlights)
    return f"Points of interest in {destination}:\n{lines}"
