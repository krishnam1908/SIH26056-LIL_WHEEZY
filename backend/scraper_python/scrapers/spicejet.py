"""SpiceJetScraper - Google Flights via Apify.

Runs a Google Flights Actor on the Apify platform (``apify-client``) and maps
its itineraries into the raw fare shape consumed by ``normalize_raw_fare``.

The previous direct SpiceJet engine (spicejet.com ``/api/v3/search/availability``
via ``curl_cffi`` impersonation) was dropped because the edge WAF made it too
unreliable. Google Flights data comes from Apify instead, so there is no local
browser/proxy infrastructure and the source of truth is a stable third-party
scraper.

Default Actor (most maintained / best documented one-way output with a flat
per-flight view and explicit ``best_flights`` / ``other_flights`` arrays):

    johnvc/google-flights-data-scraper-flight-and-price-search

Alternative that is also supported by the input builder (config ``actor_id``):

    canadesk/google-flights

Every itinerary returned by the Actor is filtered down to SpiceJet-only flights
(marketing airline code ``SG``, name containing "SpiceJet", or a ``SG<number>``
flight number) and converted to one raw fare per itinerary:

    origin, destination, travelDate, airline="SpiceJet", flightNumber,
    fareClass, baseFare, taxes, udf, convenienceFee, totalFare, currency,
    availability

Google Flights only exposes an all-in price, so ``baseFare`` mirrors
``totalFare`` and ``taxes``/``udf``/``convenienceFee`` are left empty (None/0);
the components still reconcile with the total (base + 0 == total).
"""

import inspect
import os
import re
from datetime import timedelta

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError, ApifyClientError

from ..services.fare_normalizer import normalize_raw_fare
from ..utils.date_utils import format_utc_date
from ..utils.logger import logger
from ..utils.retry import NonRetriableError
from .base import BaseScraper

DEFAULT_ACTOR_ID = "johnvc/google-flights-data-scraper-flight-and-price-search"
DEFAULT_CURRENCY = "INR"

DEFAULT_CONFIG = {
    "actor_id": DEFAULT_ACTOR_ID,
    "currency": DEFAULT_CURRENCY,
    "adults": 1,
    "children": 0,
    "infants": 0,
    "hl": "en",
    "gl": "in",
    "max_pages": 1,
    # Optional Actor filters (left unset = no filter on that dimension).
    "max_stops": None,
    "airlines": None,
    # Apify client behaviour.
    "apify_wait_secs": 60,      # how long .call() waits for the run before polling
    "apify_timeout_secs": None,  # hard timeout for the whole run (None = platform default)
    "apify_token": None,         # falls back to the APIFY_TOKEN env var
}

# Transport-level failures from the Apify client (retried by BaseScraper).
# ``ApifyApiError`` is the base for all errors returned by the Apify API;
# ``ApifyClientError`` is the base for all client-side failures, so a
# ``except`` on either (or both) covers every Apify-request failure without
# depending on names that differ between apify-client versions.
_APIFY_ERRORS = (
    ApifyClientError,
    ApifyApiError,
)

_FLIGHT_NO_RE = re.compile(r"^SG\s*-?\s*(\d+)")
_SG_CODE_RE = re.compile(r"(?:^|[\s,/-])SG(?=$|[\s,/-]|\d)")


def _default_config():
    return dict(DEFAULT_CONFIG)


def _normalize_points(points):
    """3-letter IATA route code consumed by Google Flights."""
    s = str(points or "").upper().strip()
    if not s:
        raise NonRetriableError("SpiceJetScraper: route point is required")
    if len(s) != 3 or not s.isalnum():
        raise NonRetriableError(f"SpiceJetScraper: invalid IATA-like code '{s}'")
    return s


def _stringify_alias(obj, keys):
    """Return the first truthy string among multiple field aliases."""
    for key in keys:
        value = obj.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _is_spicejet(itinerary):
    """True when an itinerary is marketed and/or operated by SpiceJet.

    Matches the airline code ``SG``, any airline name containing
    "SpiceJet" / "SpiceXpress", or a flight number shaped like ``SG123`` /
    ``SG 123`` / ``SG-123``. Checks both the itinerary-level fields and every
    leg (so SpiceJet-marketed connections survive).
    """
    if not isinstance(itinerary, dict):
        return False

    haystack = []
    for key in (
        "airline",
        "airlines",
        "marketing_airline",
        "operating_airline",
        "airline_name",
        "airlineName",
        "flight_number",
        "flightNumber",
        "flight_no",
    ):
        value = itinerary.get(key)
        if value is not None:
            haystack.append(str(value))

    for leg in itinerary.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        for key in (
            "airline",
            "airlines",
            "marketing_airline",
            "operating_airline",
            "airline_name",
            "airlineName",
            "flight_number",
            "flightNumber",
            "flight_no",
        ):
            value = leg.get(key)
            if value is not None:
                haystack.append(str(value))

    text = " ".join(haystack).upper()
    if "SPICEJET" in text or "SPICEXPRESS" in text:
        return True
    if _SG_CODE_RE.search(text):
        return True
    return bool(_FLIGHT_NO_RE.match(text.strip()))


def _extract_flight_number(itinerary):
    """Flight number of the first leg, or the itinerary-level value."""
    legs = itinerary.get("legs") if isinstance(itinerary.get("legs"), list) else []
    if legs and isinstance(legs[0], dict):
        found = _stringify_alias(legs[0], ("flight_number", "flightNumber", "flight_no"))
        if found:
            return found
    return _stringify_alias(
        itinerary, ("flight_number", "flightNumber", "flight_no")
    )


def _extract_fare_class(itinerary):
    """Cabin/travel class of the first leg (e.g. "Economy")."""
    legs = itinerary.get("legs") if isinstance(itinerary.get("legs"), list) else []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        found = _stringify_alias(leg, ("travel_class", "travelClass", "cabin", "cabin_class"))
        if found:
            return found.upper()
    return _stringify_alias(itinerary, ("travel_class", "travelClass", "cabin", "cabin_class"))


def _extract_price(itinerary):
    """All-in price of an itinerary as a number (Google Flights total)."""
    value = itinerary.get("price")
    if value is None:
        value = _stringify_alias(itinerary, ("total_price", "totalPrice", "price_amount"))
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flight_price_is_valid(price):
    return price is not None and price >= 0


def _iter_itineraries(item):
    """Yield flight/dict records from one dataset item (Actor-page).

    Primary shape (johnvc actor): ``best_flights`` + ``other_flights`` arrays.
    Fallback shape (other actors / generic): a token with ``price`` plus an
    airline-flavoured field is treated as one itinerary itself.
    """
    if not isinstance(item, dict):
        return
    for key in ("best_flights", "bestFlights", "flights", "itineraries"):
        bucket = item.get(key) or []
        if isinstance(bucket, list):
            for candidate in bucket:
                if isinstance(candidate, dict) and candidate.get("price") is not None:
                    yield candidate
    for key in ("other_flights", "otherFlights", "otherFlightsRecommendation"):
        bucket = item.get(key) or []
        if isinstance(bucket, list):
            for candidate in bucket:
                if isinstance(candidate, dict) and candidate.get("price") is not None:
                    yield candidate
    # Generic fallback: the item is itself a single flight/fare record.
    if "price" in item and (
        "airline" in item or "airlines" in item or "flight_number" in item or "flightNumber" in item
    ):
        yield item


class SpiceJetHttpError(IOError):
    """Failure talking to Apify / the Google Flights Actor run."""

    def __init__(self, message, run=None):
        super().__init__(message)
        self.run = run


class SpiceJetScraper(BaseScraper):
    def __init__(self, config=None):
        merged = _default_config()
        merged.update(config or {})
        super().__init__({"source": "spicejet", **merged})
        self.actor_id = str(self.config.get("actor_id") or DEFAULT_ACTOR_ID)
        self.currency = str(self.config.get("currency") or DEFAULT_CURRENCY)

    # ------------------------------------------------------------------ config

    def _resolve_token(self):
        """APIFY_TOKEN from the config object or the ``APIFY_TOKEN`` env var."""
        token = self.config.get("apify_token") or os.environ.get("APIFY_TOKEN")
        token = str(token or "").strip()
        if not token:
            raise NonRetriableError(
                "SpiceJetScraper: APIFY_TOKEN is missing. Set the APIFY_TOKEN "
                "environment variable (or pass config['apify_token'])."
            )
        return token

    def build_actor_input(self, origin, destination, travel_date):
        """One-way Google Flights Actor input for the configured actor_id."""
        travel_date_str = format_utc_date(travel_date)
        if "canadesk" in self.actor_id.lower():
            return {
                "operation": "gfi",
                "departureIATA": origin,
                "arrivalIATA": [destination],
                "departureDate": travel_date_str,
                "adults": self.config.get("adults", 1),
                "children": self.config.get("children", 0),
                "seatclass": str(self.config.get("seatclass", "1")),
                "stops": str(self.config.get("stops", "")),
                "currency": self.currency,
                "locale": self.config.get("hl", "en-US"),
                "maximum": 10,
                "retries": self.config.get("retries", 1),
                "delay": self.config.get("delay", 3),
            }

        run_input = {
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": travel_date_str,
            "adults": self.config.get("adults", 1),
            "children": self.config.get("children", 0),
            "infants": self.config.get("infants", 0),
            "currency": self.currency,
            "hl": self.config.get("hl", "en"),
            "gl": self.config.get("gl", "in"),
            "exclude_basic": False,
            "fetch_booking_options": False,
            "max_pages": self.config.get("max_pages", 1),
        }
        if self.config.get("max_stops") is not None:
            run_input["max_stops"] = int(self.config["max_stops"])
        if self.config.get("airlines"):
            run_input["airlines"] = str(self.config["airlines"])
        return run_input

    # --------------------------------------------------------------- transport

    def _call_actor(self, token, run_input):
        """Start the Actor run, wait for it and fetch its dataset iterator.

        :returns: ``(run, dataset_iterator)`` where run is the Apify run dict.
        :raises SpiceJetHttpError: on transport/API failures or a non-successful
            run status (retried by BaseScraper).
        """
        try:
            client = ApifyClient(token)
            actor_client = client.actor(self.actor_id)

            # apify-client changed its call() signature over versions: v1.x used
            # ``wait_secs`` (int seconds) + ``timeout`` (int seconds); >=3.x
            # renamed them to ``wait_duration`` / ``timeout`` as ``timedelta``.
            # Build the kwargs from the actual signature so both work.
            params = set(inspect.signature(actor_client.call).parameters)
            apify_wait_secs = int(self.config.get("apify_wait_secs") or 60)
            apify_timeout_secs = self.config.get("apify_timeout_secs")

            call_kwargs = {"run_input": run_input}
            if "wait_duration" in params:
                call_kwargs["wait_duration"] = timedelta(seconds=apify_wait_secs)
                if apify_timeout_secs is not None:
                    call_kwargs["timeout"] = timedelta(seconds=int(apify_timeout_secs))
            else:
                call_kwargs["wait_secs"] = apify_wait_secs
                if apify_timeout_secs is not None:
                    call_kwargs["timeout"] = int(apify_timeout_secs)

            run = actor_client.call(**call_kwargs)
            if not isinstance(run, dict):
                raise SpiceJetHttpError(
                    "SpiceJetScraper: Apify actor call returned no run information"
                )

            status = run.get("status")
            if status != "SUCCEEDED":
                detail = (
                    _stringify_alias(run, ("statusMessage", "errorMessage"))
                    or _run_error_detail(run)
                    or "no detail provided"
                )
                raise SpiceJetHttpError(
                    f"SpiceJetScraper: Apify run {run.get('id')} -> {status}: {detail}",
                    run=run,
                )

            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                raise SpiceJetHttpError(
                    "SpiceJetScraper: Apify run succeeded but has no default dataset",
                    run=run,
                )

            items = client.dataset(dataset_id).iterate_items()
            return run, items
        except SpiceJetHttpError:
            raise
        except NonRetriableError:
            raise
        except _APIFY_ERRORS as err:
            raise SpiceJetHttpError(f"SpiceJetScraper: Apify client error: {err}") from err
        except Exception as err:
            raise SpiceJetHttpError(f"SpiceJetScraper: unexpected Apify error: {err}") from err

    # ---------------------------------------------------------------- mapping

    @staticmethod
    def _to_raw_fare(itinerary, origin, destination, travel_date, currency, run, item):
        """Map one SpiceJet itinerary to the raw shape for ``normalize_raw_fare``.

        Google Flights advertises a single all-in price; there is no
        base/tax/udf/convenience computation available, so the total is placed
        in ``totalFare`` (and mirrored in ``baseFare`` with zero taxes) so the
        components always reconcile with the total.
        """
        price = _extract_price(itinerary)
        return {
            "origin": origin,
            "destination": destination,
            "travelDate": travel_date,
            "airline": "SpiceJet",
            "flightNumber": _extract_flight_number(itinerary),
            "fareClass": _extract_fare_class(itinerary),
            "baseFare": price,
            "taxes": 0,
            "udf": None,
            "convenienceFee": None,
            "totalFare": price,
            "currency": currency,
            "availability": "AVAILABLE",
            "metric": {
                "platform": "apify-google-flights",
                "actorId": None,  # filled in below by the caller
                "runId": run.get("id") if isinstance(run, dict) else None,
                "itinerary": itinerary,
                "searchParameters": item.get("search_parameters") if isinstance(item, dict) else None,
                "currency": currency,
            },
        }

    def map_items_to_raw(self, items, origin, destination, travel_date, run):
        """Filter Actor dataset items down to SpiceJet itineraries."""
        raw_flights = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parameters = item.get("search_parameters")
            currency = (
                _stringify_alias(parameters, ("currency",)) if isinstance(parameters, dict) else None
            )
            currency = currency or item.get("currency") or self.currency

            for itinerary in _iter_itineraries(item):
                if not _is_spicejet(itinerary):
                    continue
                price = _extract_price(itinerary)
                if not _flight_price_is_valid(price):
                    continue
                raw = self._to_raw_fare(
                    itinerary, origin, destination, travel_date, currency, run, item
                )
                raw["metric"]["actorId"] = self.actor_id
                raw_flights.append(raw)
        return raw_flights

    # ------------------------------------------------------------ public API

    def search_flights(self, params):
        origin = _normalize_points(params.get("origin"))
        destination = _normalize_points(params.get("destination"))
        if origin == destination:
            raise NonRetriableError("SpiceJetScraper: origin and destination must differ")
        if not params.get("travelDate"):
            raise NonRetriableError("SpiceJetScraper: travelDate is required")

        token = self.config.get("apify_token") or os.environ.get("APIFY_TOKEN")
        token = str(token or "").strip()

        # Token-free direct HTTP mode (No Playwright required)
        if not token or self.config.get("engine") == "direct":
            from ..services.http_direct_scraper import scrape_direct_http
            date_str = format_utc_date(params["travelDate"])
            return scrape_direct_http("SpiceJet", origin, destination, date_str)

        run_input = self.build_actor_input(origin, destination, params["travelDate"])

        logger.info(
            "SpiceJetScraper: calling Google Flights actor",
            {"actor": self.actor_id, "route": f"{origin}-{destination}", "date": run_input.get("outbound_date") or run_input.get("departureDate")},
        )
        run, items = self._call_actor(token, run_input)

        raw_flights = self.map_items_to_raw(
            items, origin, destination, params["travelDate"], run
        )
        if not raw_flights:
            logger.warn(
                "SpiceJetScraper: no SpiceJet flights found",
                {"route": f"{origin}-{destination}", "runId": run.get("id")},
            )
        return raw_flights

    def normalize_flight(self, raw_flight, context):
        fare = normalize_raw_fare(raw_flight, context)
        metric = raw_flight.get("metric")
        if isinstance(metric, dict):
            fare["metric"] = metric
        return fare


def _run_error_detail(run):
    """Best-effort human-readable error from an Apify run dict."""
    if not isinstance(run, dict):
        return None
    error = run.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("errorMessage")
        if message:
            return str(message)
    data = run.get("data")
    if isinstance(data, dict) and data.get("error"):
        message = data["error"].get("message") if isinstance(data["error"], dict) else None
        if message:
            return str(message)
    return None


__all__ = ["SpiceJetScraper", "DEFAULT_CONFIG", "DEFAULT_ACTOR_ID", "SpiceJetHttpError"]