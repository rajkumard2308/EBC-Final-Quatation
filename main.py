import os
import re
import json
import csv
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

HOTEL_CODE = os.getenv(
    "IPMS_HOTEL_CODE",
    "23400"
)

OPENAPI_KEY = os.getenv(
    "IPMS_OPENAPI_KEY"
)

API_URL = (
    "https://live.ipms247.com/"
    "booking/reservation_api/listing.php"
)

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

os.makedirs(
    DATA_DIR,
    exist_ok=True
)


# ============================================================
# FRIENDLY ROOM NAMES
# ============================================================

ROOM_NAME_MAP = {
    "camper": "The Camper room",
    "camper room": "The Camper room",

    "glamper": "The Glamper room",
    "glamper room": "The Glamper room",
    "the glamper": "The Glamper room",
    "the glamper with breakfast":
        "The Glamper room",

    "surveyor": "The Surveyor room",
    "surveyor room":
        "The Surveyor room",

    "surveyor suite":
        "The Surveyor suite room",
    "surveyor suite room":
        "The Surveyor suite room",
    "surveyor suite continental plan":
        "The Surveyor suite room",

    "zenith":
        "The Zenith luxury cottage",
    "zenith luxury cottage":
        "The Zenith luxury cottage",
    "zenith luxury cottage with breakfast":
        "The Zenith luxury cottage",

    "twin luxury cottage":
        "The Twin luxury cottage",
    "twin luxury cottage continental plan":
        "The Twin luxury cottage",

    "andrew's villa":
        "The Villa",
    "andrews villa":
        "The Villa",
    "villa":
        "The Villa",
}


ROOM_ORDER = [
    "The Camper room",
    "The Glamper room",
    "The Surveyor room",
    "The Surveyor suite room",
    "The Zenith luxury cottage",
    "The Twin luxury cottage",
    "The Villa",
]


# ============================================================
# SPECIAL NOTES
# ============================================================

ROOM_NOTES = {
    "The Twin luxury cottage":
        "2 Rooms next to each other",

    "The Villa":
        "2 Rooms villa",
}


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value: Any) -> date:
    """
    Convert supported date formats into date object.
    """

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):

        value = value.strip()

        formats = [
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]

        for fmt in formats:

            try:

                return datetime.strptime(
                    value,
                    fmt
                ).date()

            except ValueError:
                continue

    raise ValueError(
        f"Invalid date: {value!r}. "
        "Use DD-MM-YYYY or YYYY-MM-DD."
    )


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_int(
    value: Any,
    default: int = 0
) -> int:

    try:

        if value is None:
            return default

        return int(
            float(
                str(value).strip()
            )
        )

    except (
        ValueError,
        TypeError
    ):
        return default


def safe_float(
    value: Any,
    default: float = 0.0
) -> float:

    try:

        if value is None:
            return default

        if isinstance(
            value,
            (int, float)
        ):
            return float(value)

        text = str(value).strip()

        if not text:
            return default

        text = re.sub(
            r"[^\d.\-]",
            "",
            text
        )

        if not text:
            return default

        return float(text)

    except (
        ValueError,
        TypeError
    ):
        return default


def round_price_down_100(value: Any) -> int:
    """
    Round a customer-facing price DOWN to the nearest ₹100.

    Examples:
        11,593.00 -> 11,500
        11,530.64 -> 11,500
        12,712.00 -> 12,700
        16,243.00 -> 16,200
        32,487.00 -> 32,400
    """
    price = safe_float(value, 0)

    if price <= 0:
        return 0

    return int(price // 100) * 100


def clean_html_text(
    value: Any
) -> str:
    """
    Remove HTML tags such as <br>.
    """

    if not value:
        return ""

    text = str(value)

    text = re.sub(
        r"<br\s*/?>",
        "\n",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"<[^>]+>",
        "",
        text
    )

    return text.strip()


# ============================================================
# API KEY VALIDATION
# ============================================================

def validate_config():

    if not OPENAPI_KEY:

        raise RuntimeError(
            "IPMS_OPENAPI_KEY is missing.\n\n"
            "Create a .env file in the EBC folder:\n\n"
            "IPMS_HOTEL_CODE=23400\n"
            "IPMS_OPENAPI_KEY=YOUR_OPENAPI_KEY"
        )


# ============================================================
# ROOM NAME CLEANING
# ============================================================

def clean_room_name(
    value: Any
) -> str:

    if value is None:
        return "Unknown Room"

    name = str(value).strip()

    if not name:
        return "Unknown Room"

    prefixes = [
        r"^STAY MORE SAVE MORE\s*-\s*",
        r"^LIMITED TIME DEAL\s*!!!?\s*-\s*",
        r"^LIMITED TIME DEAL\s*-\s*",
        r"^SPECIAL OFFER\s*-\s*",
        r"^SPECIAL DEAL\s*-\s*",
        r"^PROMOTION\s*-\s*",
    ]

    for pattern in prefixes:

        name = re.sub(
            pattern,
            "",
            name,
            flags=re.IGNORECASE
        )

    return name.strip()


# ============================================================
# NORMALIZE ROOM TYPE
# ============================================================

def normalize_room_type(
    room: Dict[str, Any]
) -> str:

    # First use Roomtype_Short_code
    # because this is more reliable than Room_Name.

    short_code = str(
        room.get(
            "Roomtype_Short_code",
            ""
        )
    ).strip().lower()

    room_type = str(
        room.get(
            "Roomtype_Name",
            ""
        )
    ).strip().lower()

    room_name = str(
        room.get(
            "Room_Name",
            ""
        )
    ).strip().lower()

    room_description = str(
        room.get(
            "Room_Description",
            ""
        )
    ).strip().lower()

    combined = (
        short_code
        + " "
        + room_type
        + " "
        + room_name
        + " "
        + room_description
    )

    # --------------------------------------------------------
    # Important: check Surveyor Suite BEFORE Surveyor
    # --------------------------------------------------------

    if (
        "surveyor suite" in combined
        or "surveyor_suite" in combined
    ):
        return "The Surveyor suite room"

    if "surveyor" in combined:
        return "The Surveyor room"

    if "glamper" in combined:
        return "The Glamper room"

    if "camper" in combined:
        return "The Camper room"

    if "zenith" in combined:
        return "The Zenith luxury cottage"

    if "twin luxury" in combined:
        return "The Twin luxury cottage"

    if "twinluxury" in combined:
        return "The Twin luxury cottage"

    if "villa" in combined:
        return "The Villa"

    # Fallback exact mapping

    for key, friendly in ROOM_NAME_MAP.items():

        if key in combined:
            return friendly

    return clean_room_name(
        room.get(
            "Room_Description"
        )
        or room.get(
            "Room_Name"
        )
        or room.get(
            "Roomtype_Name"
        )
        or "Unknown Room"
    )


# ============================================================
# MEAL PLAN
# ============================================================

def detect_meal_plan(
    room: Dict[str, Any]
) -> str:

    values = [
        room.get(
            "Room_Name",
            ""
        ),
        room.get(
            "Room_Description",
            ""
        ),
        room.get(
            "Package_Name",
            ""
        ),
        room.get(
            "Package_Description",
            ""
        ),
    ]

    text = " ".join(
        str(value)
        for value in values
        if value
    ).lower()

    if "breakfast" in text:
        return "Breakfast"

    if "half board" in text:
        return "Half Board"

    if "full board" in text:
        return "Full Board"

    if "lunch" in text:
        return "Lunch"

    if "dinner" in text:
        return "Dinner"

    if "continental" in text:
        return "Continental"

    return "Room Only"


# ============================================================
# NUMBER OF NIGHTS
# ============================================================

def calculate_nights(
    check_in: date,
    check_out: date
) -> int:

    nights = (
        check_out - check_in
    ).days

    if nights <= 0:

        raise ValueError(
            "Check-out date must be after "
            "check-in date."
        )

    return nights


# ============================================================
# AVAILABLE ROOMS
# ============================================================

def get_available_rooms(
    room: Dict[str, Any],
    check_in: date,
    check_out: date
) -> int:

    availability = room.get(
        "available_rooms",
        {}
    )

    if not isinstance(
        availability,
        dict
    ):
        return 0

    current_date = check_in

    values = []

    while current_date < check_out:

        date_key = current_date.isoformat()

        value = safe_int(
            availability.get(
                date_key,
                0
            ),
            0
        )

        values.append(
            value
        )

        current_date += timedelta(
            days=1
        )

    if not values:
        return 0

    # Availability for the stay is limited
    # by the lowest availability across nights.
    return min(values)


# ============================================================
# MINIMUM NIGHTS
# ============================================================

def get_min_nights(
    room: Dict[str, Any],
    check_in: date
) -> int:

    min_nights = room.get(
        "min_nights",
        {}
    )

    if isinstance(
        min_nights,
        dict
    ):

        value = min_nights.get(
            check_in.isoformat()
        )

        return max(
            1,
            safe_int(
                value,
                1
            )
        )

    return max(
        1,
        safe_int(
            min_nights,
            1
        )
    )


# ============================================================
# STOP SELL / CLOSED
# ============================================================

def is_closed(
    room: Dict[str, Any],
    check_in: date,
    check_out: date
) -> bool:

    current_date = check_in

    while current_date < check_out:

        date_key = current_date.isoformat()

        stopsells = room.get(
            "stopsells",
            {}
        )

        if isinstance(
            stopsells,
            dict
        ):

            if safe_int(
                stopsells.get(
                    date_key,
                    0
                ),
                0
            ) == 1:

                return True

        current_date += timedelta(
            days=1
        )

    close_arrival = room.get(
        "close_on_arrival",
        {}
    )

    if isinstance(
        close_arrival,
        dict
    ):

        if safe_int(
            close_arrival.get(
                check_in.isoformat(),
                0
            ),
            0
        ) == 1:

            return True

    close_departure = room.get(
        "close_on_dept",
        {}
    )

    if isinstance(
        close_departure,
        dict
    ):

        if safe_int(
            close_departure.get(
                check_out.isoformat(),
                0
            ),
            0
        ) == 1:

            return True

    return False


# ============================================================
# PRICE EXTRACTION
# ============================================================

def extract_prices(
    room: Dict[str, Any],
    check_in: date,
    check_out: date
) -> Dict[str, float]:

    rates = room.get(
        "room_rates_info",
        {}
    )

    if not isinstance(
        rates,
        dict
    ):
        rates = {}

    nights = calculate_nights(
        check_in,
        check_out
    )

    # --------------------------------------------------------
    # Total inclusive
    # --------------------------------------------------------

    total_inclusive = safe_float(
        rates.get(
            "totalprice_inclusive_all"
        ),
        0
    )

    # --------------------------------------------------------
    # Total exclusive
    # --------------------------------------------------------

    total_exclusive = safe_float(
        rates.get(
            "totalprice_room_only"
        ),
        0
    )

    # --------------------------------------------------------
    # If total not supplied, calculate date-wise
    # --------------------------------------------------------

    if total_inclusive <= 0:

        inclusive_values = rates.get(
            "inclusive_tax_adjustment",
            {}
        )

        if isinstance(
            inclusive_values,
            dict
        ):

            for i in range(nights):

                current_date = (
                    check_in
                    + timedelta(
                        days=i
                    )
                )

                total_inclusive += safe_float(
                    inclusive_values.get(
                        current_date.isoformat(),
                        0
                    ),
                    0
                )

    if total_exclusive <= 0:

        exclusive_values = rates.get(
            "exclusive_tax",
            {}
        )

        if isinstance(
            exclusive_values,
            dict
        ):

            for i in range(nights):

                current_date = (
                    check_in
                    + timedelta(
                        days=i
                    )
                )

                total_exclusive += safe_float(
                    exclusive_values.get(
                        current_date.isoformat(),
                        0
                    ),
                    0
                )

    # --------------------------------------------------------
    # Nightly price BEFORE TAX
    # --------------------------------------------------------

    if total_exclusive > 0:

        nightly_without_tax = (
            total_exclusive / nights
        )

    else:

        nightly_without_tax = safe_float(
            rates.get(
                "avg_per_night_without_tax"
            ),
            0
        )

    # --------------------------------------------------------
    # Nightly price INCLUDING TAX
    # --------------------------------------------------------

    if total_inclusive > 0:

        nightly_with_tax = (
            total_inclusive / nights
        )

    else:

        nightly_with_tax = safe_float(
            rates.get(
                "avg_per_night_after_discount"
            ),
            0
        )

    taxes = (
        total_inclusive
        - total_exclusive
    )

    if taxes < 0:
        taxes = 0

    return {
        "stay_price":
            round(
                total_inclusive,
                2
            ),

        "stay_price_without_tax":
            round(
                total_exclusive,
                2
            ),

        "nightly_price":
            round(
                nightly_with_tax,
                2
            ),

        "nightly_price_without_tax":
            round(
                nightly_without_tax,
                2
            ),

        "taxes":
            round(
                taxes,
                2
            ),
    }


# ============================================================
# API REQUEST
# ============================================================

def fetch_availability(
    check_in: str,
    check_out: str,
    adults: int = 2,
    children: int = 0,
    rooms: int = 1,
) -> List[Dict[str, Any]]:

    validate_config()

    # IMPORTANT:
    # Do NOT send num_nights when check_out_date
    # is being sent.

    params = {
        "request_type": "RoomList",

        "HotelCode":
            HOTEL_CODE,

        "APIKey":
            OPENAPI_KEY,

        "check_in_date":
            check_in,

        "check_out_date":
            check_out,

        "number_adults":
            adults,

        "number_children":
            children,

        "num_rooms":
            rooms,

        "promotion_code":
            "",

        "property_configuration_info":
            0,

        "showtax":
            1,

        "show_only_available_rooms":
            1,

        "language":
            "en",
    }

    headers = {
        "Accept":
            "application/json",

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/155.0.0.0 "
                "Safari/537.36"
            ),
    }

    print()
    print("=" * 60)
    print("Calling IPMS247 OpenAPI")
    print("=" * 60)

    print(
        "Check-in :",
        check_in
    )

    print(
        "Check-out:",
        check_out
    )

    print(
        "Adults   :",
        adults
    )

    print(
        "Children :",
        children
    )

    print(
        "Rooms    :",
        rooms
    )

    try:

        response = requests.get(
            API_URL,
            params=params,
            headers=headers,
            timeout=45,
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            "Unable to connect to IPMS247 API:\n"
            f"{exc}"
        ) from exc

    print(
        "HTTP Status:",
        response.status_code
    )

    if response.status_code != 200:

        raise RuntimeError(
            "IPMS247 OpenAPI request failed.\n\n"
            f"HTTP Status: "
            f"{response.status_code}\n\n"
            f"{response.text[:3000]}"
        )

    try:

        data = response.json()

    except ValueError as exc:

        raise RuntimeError(
            "IPMS247 API did not return JSON.\n\n"
            f"{response.text[:3000]}"
        ) from exc

    # --------------------------------------------------------
    # Save raw response
    # --------------------------------------------------------

    raw_path = os.path.join(
        DATA_DIR,
        "availability_response.json"
    )

    with open(
        raw_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        "Raw response saved:",
        raw_path
    )

    # --------------------------------------------------------
    # API ERROR
    # --------------------------------------------------------

    if isinstance(
        data,
        list
    ):

        if len(data) == 1:

            first = data[0]

            if isinstance(
                first,
                dict
            ):

                error_details = first.get(
                    "Error Details"
                )

                if error_details:

                    message = error_details.get(
                        "Error_Message",
                        "Unknown API error"
                    )

                    raise RuntimeError(
                        f"IPMS247 API Error: "
                        f"{message}"
                    )

    if not isinstance(
        data,
        list
    ):

        raise RuntimeError(
            "Unexpected IPMS247 API response."
        )

    print(
        "Total rate records:",
        len(data)
    )

    return data


# ============================================================
# PARSE ROOMS
# ============================================================

def parse_rooms(
    raw_rooms: List[Dict[str, Any]],
    check_in: date,
    check_out: date
) -> List[Dict[str, Any]]:

    parsed = []

    nights = calculate_nights(
        check_in,
        check_out
    )

    for index, room in enumerate(
        raw_rooms
    ):

        if not isinstance(
            room,
            dict
        ):
            continue

        # ----------------------------------------------------
        # Identify room type
        # ----------------------------------------------------

        friendly_room_name = (
            normalize_room_type(
                room
            )
        )

        # ----------------------------------------------------
        # Availability
        # ----------------------------------------------------

        available = get_available_rooms(
            room,
            check_in,
            check_out
        )

        if available <= 0:
            continue

        # ----------------------------------------------------
        # Minimum nights
        # ----------------------------------------------------

        min_nights = get_min_nights(
            room,
            check_in
        )

        if nights < min_nights:

            continue

        # ----------------------------------------------------
        # Stop sell
        # ----------------------------------------------------

        if is_closed(
            room,
            check_in,
            check_out
        ):

            continue

        # ----------------------------------------------------
        # Prices
        # ----------------------------------------------------

        prices = extract_prices(
            room,
            check_in,
            check_out
        )

        # ----------------------------------------------------
        # Occupancy
        # ----------------------------------------------------

        max_adults = safe_int(
            room.get(
                "Room_Max_adult",
                room.get(
                    "max_adult_occupancy",
                    2
                )
            ),
            2
        )

        max_children = safe_int(
            room.get(
                "Room_Max_child",
                room.get(
                    "max_child_occupancy",
                    0
                )
            ),
            0
        )

        # The requested output is based on
        # 2 occupants.
        occupancy_text = "2 occupants"

        # ----------------------------------------------------
        # Rate plan
        # ----------------------------------------------------

        rate_plan = clean_room_name(
            room.get(
                "Room_Name",
                friendly_room_name
            )
        )

        # ----------------------------------------------------
        # Meal
        # ----------------------------------------------------

        meal_plan = detect_meal_plan(
            room
        )

        # ----------------------------------------------------
        # Package
        # ----------------------------------------------------

        package_name = clean_html_text(
            room.get(
                "Package_Name",
                ""
            )
        )

        package_id = room.get(
            "Package_Id",
            ""
        )

        deals = room.get(
            "deals",
            ""
        )

        # ----------------------------------------------------
        # Description
        # ----------------------------------------------------

        description = clean_html_text(
            room.get(
                "Room_Description",
                ""
            )
        )

        # ----------------------------------------------------
        # Amenities
        # ----------------------------------------------------

        amenities = clean_html_text(
            room.get(
                "RoomAmenities",
                ""
            )
        )

        # ----------------------------------------------------
        # Cancellation
        # ----------------------------------------------------

        non_refundable = (
            safe_int(
                room.get(
                    "prepaid_noncancel_nonrefundable",
                    0
                ),
                0
            ) == 1
        )

        # ----------------------------------------------------
        # Currency
        # ----------------------------------------------------

        currency_code = room.get(
            "currency_code",
            "INR"
        )

        currency_sign = room.get(
            "currency_sign",
            "Rs"
        )

        # ----------------------------------------------------
        # Image
        # ----------------------------------------------------

        room_image = room.get(
            "room_main_image",
            ""
        )

        # ----------------------------------------------------
        # Room IDs
        # ----------------------------------------------------

        room_type_id = room.get(
            "roomtypeunkid",
            ""
        )

        rate_type_id = room.get(
            "ratetypeunkid",
            ""
        )

        room_rate_id = room.get(
            "roomrateunkid",
            ""
        )

        room_short_code = room.get(
            "Roomtype_Short_code",
            ""
        )

        # ----------------------------------------------------
        # Add parsed record
        # ----------------------------------------------------

        parsed.append({

            "room_name":
                friendly_room_name,

            "room_type":
                room.get(
                    "Roomtype_Name",
                    ""
                ),

            "room_short_code":
                room_short_code,

            "room_type_id":
                room_type_id,

            "rate_type_id":
                rate_type_id,

            "room_rate_id":
                room_rate_id,

            "rate_plan_name":
                rate_plan,

            "available_rooms":
                available,

            "occupancy":
                occupancy_text,

            "max_adults":
                max_adults,

            "max_children":
                max_children,

            "meal_plan":
                meal_plan,

            "min_nights":
                min_nights,

            "requested_nights":
                nights,

            # Tax-inclusive
            "nightly_price":
                prices[
                    "nightly_price"
                ],

            # BEFORE TAX
            "nightly_price_without_tax":
                prices[
                    "nightly_price_without_tax"
                ],

            "stay_price":
                prices[
                    "stay_price"
                ],

            "stay_price_without_tax":
                prices[
                    "stay_price_without_tax"
                ],

            "taxes":
                prices[
                    "taxes"
                ],

            "currency_code":
                currency_code,

            "currency_sign":
                currency_sign,

            "package_name":
                package_name,

            "package_id":
                package_id,

            "deals":
                deals,

            "is_promotion":
                bool(
                    room.get(
                        "IsPromotion",
                        False
                    )
                ),

            "non_refundable":
                non_refundable,

            "description":
                description,

            "amenities":
                amenities,

            "room_image":
                room_image,

            "check_in":
                check_in.strftime(
                    "%d-%m-%Y"
                ),

            "check_out":
                check_out.strftime(
                    "%d-%m-%Y"
                ),

            "_raw_index":
                index,
        })

    return parsed


# ============================================================
# SELECT BEST RATE FOR EACH ROOM TYPE
# ============================================================

def select_best_rates(
    rooms: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    grouped = {}

    for room in rooms:

        key = room.get(
            "room_name",
            "Unknown Room"
        )

        grouped.setdefault(
            key,
            []
        ).append(room)

    final_rooms = []

    for room_name, candidates in grouped.items():

        # ----------------------------------------------------
        # Keep valid prices
        # ----------------------------------------------------

        valid = [
            room
            for room in candidates
            if safe_float(
                room.get(
                    "nightly_price_without_tax",
                    0
                ),
                0
            ) > 0
        ]

        if not valid:

            valid = candidates

        # ----------------------------------------------------
        # Select cheapest valid rate
        # ----------------------------------------------------

        selected = min(
            valid,
            key=lambda room:
                safe_float(
                    room.get(
                        "nightly_price_without_tax",
                        0
                    ),
                    float("inf")
                )
        )

        selected = dict(
            selected
        )

        # ----------------------------------------------------
        # Keep rate plan list
        # ----------------------------------------------------

        rate_plans = []

        for candidate in candidates:

            name = candidate.get(
                "rate_plan_name"
            )

            if (
                name
                and name not in rate_plans
            ):

                rate_plans.append(
                    name
                )

        selected[
            "available_rate_plans"
        ] = rate_plans

        # ----------------------------------------------------
        # Availability
        # ----------------------------------------------------

        # Use the lowest positive availability across the
        # available rate plans for the same room category.
        # This prevents one rate plan from inflating the room
        # count shown to the customer.
        positive_availability = [
            safe_int(
                candidate.get(
                    "available_rooms",
                    0
                ),
                0
            )
            for candidate in candidates
            if safe_int(
                candidate.get(
                    "available_rooms",
                    0
                ),
                0
            ) > 0
        ]

        selected[
            "available_rooms"
        ] = (
            min(positive_availability)
            if positive_availability
            else 0
        )

        final_rooms.append(
            selected
        )

    # --------------------------------------------------------
    # Requested room order
    # --------------------------------------------------------

    order_map = {
        name: index
        for index, name in enumerate(
            ROOM_ORDER
        )
    }

    final_rooms.sort(
        key=lambda room:
            order_map.get(
                room.get(
                    "room_name",
                    ""
                ),
                999
            )
    )

    return final_rooms


# ============================================================
# HUMAN READABLE SUMMARY
# ============================================================

def create_human_readable_summary(
    rooms: List[Dict[str, Any]],
    check_in: str,
    check_out: str
) -> str:

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    lines = []

    lines.append(
        f"For {check_in} - {check_out}, "
        "Here is the Room availability "
        "with prices below:"
    )

    lines.append("")

    # --------------------------------------------------------
    # Room lookup
    # --------------------------------------------------------

    room_lookup = {}

    for room in rooms:

        name = room.get(
            "room_name",
            ""
        )

        existing = room_lookup.get(
            name
        )

        if existing is None:

            room_lookup[name] = room

        else:

            new_price = safe_float(
                room.get(
                    "nightly_price_without_tax",
                    0
                ),
                0
            )

            old_price = safe_float(
                existing.get(
                    "nightly_price_without_tax",
                    0
                ),
                0
            )

            if (
                new_price > 0
                and (
                    old_price <= 0
                    or new_price < old_price
                )
            ):

                room_lookup[name] = room

    # --------------------------------------------------------
    # Create sentences
    # --------------------------------------------------------

    for room_name in ROOM_ORDER:

        room = room_lookup.get(
            room_name
        )

        # IMPORTANT:
        # If API did not return the room as available,
        # don't invent it.

        if not room:
            continue

        available = safe_int(
            room.get(
                "available_rooms",
                0
            ),
            0
        )

        if available <= 0:
            continue

        price = safe_float(
            room.get(
                "nightly_price_without_tax",
                0
            ),
            0
        )

        if price <= 0:
            continue

        occupancy = room.get(
            "occupancy",
            "2 occupants"
        )

        # Customer-facing rate: round DOWN to the nearest ₹100.
        display_price = round_price_down_100(price)

        line = (
            f"{room_name} "
            f"({occupancy}) is available "
            f"for Rs. {display_price:,} "
            "plus taxes per night."
        )

        # ----------------------------------------------------
        # Special note
        # ----------------------------------------------------

        if room_name == "The Glamper room":
            if available == 1:
                line += " (We have 1 Glamper room)"
            else:
                line += (
                    f" (We have {available} Glamper rooms)"
                )

        else:
            note = ROOM_NOTES.get(
                room_name
            )

            if note:
                line += f" ({note})"

        lines.append(
            line
        )

    # --------------------------------------------------------
    # No rooms
    # --------------------------------------------------------

    if len(lines) == 2:

        lines.append(
            "No rooms are available "
            "for the selected dates."
        )

    return "\n".join(
        lines
    )


# ============================================================
# DETAILED TEXT REPORT
# ============================================================

def create_text_report(
    rooms: List[Dict[str, Any]],
    check_in: str,
    check_out: str
) -> str:

    summary = create_human_readable_summary(
        rooms,
        check_in,
        check_out
    )

    lines = [
        summary,
        "",
        "=" * 60,
        "DETAILED ROOM INFORMATION",
        "=" * 60,
        "",
    ]

    for index, room in enumerate(
        rooms,
        start=1
    ):

        lines.append(
            f"{index}. "
            f"{room.get('room_name')}"
        )

        lines.append(
            f"   Available Rooms: "
            f"{room.get('available_rooms')}"
        )

        lines.append(
            f"   Occupancy: "
            f"{room.get('occupancy')}"
        )

        lines.append(
            f"   Meal Plan: "
            f"{room.get('meal_plan')}"
        )

        lines.append(
            f"   Nightly Price Before Tax: "
            f"Rs. "
            f"{round_price_down_100(room.get('nightly_price_without_tax', 0)):,}"
        )

        lines.append(
            f"   Nightly Price Including Tax: "
            f"Rs. "
            f"{room.get('nightly_price', 0):,.2f}"
        )

        lines.append(
            f"   Total Stay Before Tax: "
            f"Rs. "
            f"{room.get('stay_price_without_tax', 0):,.2f}"
        )

        lines.append(
            f"   Total Stay Including Tax: "
            f"Rs. "
            f"{room.get('stay_price', 0):,.2f}"
        )

        lines.append(
            f"   Taxes: "
            f"Rs. "
            f"{room.get('taxes', 0):,.2f}"
        )

        lines.append(
            f"   Minimum Nights: "
            f"{room.get('min_nights')}"
        )

        lines.append("")

    return "\n".join(
        lines
    )


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    rooms: List[Dict[str, Any]]
) -> str:

    path = os.path.join(
        DATA_DIR,
        "room_availability.json"
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            rooms,
            file,
            indent=2,
            ensure_ascii=False
        )

    return path


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(
    rooms: List[Dict[str, Any]]
) -> str:

    path = os.path.join(
        DATA_DIR,
        "room_availability.csv"
    )

    fields = [
        "room_name",
        "room_type",
        "rate_plan_name",
        "available_rooms",
        "occupancy",
        "meal_plan",
        "min_nights",
        "nightly_price_without_tax",
        "nightly_price",
        "stay_price_without_tax",
        "stay_price",
        "taxes",
        "currency_code",
        "package_name",
        "non_refundable",
        "check_in",
        "check_out",
    ]

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        writer.writeheader()

        for room in rooms:

            writer.writerow({
                field:
                    room.get(
                        field,
                        ""
                    )
                for field in fields
            })

    return path


# ============================================================
# SAVE TXT
# ============================================================

def save_text(
    text: str
) -> str:

    path = os.path.join(
        DATA_DIR,
        "room_availability.txt"
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            text
        )

    return path


# ============================================================
# MAIN SCRAPER
# ============================================================

def scrape_availability(
    check_in: Any,
    check_out: Any,
    adults: int = 2,
    children: int = 0,
    rooms: int = 1,
    headless: bool = True,
) -> Dict[str, Any]:

    # Kept for compatibility with older app.py.
    # No browser is used anymore.
    del headless

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    check_in_date = parse_date(
        check_in
    )

    check_out_date = parse_date(
        check_out
    )

    nights = calculate_nights(
        check_in_date,
        check_out_date
    )

    # --------------------------------------------------------
    # Guest information
    # --------------------------------------------------------

    adults = max(
        1,
        safe_int(
            adults,
            2
        )
    )

    children = max(
        0,
        safe_int(
            children,
            0
        )
    )

    rooms = max(
        1,
        safe_int(
            rooms,
            1
        )
    )

    # --------------------------------------------------------
    # API date format
    # --------------------------------------------------------

    api_check_in = (
        check_in_date.isoformat()
    )

    api_check_out = (
        check_out_date.isoformat()
    )

    # --------------------------------------------------------
    # Display date
    # --------------------------------------------------------

    display_check_in = (
        check_in_date.strftime(
            "%d-%m-%Y"
        )
    )

    display_check_out = (
        check_out_date.strftime(
            "%d-%m-%Y"
        )
    )

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------

    raw_rooms = fetch_availability(
        check_in=api_check_in,
        check_out=api_check_out,
        adults=adults,
        children=children,
        rooms=rooms,
    )

    # --------------------------------------------------------
    # Parse
    # --------------------------------------------------------

    parsed_rooms = parse_rooms(
        raw_rooms=raw_rooms,
        check_in=check_in_date,
        check_out=check_out_date,
    )

    print(
        "Available rate plans:",
        len(parsed_rooms)
    )

    # --------------------------------------------------------
    # Group
    # --------------------------------------------------------

    final_rooms = select_best_rates(
        parsed_rooms
    )

    print(
        "Final room categories:",
        len(final_rooms)
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    human_summary = (
        create_human_readable_summary(
            rooms=final_rooms,
            check_in=display_check_in,
            check_out=display_check_out,
        )
    )

    # --------------------------------------------------------
    # Detailed text
    # --------------------------------------------------------

    availability_text = (
        create_text_report(
            rooms=final_rooms,
            check_in=display_check_in,
            check_out=display_check_out,
        )
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    json_path = save_json(
        final_rooms
    )

    csv_path = save_csv(
        final_rooms
    )

    txt_path = save_text(
        availability_text
    )

    print()
    print(human_summary)

    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return {

        "check_in":
            display_check_in,

        "check_out":
            display_check_out,

        "nights":
            nights,

        "adults":
            adults,

        "children":
            children,

        "rooms_requested":
            rooms,

        "rooms":
            final_rooms,

        "human_summary":
            human_summary,

        "availability_text":
            availability_text,

        "raw_response":
            raw_rooms,

        "files": {

            "json":
                json_path,

            "csv":
                csv_path,

            "txt":
                txt_path,
        },
    }


# ============================================================
# COMMAND LINE TEST
# ============================================================

if __name__ == "__main__":

    try:

        result = scrape_availability(
            check_in="05-10-2026",
            check_out="07-10-2026",
            adults=2,
            children=0,
            rooms=1,
        )

        print()
        print("=" * 60)
        print(
            "SCRAPING COMPLETED SUCCESSFULLY"
        )
        print("=" * 60)
        print()

        print(
            result[
                "human_summary"
            ]
        )

    except Exception as exc:

        print()
        print("=" * 60)
        print(
            "SCRAPING FAILED"
        )
        print("=" * 60)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        raise