"""Auto-generated config form from Pydantic JSON Schema."""

import streamlit as st

from ..config import Config


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


def _build_form(schema: dict, prefix: str = "") -> dict:
    """Render Streamlit widgets for a JSON Schema object and return collected values."""
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

        if ref:
            nested_schema = _resolve_ref(ref, schema)
            with st.expander(f"**{label}**", expanded=False):
                if description:
                    st.caption(description)
                values[key] = _build_form(nested_schema, prefix=full_key)

        elif ptype == "object":
            with st.expander(f"**{label}**", expanded=False):
                if description:
                    st.caption(description)
                values[key] = _build_form(prop, prefix=full_key)

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
            values[key] = st.text_input(label, value=str(default) if default is not None else "",
                                       key=full_key, help=description)

    return values


def render_config_form() -> Config:
    """Render the full configuration form and return a Config object."""
    schema = Config.model_json_schema()

    st.subheader("Simulation Configuration")

    col1, col2 = st.columns([1, 5])
    with col1:
        st.markdown("**Quick Presets**")
        if st.button("Default", key="preset_default"):
            st.session_state["config_form_submitted"] = False
            st.rerun()
        if st.button("Quick Mode", key="preset_quick"):
            st.session_state["config_preset"] = "quick"
            st.session_state["config_form_submitted"] = False
            st.rerun()

    with col2:
        raw = _build_form(schema, prefix="")

    # Apply quick preset if selected
    if st.session_state.get("config_preset") == "quick":
        from ..config import deep_merge
        quick_overrides = {
            "signal": {"duration": 4.0},
            "srpphat": {"max_freq": 2000.0, "search": {"resolution_deg": 4.0}},
            "output": {"save_animation": False},
        }
        deep_merge(raw, quick_overrides)
        st.session_state["config_preset"] = None
        st.info("Quick mode applied: 4s duration, 4° resolution, max_freq=2000, no animation")

    return Config.from_dict(raw)
