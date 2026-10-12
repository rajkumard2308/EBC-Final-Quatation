import html
import math
from datetime import date, timedelta
import streamlit as st
import streamlit.components.v1 as components
import main

st.set_page_config(page_title="EBC Final Quotation", page_icon="🏨", layout="wide", initial_sidebar_state="collapsed")
st.markdown('''<style>.block-container{max-width:1150px;padding-top:3.2rem;padding-bottom:2rem}.app-title{font-size:36px;font-weight:800;letter-spacing:-.7px;margin-bottom:2px}.app-subtitle{font-size:16px;opacity:.72;margin-bottom:24px}.quote-card{border:1px solid rgba(128,128,128,.32);border-radius:16px;padding:24px 28px;margin-top:8px;line-height:1.85}div.stButton>button{min-height:44px;border-radius:10px;font-weight:650}</style><div class="app-title">🏨 Everest Base Camp</div><div class="app-subtitle">Room rates, availability & final quotation</div>''', unsafe_allow_html=True)

ROOM_OCCUPANCY = {
    "The Camper room": 2,
    "The Glamper room": 2,
    "The Surveyor room": 2,
    "The Surveyor suite room": 2,
    "The Zenith luxury cottage": 2,
    "The Twin luxury cottage": 4,
    "The Villa": 6,
}
ROOM_TYPES = list(ROOM_OCCUPANCY)

if "check_in_date" not in st.session_state:
    st.session_state.check_in_date = date.today()
if "check_out_date" not in st.session_state:
    st.session_state.check_out_date = date.today() + timedelta(days=1)
if "selected_room_types" not in st.session_state:
    st.session_state.selected_room_types = ["The Glamper room"]

def sync_checkout():
    st.session_state.check_out_date = st.session_state.check_in_date + timedelta(days=1)

def money(value):
    return f"Rs. {value:,.2f}"

def floor_to_hundred(value):
    return math.floor(max(0.0, float(value)) / 100) * 100

def room_availability(result, room_name):
    for item in (result or {}).get("rooms", []) or []:
        if str(item.get("room_name", "")).strip().casefold() == room_name.casefold():
            try:
                return max(0, int(float(item.get("available_rooms", 0) or 0)))
            except (TypeError, ValueError):
                return 0
    return 0

def get_room_rate(room):
    rate = float(room.get("nightly_price_without_tax", 0) or 0)
    if rate <= 0:
        rate = float(room.get("nightly_price", 0) or 0)
    return rate

st.markdown("### Quotation details")
c1, c2 = st.columns(2, gap="large")
with c1:
    check_in = st.date_input("Check-in Date", min_value=date.today(), key="check_in_date", on_change=sync_checkout)
with c2:
    check_out = st.date_input("Checkout Date", min_value=check_in + timedelta(days=1), key="check_out_date")

room_types = st.multiselect(
    "Room Type(s) — select one or more",
    options=ROOM_TYPES,
    key="selected_room_types",
    help="You can combine different room types in one quotation. Room counts are limited by the latest fetched IPMS availability.",
)

cached_result = st.session_state.get("availability_result")
cached_selection = st.session_state.get("quotation_selection")
cached_dates_match = bool(
    cached_result and cached_selection
    and cached_selection.get("check_in") == check_in.isoformat()
    and cached_selection.get("check_out") == check_out.isoformat()
)

room_counts = {}
room_limits = {}
if room_types:
    st.markdown("#### Number of rooms by type")
    count_cols = st.columns(min(3, len(room_types)), gap="large")
    for index, name in enumerate(room_types):
        limit = room_availability(cached_result, name) if cached_dates_match else 14
        # Before the first fetch, allow a provisional selection; the submit
        # handler validates every type against live IPMS availability.
        limit = max(1, limit)
        room_limits[name] = limit
        key = "rooms_count_" + str(ROOM_TYPES.index(name))
        previous = int(st.session_state.get(key, 1) or 1)
        st.session_state[key] = min(max(previous, 1), limit)
        with count_cols[index % len(count_cols)]:
            room_counts[name] = int(st.number_input(
                name,
                min_value=1,
                max_value=limit,
                step=1,
                key=key,
                help=(f"Maximum available: {limit}" if cached_dates_match else "Fetch rates to confirm live availability; this count will be validated before quotation."),
            ))
        if cached_dates_match:
            st.caption(f"{name}: {limit} available")
else:
    st.info("Select at least one room type to continue.")

standard_capacity = sum(ROOM_OCCUPANCY[name] * room_counts.get(name, 0) for name in room_types)
st.caption("Standard occupancy by selection: " + (", ".join(f"{name}: {ROOM_OCCUPANCY[name]} per room × {room_counts.get(name, 0)}" for name in room_types) if room_types else "select room type(s)"))
c3, c4, c5 = st.columns(3, gap="large")
with c3:
    occupants = int(st.number_input("Total No. of Occupants", min_value=1, max_value=100, value=max(2, standard_capacity), step=1))
with c4:
    discount_pct = st.select_slider("Discount Percentage (%)", options=list(range(0, 101, 5)), value=15, help="Discount must be in multiples of 5%.")
with c5:
    include_taxes = st.radio("Quotation rate", ["With taxes", "Without taxes"], horizontal=True)

tax_pct = 18.0
if include_taxes == "With taxes":
    tax_pct = st.number_input("Tax Percentage (%)", min_value=0.0, max_value=100.0, value=18.0, step=1.0)

pet_included = st.checkbox("Include pet in this quotation")
pet_plan = None
if pet_included:
    pet_plan = st.radio("Pet option", ["With food", "Without food"], horizontal=True)
    st.caption("Pet charge: Rs. 3,500/night with food or Rs. 2,500/night without food.")

nights = (check_out - check_in).days
st.caption(f"No. of Nights: {nights}" if nights > 0 else "Checkout date must be after check-in date.")

if st.button("🔍 Fetch Rates & Prepare Final Quotation", type="primary", use_container_width=True):
    if check_out <= check_in:
        st.error("Checkout date must be after check-in date.")
        st.stop()
    if not room_types:
        st.error("Please select at least one room type.")
        st.stop()
    try:
        with st.spinner("Fetching live room rates and availability from IPMS..."):
            # Fetch availability once. We validate every selected room type below.
            # Fetch room inventory using the standard 2-adult search. Do not pass the
            # total party size here: the IPMS endpoint can filter out rooms whose
            # standard occupancy is lower than the requested party size. Extra
            # guest charges are calculated locally after the room rates are fetched.
            result = main.scrape_availability(
                check_in=check_in,
                check_out=check_out,
                adults=2,
                children=0,
                rooms=1,
            )
        st.session_state["availability_result"] = result
        all_rooms = result.get("rooms", []) or []
        validated_counts = {}
        problems = []
        for name in room_types:
            available = room_availability(result, name)
            requested = int(room_counts[name])
            if available <= 0:
                problems.append(f"{name}: no availability returned by IPMS.")
            elif requested > available:
                problems.append(f"{name}: requested {requested}, but only {available} room(s) are available.")
            else:
                validated_counts[name] = requested
        if problems:
            st.session_state.pop("quotation_selection", None)
            st.error("Please correct the room selection based on live availability: " + " ".join(problems))
        else:
            st.session_state["quotation_selection"] = {
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
                "occupants": int(occupants),
                "room_types": list(room_types),
                "room_counts": validated_counts,
                "discount_pct": float(discount_pct),
                "include_taxes": include_taxes,
                "tax_pct": float(tax_pct),
                "pet_included": bool(pet_included),
                "pet_plan": pet_plan,
            }
    except Exception as exc:
        st.error("Unable to fetch live room rates.")
        with st.expander("Show technical error"):
            st.exception(exc)

result = st.session_state.get("availability_result")
selection = st.session_state.get("quotation_selection")
if result is not None:
    all_rooms = result.get("rooms", []) or []
    available_rooms = [r for r in all_rooms if int(float(r.get("available_rooms", 0) or 0)) > 0]
    st.markdown("---")
    if available_rooms:
        with st.expander("Live room availability for selected dates", expanded=False):
            for item in available_rooms:
                st.write(f"**{item.get('room_name', 'Room')}** — {int(float(item.get('available_rooms', 0) or 0))} available")

if result is not None and selection:
    ci = date.fromisoformat(selection["check_in"])
    co = date.fromisoformat(selection["check_out"])
    stay_nights = (co - ci).days
    all_rooms = result.get("rooms", []) or []
    room_by_name = {str(r.get("room_name", "")).strip().casefold(): r for r in all_rooms}
    chosen_types = selection.get("room_types", [])
    counts = selection.get("room_counts", {})
    st.markdown("## Final Quotation")
    quote_lines = []
    quote_lines.extend([
        "Please find the details below:",
        f"Check-in Date: {ci.strftime('%d-%m-%Y')}",
        f"Checkout Date: {co.strftime('%d-%m-%Y')}",
        f"No of Occupants: {selection['occupants']}",
        f"No of Nights: {stay_nights}",
    ])
    room_subtotal = 0.0
    total_rooms = 0
    room_breakdown = []
    total_standard_capacity = 0
    missing = []
    for name in chosen_types:
        room = room_by_name.get(name.casefold())
        count = int(counts.get(name, 0))
        if not room or int(float(room.get("available_rooms", 0) or 0)) < count:
            missing.append(name)
            continue
        api_rate = get_room_rate(room)
        if api_rate <= 0:
            missing.append(name)
            continue
        rounded_rate = floor_to_hundred(api_rate)
        line_subtotal = rounded_rate * stay_nights * count
        room_subtotal += line_subtotal
        total_rooms += count
        total_standard_capacity += ROOM_OCCUPANCY[name] * count
        room_breakdown.append((name, count, rounded_rate, line_subtotal, api_rate))
    if missing:
        st.error("No valid live rate/availability for: " + ", ".join(missing) + ". Fetch rates again or choose different room types.")
    elif not room_breakdown:
        st.warning("Select room type(s) and fetch live rates to generate a quotation.")
    else:
        for name, count, rate, line_subtotal, api_rate in room_breakdown:
            quote_lines.append(f"Room Type: {name} ({count} rooms) — {money(rate)} per room/night")
        quote_lines.extend(["Check-in Time: 2:00 PM", "Checkout Time: 10:30 AM", "Meal plan: Continental Plan"])
        extra_guest_count = max(0, int(selection["occupants"]) - total_standard_capacity)
        extra_guest_charge = extra_guest_count * 3500.0 * stay_nights
        pet_charge = ((3500.0 if selection.get("pet_plan") == "With food" else 2500.0) * stay_nights) if selection.get("pet_included") else 0.0
        subtotal = room_subtotal + extra_guest_charge + pet_charge
        tax_amount = subtotal * float(selection.get("tax_pct", 18.0)) / 100.0
        total_with_tax = subtotal + tax_amount
        if selection["include_taxes"] == "With taxes":
            final_total = total_with_tax
            total_line = f"Total (inclusive of taxes and breakfast): {money(final_total)}"
        else:
            final_total = subtotal
            total_line = f"Total (breakfast included): {money(final_total)}"
        discounted = final_total * (1 - float(selection["discount_pct"]) / 100.0)
        quote_lines.append(total_line)
        if extra_guest_charge:
            quote_lines.append(f"Extra guest charges ({extra_guest_count} extra guests × Rs. 3,500 × {stay_nights} nights): {money(extra_guest_charge)}")
        if pet_charge:
            quote_lines.append(f"Pet ({selection['pet_plan'].lower()}, {stay_nights} night(s)): {money(pet_charge)}")
        # Show the discounted price only when a positive discount is applied.
        discount_pct = float(selection.get("discount_pct", 0) or 0)
        if discount_pct > 0:
            if selection["include_taxes"] == "With taxes":
                quote_lines.append(
                    f"Total price after {discount_pct:g}% discount: {money(discounted)}"
                )
            else:
                quote_lines.append(
                    f"If you pay by cash, total price after {discount_pct:g}% discount: {money(discounted)}"
                )
        quotation = "\n".join(quote_lines)
        # Render the quotation and its copy button together so the button sits
        # in the top-right corner of the quotation card. No separate copy section.
        escaped = html.escape(quotation, quote=True)
        quote_html_lines = "<br>".join(html.escape(line) for line in quote_lines)
        component_height = max(300, 150 + len(quote_lines) * 34)
        components.html(f'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #0e1117; color: #ffffff; font-family: Arial, sans-serif; }}
body {{ color: #ffffff; }}
.quote-card {{ position: relative; background: #0e1117; color: #ffffff; border: 1px solid #343841; border-radius: 16px; padding: 28px; padding-top: 66px; line-height: 1.85; font-size: 16px; overflow-wrap: anywhere; }}
.quote-card div {{ color: #ffffff; }}
#copyStatus {{ color: #ffffff; }}
.copy-wrap {{ position: absolute; top: 16px; right: 16px; display: flex; align-items: center; gap: 10px; }}
#copyQuote {{ padding: 10px 15px; border: 0; border-radius: 9px; background: #2563eb; color: white; font-weight: 700; cursor: pointer; font-size: 14px; white-space: nowrap; }}
#copyStatus {{ font-size: 12px; }}
@media (max-width: 520px) {{ .quote-card {{ padding: 18px; padding-top: 68px; }} .copy-wrap {{ top: 12px; right: 12px; }} }}
</style>
</head>
<body>
<div class="quote-card">
  <div class="copy-wrap">
    <button id="copyQuote" type="button">📋 Copy quotation</button>
    <span id="copyStatus" aria-live="polite"></span>
  </div>
  <div>{quote_html_lines}</div>
</div>
<textarea id="quoteText" aria-hidden="true" style="position:absolute;left:-9999px;top:0">{escaped}</textarea>
<script>
document.getElementById('copyQuote').addEventListener('click', async () => {{
  const text = document.getElementById('quoteText').value;
  const status = document.getElementById('copyStatus');
  try {{
    await navigator.clipboard.writeText(text);
    status.textContent = 'Copied!';
  }} catch (e) {{
    const area = document.getElementById('quoteText');
    area.style.position = 'static'; area.style.left = 'auto'; area.select();
    const ok = document.execCommand('copy');
    area.style.position = 'absolute'; area.style.left = '-9999px';
    status.textContent = ok ? 'Copied!' : 'Please select and copy the quotation.';
  }}
}});
</script>
</body>
</html>''', height=component_height, scrolling=False)
        rate_summary = "; ".join(f"{name}: API {money(api_rate)} → rounded {money(rate)} per room/night × {count}" for name, count, rate, _, api_rate in room_breakdown)
        st.caption(f"{rate_summary}. Room subtotal before tax: {money(room_subtotal)}. Extra-guest and pet charges are calculated per night before tax.")
