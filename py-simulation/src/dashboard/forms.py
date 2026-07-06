"""Auto-generated config form from Pydantic JSON Schema."""

import json

import streamlit as st

from src.config import Config


def _parse_free_text(text: str):
    """Parse a free-text widget value: '' → None (field omitted → default),
    JSON for numbers/lists, otherwise the raw string."""
    text = text.strip()
    if text in ("", "None", "none", "null"):
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def _resolve_ref(ref: str, schema: dict) -> dict:
    """Resolve a JSON Schema $ref like '#/$defs/ArrayConfig' to the actual definition."""
    parts = ref.lstrip("#/").split("/")
    current = schema
    for p in parts:
        current = current[p]
    return current


def _title_from_key(key: str) -> str:
    return key.replace("_", " ").title()


def _subtitle(schema: dict, key: str) -> str:
    prop = schema.get("properties", {}).get(key, {})
    unit = prop.get("unit", "")
    desc = prop.get("description", "")
    parts = [desc] if desc else []
    if unit:
        parts.append(f"[{unit}]")
    return " — ".join(parts)


def _build_form(schema: dict, prefix: str = "", root: dict | None = None) -> dict:
    """Render Streamlit widgets for a JSON Schema object and return collected values.

    `root` is the top-level schema holding `$defs`; refs must always be
    resolved against it, not against the nested schema being rendered.
    """
    if root is None:
        root = schema
    values = {}
    props = schema.get("properties", {})
    for key, prop in props.items():
        full_key = f"{prefix}.{key}" if prefix else key
        ptype = prop.get("type", "")
        ref = prop.get("$ref", "")
        default = prop.get("default")
        description = prop.get("description", "")
        minimum = prop.get("minimum") or prop.get("exclusiveMinimum")
        maximum = prop.get("maximum") or prop.get("exclusiveMaximum")
        enum = prop.get("enum")
        unit = prop.get("unit", "")
        label = prop.get("title", _title_from_key(key))

        variants = prop.get("oneOf") or prop.get("anyOf") or []
        ref_variants = [v["$ref"] for v in variants if "$ref" in v]

        if "const" in prop:
            # Literal discriminator fields (e.g. array 'type') are not editable.
            values[key] = prop["const"]

        elif ref:
            nested_schema = _resolve_ref(ref, root)
            with st.expander(f"**{label}**", expanded=False):
                if description:
                    st.caption(description)
                values[key] = _build_form(nested_schema, prefix=full_key, root=root)

        elif len(ref_variants) > 1:
            # Union of models (e.g. array geometry): pick a variant, render it.
            defs = {r: _resolve_ref(r, root) for r in ref_variants}
            names = {
                r: d.get("properties", {}).get("type", {}).get("const", d.get("title", r))
                for r, d in defs.items()
            }
            with st.expander(f"**{label}**", expanded=False):
                if description:
                    st.caption(description)
                chosen = st.selectbox(
                    f"{label} type", options=ref_variants,
                    format_func=lambda r: names[r],
                    key=f"{full_key}._variant",
                )
                values[key] = _build_form(
                    defs[chosen], prefix=f"{full_key}.{names[chosen]}", root=root
                )

        elif ptype == "object" and prop.get("properties"):
            with st.expander(f"**{label}**", expanded=False):
                if description:
                    st.caption(description)
                values[key] = _build_form(prop, prefix=full_key, root=root)

        elif ptype == "object":
            # Free-form dict field (e.g. trajectory, initial_bearing): edit as JSON.
            text = st.text_input(
                label, value=json.dumps(default) if default is not None else "",
                key=full_key, help=description,
            )
            values[key] = _parse_free_text(text)

        elif ptype == "boolean":
            values[key] = st.checkbox(label, value=default, key=full_key,
                                     help=description)

        elif ptype == "integer":
            if minimum is not None and maximum is not None:
                values[key] = st.slider(label, min_value=int(minimum),
                                       max_value=int(maximum),
                                       value=int(default), key=full_key,
                                       help=description)
            else:
                values[key] = st.number_input(label, value=int(default),
                                             step=1, key=full_key,
                                             help=description)

        elif ptype == "number":
            fmt_val = _subtitle(schema, key) or description
            if minimum is not None and maximum is not None:
                mn = float(minimum) if "minimum" in prop else 0.0
                mx = float(maximum)
                values[key] = st.slider(label, min_value=mn, max_value=mx,
                                       value=float(default), key=full_key,
                                       help=fmt_val)
            else:
                values[key] = st.number_input(label, value=float(default),
                                             key=full_key, help=fmt_val)

        elif enum:
            values[key] = st.selectbox(label, options=list(enum),
                                      index=list(enum).index(default) if default in enum else 0,
                                      key=full_key, help=description)

        else:
            # JSON, not str(): repr of a string list (single quotes) would
            # not survive the _parse_free_text round-trip.
            if default is None:
                text_default = ""
            else:
                try:
                    text_default = json.dumps(default)
                except (TypeError, ValueError):
                    text_default = str(default)
            text = st.text_input(label, value=text_default,
                                key=full_key, help=description)
            values[key] = _parse_free_text(text)

    return values


_ARRAY_VARIANT_REFS = {
    "dual_ring": "#/$defs/DualRingArrayConfig",
    "single_ring": "#/$defs/SingleRingArrayConfig",
    "xyz": "#/$defs/ArbitraryArrayConfig",
}

_TOP_LEVEL_SECTIONS = (
    "array", "signal", "mic", "drone", "srpphat", "environment", "output",
    "mcu",
)

QUICK_OVERRIDES = {
    "signal": {"duration": 4.0},
    "srpphat": {"max_freq": 2000.0, "search": {"resolution_deg": 4.0}},
    "output": {"save_animation": False},
}


def apply_overrides_to_widget_state(overrides: dict, prefix: str = "") -> None:
    """Write override values into widget session-state keys.

    Must run BEFORE the widgets are instantiated (Streamlit forbids writing
    a widget's key after it has rendered in the same run)."""
    for k, v in overrides.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            apply_overrides_to_widget_state(v, key)
        else:
            st.session_state[key] = v


def apply_array_to_widget_state(array_dict: dict) -> None:
    """Point the array-variant selector and its sub-form at a geometry."""
    kind = array_dict.get("type", "dual_ring")
    st.session_state["array._variant"] = _ARRAY_VARIANT_REFS[kind]
    fields = {k: v for k, v in array_dict.items() if k != "type"}
    apply_overrides_to_widget_state(fields, prefix=f"array.{kind}")


def _reset_form_widget_state() -> None:
    for key in list(st.session_state.keys()):
        if any(key == s or key.startswith(f"{s}.") for s in _TOP_LEVEL_SECTIONS):
            del st.session_state[key]


def render_config_form() -> Config:
    """Render the full configuration form and return a Config object."""
    schema = Config.model_json_schema()

    # Pending state changes must be applied before any widget renders.
    preset = st.session_state.pop("config_preset", None)
    if preset == "default":
        _reset_form_widget_state()
        st.info("Form reset to defaults")
    elif preset == "quick":
        apply_overrides_to_widget_state(QUICK_OVERRIDES)
        st.info("Quick mode applied: 4s duration, 4° resolution, "
                "max_freq=2000, no animation")

    handoff = st.session_state.pop("handoff_array_config", None)
    if handoff is not None:
        apply_array_to_widget_state(handoff)
        st.info("Array geometry loaded from the Educational tab")

    st.subheader("Simulation Configuration")

    col1, col2 = st.columns([1, 5])
    with col1:
        st.markdown("**Quick Presets**")
        if st.button("Default", key="preset_default"):
            st.session_state["config_preset"] = "default"
            st.session_state["config_form_submitted"] = False
            st.rerun()
        if st.button("Quick Mode", key="preset_quick"):
            st.session_state["config_preset"] = "quick"
            st.session_state["config_form_submitted"] = False
            st.rerun()

    with col2:
        raw = _build_form(schema, prefix="")

    return Config.from_dict(raw)
